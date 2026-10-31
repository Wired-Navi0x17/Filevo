use crate::app::App;
use crate::model::{Message, Role};
use crate::ui::art::{activity_ticker, cat_animation_lines, pulse_wave};
use crate::ui::text::{spaces, truncate, width, wrap};
use crate::ui::theme::Theme;
use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::Paragraph;

#[derive(Debug, Clone, Copy, Default)]
pub struct Metrics {
    pub top: usize,
    pub max_top: usize,
    pub viewport: usize,
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) -> Metrics {
    if area.width < 4 || area.height < 3 {
        return Metrics::default();
    }
    let block = if app.focus == crate::app::Focus::Conversation {
        theme.focused_panel()
    } else {
        theme.panel()
    };
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let inner_width = inner.width as usize;

    let mut lines: Vec<Line<'static>> = Vec::new();
    if app.messages.is_empty() {
        render_welcome_state(&mut lines, inner_width, inner.height as usize, app.tick, theme);
    } else {
        for (index, message) in app.messages.iter().enumerate() {
            if index > 0 {
                lines.push(Line::default());
            }
            push_message(&mut lines, message, inner_width, theme);
        }
    }

    let viewport = inner.height as usize;
    let total = lines.len();
    let max_top = total.saturating_sub(viewport);
    let top = if app.follow_tail {
        max_top
    } else {
        app.scroll_top.min(max_top)
    };

    let paragraph =
        Paragraph::new(Text::from(lines)).scroll((top.min(u16::MAX as usize) as u16, 0));
    frame.render_widget(paragraph, inner);

    Metrics {
        top,
        max_top,
        viewport,
    }
}

fn render_welcome_state(
    lines: &mut Vec<Line<'static>>,
    inner_width: usize,
    viewport_height: usize,
    tick: u64,
    theme: &Theme,
) {
    let show_cat = inner_width >= 40 && viewport_height >= 18;
    let top_pad = if show_cat {
        (viewport_height.saturating_sub(26) / 3).min(2)
    } else {
        (viewport_height.saturating_sub(12) / 3).min(4)
    };
    for _ in 0..top_pad {
        lines.push(Line::default());
    }

    if show_cat {
        let cat = cat_animation_lines(tick, theme);
        lines.extend(cat);
        lines.push(Line::default());
    } else {
        let wave_width = inner_width.saturating_sub(10).min(42);
        let wave = pulse_wave(tick, wave_width);
        lines.push(Line::from(vec![
            Span::raw("   "),
            Span::styled(wave, Style::default().fg(theme.primary)),
            Span::styled(
                format!(" {}", activity_ticker(tick)),
                Style::default().fg(theme.secondary),
            ),
        ]));
        lines.push(Line::default());
    }

    lines.push(Line::from(vec![
        Span::raw("   "),
        Span::styled(
            "✦ Filevo Intelligence Online",
            Style::default()
                .fg(theme.text)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" · RLCD Policy Active", Style::default().fg(theme.text_dim)),
    ]));
    lines.push(Line::from(vec![
        Span::raw("   "),
        Span::styled(
            "Author professional Word documents via ArtCraft WordCraft with zero AI slop.",
            Style::default().fg(theme.text_dim),
        ),
    ]));
    lines.push(Line::default());

    let shortcuts = [
        ("/create <topic>", "Generate complete DOCX, PDF & visual preview"),
        ("/create --live <topic>", "Watch live composition in WordCraft desktop"),
        ("/train @sample.docx", "Adapt RLCD policy and structure from file"),
        ("/wordcraft status", "Inspect WordCraft MCP server connection & tools"),
    ];

    for (cmd, desc) in shortcuts {
        lines.push(Line::from(vec![
            Span::raw("   "),
            Span::styled(
                format!("{:<26}", cmd),
                Style::default()
                    .fg(theme.primary)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(desc, Style::default().fg(theme.muted)),
        ]));
    }
}

fn push_message(
    lines: &mut Vec<Line<'static>>,
    message: &Message,
    inner_width: usize,
    theme: &Theme,
) {
    let (name, marker, role_style) = match (message.role, message.is_error) {
        (Role::User, _) => (
            "You",
            theme.glyph("❯", ">"),
            Style::default().fg(theme.text).add_modifier(Modifier::BOLD),
        ),
        (Role::Assistant, false) => (
            "Filevo",
            theme.glyph("◈", "*"),
            Style::default()
                .fg(theme.primary)
                .add_modifier(Modifier::BOLD),
        ),
        (Role::Assistant, true) => (
            "Filevo",
            "!",
            Style::default().fg(theme.red).add_modifier(Modifier::BOLD),
        ),
        (Role::System, _) => (
            "System",
            theme.glyph("⚙", "*"),
            Style::default()
                .fg(theme.amber)
                .add_modifier(Modifier::BOLD),
        ),
    };
    let marker_colour = match (message.role, message.is_error) {
        (Role::Assistant, true) => theme.red,
        (Role::System, _) => theme.amber,
        _ => theme.primary,
    };

    let left_width = 2 + width(marker) + 1 + width(name);
    let timestamp = message.timestamp.as_str();
    let timestamp_width = width(timestamp);
    let gap = inner_width.saturating_sub(left_width + timestamp_width + 1);
    let mut header = vec![
        Span::styled(" ", Style::default()),
        Span::styled(marker.to_string(), Style::default().fg(marker_colour)),
        Span::styled(" ", Style::default()),
        Span::styled(name.to_string(), role_style),
    ];
    if gap > 0 && timestamp_width > 0 {
        header.push(Span::styled(
            spaces(gap),
            Style::default().fg(theme.text_dim),
        ));
        header.push(Span::styled(
            timestamp.to_string(),
            Style::default().fg(theme.muted),
        ));
    }
    lines.push(Line::from(header));

    let body_indent = 4;
    let body_width = inner_width.saturating_sub(body_indent + 1).max(10);
    let body_style = if message.is_error {
        Style::default().fg(theme.red)
    } else if message.role == Role::System {
        Style::default().fg(theme.amber)
    } else {
        Style::default().fg(theme.text)
    };

    let body = wrap(&message.content, body_width);
    for row in 0..body.len() {
        let text = body.get(row).map(|s| s.as_str()).unwrap_or("");
        let mut spans: Vec<Span<'static>> = Vec::new();
        if message.role == Role::Assistant {
            spans.push(Span::styled("  │ ", Style::default().fg(theme.border_focus)));
        } else {
            spans.push(Span::raw(spaces(body_indent)));
        }
        if !text.is_empty() {
            spans.push(Span::styled(truncate(text, body_width), body_style));
        }
        lines.push(Line::from(spans));
    }
}
