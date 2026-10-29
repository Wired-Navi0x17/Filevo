//! Detail views for MODEL, STATUS and HELP.  They share one scrollable text
//! surface so long Python reports remain usable at any terminal size.

use crate::app::{App, BackendState, Focus, View, COMMANDS};
use crate::model::format_epoch_document;
use crate::ui::text::{pad, truncate, wrap};
use crate::ui::theme::Theme;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, Paragraph};
use ratatui::Frame;

const SPINNER: [&str; 8] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧"];

pub struct DetailMetrics {
    pub max_scroll: usize,
    pub viewport: usize,
}

fn push_wrapped(lines: &mut Vec<Line<'static>>, text: &str, style: Style, width: usize) {
    for line in wrap(text, width) {
        lines.push(Line::from(Span::styled(line, style)));
    }
}

fn heading(lines: &mut Vec<Line<'static>>, title: &str, theme: &Theme) {
    if !lines.is_empty() {
        lines.push(Line::default());
    }
    lines.push(Line::from(Span::styled(
        title.to_string(),
        Style::default()
            .fg(theme.primary)
            .add_modifier(Modifier::BOLD),
    )));
}

fn field(
    lines: &mut Vec<Line<'static>>,
    label: &str,
    value: &str,
    theme: &Theme,
    width: usize,
) {
    let prefix = format!("  {label}: ");
    let budget = width.saturating_sub(crate::ui::text::width(&prefix)).max(8);
    lines.push(Line::from(vec![
        Span::styled(prefix, Style::default().fg(theme.text_dim)),
        Span::styled(truncate(value, budget), Style::default().fg(theme.text)),
    ]));
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) -> DetailMetrics {
    if area.width < 4 || area.height < 3 {
        return DetailMetrics {
            max_scroll: 0,
            viewport: 0,
        };
    }
    let (title, icon) = match app.view {
        View::Model => ("Model Telemetry", theme.glyph("◈", "*")),
        View::Status => ("System Status", theme.glyph("⚙", "*")),
        View::Help => ("Help & Command Reference", theme.glyph("?", "?")),
        View::Home => ("Conversation", theme.glyph("❯", ">")),
    };
    let block = if app.focus == Focus::Conversation {
        theme.focused_panel()
    } else {
        theme.panel()
    }
    .title(Span::styled(
        format!(" {icon} {title} "),
        Style::default()
            .fg(theme.primary)
            .add_modifier(Modifier::BOLD),
    ));
    let inner = block.inner(area);
    frame.render_widget(block, area);
    if inner.width == 0 || inner.height == 0 {
        return DetailMetrics {
            max_scroll: 0,
            viewport: 0,
        };
    }
    let width = inner.width as usize;
    let mut lines: Vec<Line<'static>> = vec![Line::default()];
    match app.view {
        View::Model => model_view(&mut lines, app, theme, width),
        View::Status => status_view(&mut lines, app, theme, width),
        View::Help => help_view(&mut lines, app, theme, width),
        View::Home => {}
    }

    let viewport = inner.height as usize;
    let max_scroll = lines.len().saturating_sub(viewport);
    let scroll = app.detail_scroll.min(max_scroll);
    frame.render_widget(
        Paragraph::new(Text::from(lines))
            .style(Style::default().bg(theme.panel_bg))
            .scroll((scroll.min(u16::MAX as usize) as u16, 0)),
        inner,
    );
    DetailMetrics {
        max_scroll,
        viewport,
    }
}

fn spinner_line(app: &App, label: &str, theme: &Theme) -> Line<'static> {
    let frame_char = if theme.unicode {
        SPINNER[(app.tick as usize) % SPINNER.len()]
    } else {
        "*"
    };
    Line::from(vec![
        Span::styled(
            format!("  {frame_char} "),
            Style::default().fg(theme.primary),
        ),
        Span::styled(label.to_string(), Style::default().fg(theme.amber)),
    ])
}

fn model_view(lines: &mut Vec<Line<'static>>, app: &App, theme: &Theme, width: usize) {
    if app.demo {
        lines.push(Line::from(Span::styled(
            "  Demo fixture · these values are not live telemetry",
            Style::default()
                .fg(theme.amber)
                .add_modifier(Modifier::BOLD),
        )));
    }
    if app.detail_loading {
        lines.push(spinner_line(app, "Reading model telemetry…", theme));
    }
    if let Some(error) = &app.detail_error {
        lines.push(Line::from(Span::styled(
            format!("  {error}"),
            Style::default().fg(theme.red),
        )));
    }
    if let Some(output) = &app.model_output {
        heading(lines, "Backend report", theme);
        for line in output.lines() {
            for wrapped in wrap(line, width.saturating_sub(2)) {
                lines.push(Line::from(Span::styled(
                    format!("  {wrapped}"),
                    Style::default().fg(theme.text),
                )));
            }
        }
    } else {
        let dashboard = &app.dashboard;
        let received = app.demo
            || dashboard.generated_at.is_some()
            || !dashboard.model.id.is_empty()
            || matches!(app.backend, BackendState::Online);
        heading(lines, "Model", theme);
        if !received {
            lines.push(Line::from(Span::styled(
                "  Waiting for the Filevo daemon…",
                Style::default().fg(theme.text_dim),
            )));
        } else {
            field(
                lines,
                "Identifier",
                if dashboard.model.id.is_empty() {
                    "Not reported"
                } else {
                    &dashboard.model.id
                },
                theme,
                width,
            );
            field(lines, "Name", dashboard.model.display_name(), theme, width);
            field(
                lines,
                "Device",
                if dashboard.model.device.is_empty() {
                    "Not reported"
                } else {
                    &dashboard.model.device
                },
                theme,
                width,
            );
            field(
                lines,
                "Context",
                &dashboard.model.context_label(),
                theme,
                width,
            );
            field(
                lines,
                "Loaded",
                if dashboard.model.loaded { "Yes" } else { "No" },
                theme,
                width,
            );
            if let Some(error) = &dashboard.model.load_error {
                field(lines, "Load error", error, theme, width);
            }
        }

        heading(lines, "Policy", theme);
        field(
            lines,
            "Status",
            if dashboard.session.policy_status.trim().is_empty() {
                "Unknown"
            } else {
                &dashboard.session.policy_status
            },
            theme,
            width,
        );
        field(
            lines,
            "Episodes",
            &dashboard.policy.episodes.to_string(),
            theme,
            width,
        );
        field(
            lines,
            "Baseline",
            &format!("{:.3}", dashboard.policy.baseline),
            theme,
            width,
        );
        field(
            lines,
            "Temperature",
            &format!("{:.2}", dashboard.policy.temperature),
            theme,
            width,
        );
        if !dashboard.policy.archetypes.is_empty() {
            heading(lines, "Policy archetype weights", theme);
            for (name, value) in dashboard.policy.archetypes.iter().take(8) {
                let label = format!("  {:<24}", truncate(name, 24));
                lines.push(Line::from(vec![
                    Span::styled(label, Style::default().fg(theme.text_dim)),
                    Span::styled(
                        format!("{:.1}%", value * 100.0),
                        Style::default().fg(theme.text),
                    ),
                ]));
            }
        }
        if !dashboard.policy.fonts.is_empty() {
            heading(lines, "Policy font weights", theme);
            for (name, value) in dashboard.policy.fonts.iter().take(6) {
                let label = format!("  {:<24}", truncate(name, 24));
                lines.push(Line::from(vec![
                    Span::styled(label, Style::default().fg(theme.text_dim)),
                    Span::styled(
                        format!("{:.1}%", value * 100.0),
                        Style::default().fg(theme.text),
                    ),
                ]));
            }
        }
        if app.demo {
            lines.push(Line::default());
            lines.push(Line::from(Span::styled(
                "  Launch without --demo to read the live daemon.",
                Style::default().fg(theme.muted),
            )));
        }
    }
}

fn status_view(lines: &mut Vec<Line<'static>>, app: &App, theme: &Theme, width: usize) {
    if app.demo {
        lines.push(Line::from(Span::styled(
            "  Demo fixture · these values are not live telemetry",
            Style::default()
                .fg(theme.amber)
                .add_modifier(Modifier::BOLD),
        )));
    }
    if app.detail_loading {
        lines.push(spinner_line(app, "Reading system status…", theme));
    }
    if let Some(error) = &app.detail_error {
        lines.push(Line::from(Span::styled(
            format!("  {error}"),
            Style::default().fg(theme.red),
        )));
    }
    if let Some(output) = &app.status_output {
        heading(lines, "Backend report", theme);
        for line in output.lines() {
            for wrapped in wrap(line, width.saturating_sub(2)) {
                lines.push(Line::from(Span::styled(
                    format!("  {wrapped}"),
                    Style::default().fg(theme.text),
                )));
            }
        }
        return;
    }

    let dashboard = &app.dashboard;
    heading(lines, "Connection", theme);
    let backend = match &app.backend {
        BackendState::Demo => "Demo (no backend)".to_string(),
        BackendState::Connecting => "Connecting".to_string(),
        BackendState::Online => "Live daemon".to_string(),
        BackendState::Offline(error) => format!("Offline: {error}"),
    };
    field(lines, "Backend", &backend, theme, width);
    field(
        lines,
        "Snapshot",
        &format_epoch_document(dashboard.generated_at),
        theme,
        width,
    );

    heading(lines, "Session", theme);
    field(
        lines,
        "Files indexed",
        &dashboard.session.files_indexed.to_string(),
        theme,
        width,
    );
    field(
        lines,
        "Documents created",
        &dashboard.session.docs_created.to_string(),
        theme,
        width,
    );
    field(
        lines,
        "Conversation memory",
        &if dashboard.session.memory_limit > 0 {
            format!(
                "{}/{} turns",
                dashboard.session.memory_used, dashboard.session.memory_limit
            )
        } else {
            "Not reported".to_string()
        },
        theme,
        width,
    );

    heading(lines, "Hardware", theme);
    match &dashboard.telemetry.gpu {
        Some(gpu) => {
            field(lines, "GPU", &gpu.name, theme, width);
            field(
                lines,
                "GPU utilisation",
                &format!("{:.0}%", gpu.utilization),
                theme,
                width,
            );
            field(
                lines,
                "GPU memory",
                &format!(
                    "{:.0} / {:.0} MB",
                    gpu.memory_used_mb, gpu.memory_total_mb
                ),
                theme,
                width,
            );
        }
        None => field(lines, "GPU", "Not reported", theme, width),
    }
    match &dashboard.telemetry.system_memory {
        Some(memory) => field(
            lines,
            "System memory",
            &format!(
                "{} / {}",
                crate::model::format_size(memory.used),
                crate::model::format_size(memory.total)
            ),
            theme,
            width,
        ),
        None => field(lines, "System memory", "Not reported", theme, width),
    }

    heading(lines, "Storage", theme);
    match &dashboard.telemetry.disk {
        Some(disk) => {
            field(lines, "Path", &disk.path, theme, width);
            field(
                lines,
                "Used",
                &format!(
                    "{} of {} ({} free)",
                    crate::model::format_size(disk.used),
                    crate::model::format_size(disk.total),
                    crate::model::format_size(disk.free)
                ),
                theme,
                width,
            );
        }
        None => field(lines, "Disk", "Not reported", theme, width),
    }

    heading(lines, "Web grounding", theme);
    field(
        lines,
        "Enabled",
        if dashboard.telemetry.web.enabled {
            "Yes"
        } else {
            "No"
        },
        theme,
        width,
    );
    field(
        lines,
        "Live references",
        &dashboard.telemetry.web.live_references.to_string(),
        theme,
        width,
    );
    field(
        lines,
        "Last result",
        &dashboard.telemetry.web.last_result,
        theme,
        width,
    );

    if !dashboard.errors.is_empty() {
        heading(lines, "Backend warnings", theme);
        for error in &dashboard.errors {
            for wrapped in wrap(error, width.saturating_sub(4)) {
                lines.push(Line::from(Span::styled(
                    format!("  ! {wrapped}"),
                    Style::default().fg(theme.amber),
                )));
            }
        }
    }
}

fn help_view(lines: &mut Vec<Line<'static>>, app: &App, theme: &Theme, width: usize) {
    if app.demo {
        lines.push(Line::from(Span::styled(
            "  Demo mode uses the reference fixtures and blocks backend actions.",
            Style::default().fg(theme.amber),
        )));
    }
    heading(lines, "Commands", theme);
    let usage_width = COMMANDS
        .iter()
        .map(|spec| crate::ui::text::width(spec.usage))
        .max()
        .unwrap_or(20)
        .min(28);
    for spec in COMMANDS {
        if width >= usage_width + 30 {
            lines.push(Line::from(vec![
                Span::styled(
                    format!("  {}", pad(spec.usage, usage_width)),
                    Style::default()
                        .fg(theme.primary)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled("  ", Style::default()),
                Span::styled(spec.description, Style::default().fg(theme.text_dim)),
            ]));
        } else {
            lines.push(Line::from(Span::styled(
                format!("  {}", spec.usage),
                Style::default()
                    .fg(theme.primary)
                    .add_modifier(Modifier::BOLD),
            )));
            for line in wrap(spec.description, width.saturating_sub(6)) {
                lines.push(Line::from(Span::styled(
                    format!("     {line}"),
                    Style::default().fg(theme.text_dim),
                )));
            }
        }
    }

    heading(lines, "Keyboard", theme);
    let keys = [
        ("Enter", "Send the message or command"),
        ("Tab", "Complete a slash command; Ctrl+Tab moves focus"),
        ("Up / Down", "History in the prompt; scroll in focused panels"),
        ("PgUp / PgDn", "Page through the conversation or detail report"),
        ("Esc", "Move focus between the prompt and navigation"),
        ("F1", "Open this help view"),
        ("F6", "Cycle focus between visible panels"),
        ("Alt+1 … 8", "Jump to HOME … HELP"),
        ("Ctrl+A / Ctrl+E", "Start / end of the input line"),
        ("Ctrl+U", "Clear the input line"),
        ("Ctrl+R", "Refresh live dashboard telemetry"),
        ("Ctrl+C", "Cancel the running backend task"),
        ("Ctrl+Q", "Exit Filevo and restore the terminal"),
    ];
    for (key, description) in keys {
        lines.push(Line::from(vec![
            Span::styled(
                format!("  {:<16}", key),
                Style::default()
                    .fg(theme.text)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(description, Style::default().fg(theme.text_dim)),
        ]));
    }

    heading(lines, "Attachments", theme);
    push_wrapped(
        lines,
        "Mention a generated document with @/absolute/path.docx. Focus Recent Documents (F6) and press Enter to insert an attachment.",
        Style::default().fg(theme.text_dim),
        width.saturating_sub(2),
    );

    heading(lines, "RLCD semantics", theme);
    push_wrapped(
        lines,
        "Confidence is the probability of the selected intent. Entropy is normalized Shannon entropy in base 2 (0 = certain, 1 = uniform).",
        Style::default().fg(theme.text_dim),
        width.saturating_sub(2),
    );
    push_wrapped(
        lines,
        "The panel at HOME only plots a distribution after the current prompt was evaluated and the five probabilities passed validation. The backend's default prior is withheld because it is not a live calibration.",
        Style::default().fg(theme.text_dim),
        width.saturating_sub(2),
    );

    heading(lines, "Terminal", theme);
    push_wrapped(
        lines,
        "FILEVO_ASCII=1 disables Unicode artwork. NO_COLOR=1 disables colour. The interface requires at least 60×20 cells and offers compact, standard and spacious layouts.",
        Style::default().fg(theme.text_dim),
        width.saturating_sub(2),
    );
}
