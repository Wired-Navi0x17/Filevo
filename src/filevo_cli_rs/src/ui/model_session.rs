//! Model and Session panel.  Every value comes from the live dashboard; when
//! the backend has not answered yet the panel says so instead of inventing a
//! model name or a CUDA device.

use crate::app::App;
use crate::model::Dashboard;
use crate::ui::text::{truncate, width};
use crate::ui::theme::Theme;
use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, Paragraph};

fn label(
    icon: &'static str,
    name: &str,
    value: &str,
    theme: &Theme,
    max_width: usize,
) -> Line<'static> {
    let prefix = format!("{icon} {name}: ");
    let prefix_width = width(&prefix);
    let budget = max_width.saturating_sub(prefix_width);
    Line::from(vec![
        Span::styled(format!("{icon} "), Style::default().fg(theme.primary)),
        Span::styled(format!("{name}: "), theme.label_style()),
        Span::styled(truncate(value, budget), theme.value_style()),
    ])
}

fn device_label(dashboard: &Dashboard) -> String {
    let device = dashboard.model.device.trim();
    let gpu = dashboard
        .telemetry
        .gpu
        .as_ref()
        .map(|gpu| gpu.name.as_str())
        .unwrap_or("");
    if let Some(rest) = gpu.split("RTX").nth(1) {
        let mut tokens = rest.split_whitespace();
        let number = tokens.next().unwrap_or("").trim();
        if !number.is_empty() {
            return format!("RTX {number} (CUDA)");
        }
    }
    match device.to_ascii_lowercase().as_str() {
        "cuda" => "CUDA (adapter not reported)".to_string(),
        "cpu" => "CPU".to_string(),
        "" => "Unknown".to_string(),
        other => other.to_string(),
    }
}

fn web_label(dashboard: &Dashboard) -> String {
    let web = &dashboard.telemetry.web;
    if !web.enabled {
        return "Disabled".to_string();
    }
    if web.live_references > 0 {
        format!("Enabled · {} live", web.live_references)
    } else {
        format!("Enabled · {}", web.last_result)
    }
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    if area.width < 4 || area.height < 2 {
        return;
    }
    let ticker = crate::ui::art::radar_glyph(app.tick);
    let block = theme.panel().title(Line::from(vec![
        Span::styled(format!(" {} ", ticker), Style::default().fg(theme.primary)),
        Span::styled(
            "Model ",
            Style::default().fg(theme.text).add_modifier(Modifier::BOLD),
        ),
    ]));
    let inner = block.inner(area);
    frame.render_widget(block, area);
    if inner.width == 0 || inner.height == 0 {
        return;
    }

    let dashboard = &app.dashboard;
    let connected = !matches!(app.backend, crate::app::BackendState::Connecting)
        || !dashboard.model.id.is_empty()
        || app.demo;
    let name = if dashboard.model.id.is_empty() {
        if app.demo {
            "Demo model".to_string()
        } else if connected {
            "Not reported".to_string()
        } else {
            "Connecting…".to_string()
        }
    } else {
        dashboard.model.display_name().to_string()
    };
    let name_style = if dashboard.model.id.is_empty() && !app.demo {
        Style::default().fg(theme.text_dim)
    } else {
        Style::default()
            .fg(theme.primary)
            .add_modifier(Modifier::BOLD)
    };

    let session = &dashboard.session;
    let mut rows: Vec<(&'static str, Line<'static>)> = Vec::new();
    rows.push((
        "name",
        Line::from(vec![
            Span::styled(
                format!("{} ", theme.glyph("◈", "*")),
                Style::default().fg(theme.primary),
            ),
            Span::styled(
                truncate(&name, inner.width.saturating_sub(2) as usize),
                name_style,
            ),
        ]),
    ));
    rows.push((
        "device",
        label(
            theme.glyph("▣", "D"),
            "Device",
            &device_label(dashboard),
            theme,
            inner.width as usize,
        ),
    ));
    rows.push((
        "context",
        label(
            theme.glyph("▦", "C"),
            "Context",
            &dashboard.model.context_label(),
            theme,
            inner.width as usize,
        ),
    ));
    rows.push((
        "mode",
        label(
            theme.glyph("◉", "M"),
            "Mode",
            dashboard.model.mode_label(),
            theme,
            inner.width as usize,
        ),
    ));
    rows.push((
        "web",
        label(
            theme.glyph("◍", "W"),
            "Web",
            &web_label(dashboard),
            theme,
            inner.width as usize,
        ),
    ));
    rows.push((
        "files",
        label(
            theme.glyph("▤", "F"),
            "Files Indexed",
            &session.files_indexed.to_string(),
            theme,
            inner.width as usize,
        ),
    ));
    rows.push((
        "docs",
        label(
            theme.glyph("▥", "D"),
            "Documents Created",
            &session.docs_created.to_string(),
            theme,
            inner.width as usize,
        ),
    ));
    rows.push((
        "policy",
        label(
            theme.glyph("⌁", "P"),
            "Policy Status",
            if session.policy_status.trim().is_empty() {
                "Unknown"
            } else {
                &session.policy_status
            },
            theme,
            inner.width as usize,
        ),
    ));
    let memory = if session.memory_limit == 0 {
        "Unavailable".to_string()
    } else {
        format!("{}/{} turns", session.memory_used, session.memory_limit)
    };
    rows.push((
        "memory",
        label(
            theme.glyph("⌂", "T"),
            "Memory",
            &memory,
            theme,
            inner.width as usize,
        ),
    ));

    let height = inner.height as usize;
    let mut keys: Vec<&str> = vec!["name", "device", "context", "mode", "web"];
    let mut include_session_header = height >= 12;
    keys.extend(["files", "docs", "policy", "memory"]);
    if height < 10 {
        keys.retain(|key| *key != "web");
    }
    if height < 9 {
        keys.retain(|key| *key != "context");
    }
    if height < 8 {
        keys.retain(|key| *key != "policy");
    }
    if height < 7 {
        include_session_header = false;
    }
    if height < 6 {
        keys.retain(|key| *key != "docs");
    }
    if height < 5 {
        keys.retain(|key| *key != "memory");
    }
    if height < 4 {
        keys.retain(|key| *key != "files");
    }

    let mut lines: Vec<Line<'static>> = Vec::new();
    for (key, line) in rows {
        if key == "files" && include_session_header {
            let title = "Session";
            let rule_width = inner.width as usize - width(title) - 3;
            lines.push(Line::from(vec![
                Span::styled(
                    format!("{title} "),
                    Style::default()
                        .fg(theme.secondary)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled("─".repeat(rule_width), Style::default().fg(theme.border)),
            ]));
        }
        if keys.contains(&key) {
            lines.push(line);
        }
    }
    if height >= 12 {
        lines.insert(0, Line::default());
    }

    let paragraph = Paragraph::new(Text::from(lines))
        .style(Style::default().fg(theme.text))
        .block(Block::default());
    frame.render_widget(paragraph, inner);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fixtures::demo_dashboard;

    #[test]
    fn gpu_name_is_condensed_without_inventing_a_model() {
        let mut dashboard = demo_dashboard();
        dashboard.telemetry.gpu.as_mut().unwrap().name =
            "NVIDIA GeForce RTX 4090 Laptop GPU".to_string();
        assert_eq!(device_label(&dashboard), "RTX 4090 (CUDA)");
        dashboard.telemetry.gpu = None;
        dashboard.model.device = "cpu".to_string();
        assert_eq!(device_label(&dashboard), "CPU");
    }

    #[test]
    fn missing_web_telemetry_is_not_called_online() {
        let mut dashboard = demo_dashboard();
        dashboard.telemetry.web.enabled = false;
        assert_eq!(web_label(&dashboard), "Disabled");
    }
}
