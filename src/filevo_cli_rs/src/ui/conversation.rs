//! Conversation panel with measured word wrapping and scroll offsets.
//!
//! The panel builds every visual line before rendering so the application can
//! remember an exact `max_top` for PageUp/PageDown and for preserving the
//! reading position when a new reply arrives.

use crate::app::App;
use crate::model::{Message, Role};
use crate::ui::art::{owl_width, OWL};
use crate::ui::text::{spaces, truncate, width, wrap};
use crate::ui::theme::Theme;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

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
    let body_gutter = if inner_width >= 72 {
        owl_width() + 2
    } else {
        2
    };

    let mut lines: Vec<Line<'static>> = Vec::new();
    if app.messages.is_empty() {
        lines.push(Line::default());
        lines.push(Line::from(vec![
            Span::styled("  ", Style::default()),
            Span::styled(
                theme.glyph("❯", ">"),
                Style::default().fg(theme.primary).add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                " No conversation yet",
                Style::default()
                    .fg(theme.text)
                    .add_modifier(Modifier::BOLD),
            ),
        ]));
        lines.push(Line::from(Span::styled(
            "    Type a message or a /command below.",
            Style::default().fg(theme.text_dim),
        )));
        if !app.demo {
            lines.push(Line::from(Span::styled(
                "    Connecting to the Filevo daemon…",
                Style::default().fg(theme.muted),
            )));
        }
    } else {
        for (index, message) in app.messages.iter().enumerate() {
            if index > 0 {
                lines.push(Line::default());
            }
            push_message(&mut lines, message, inner_width, body_gutter, theme);
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

    let paragraph = Paragraph::new(Text::from(lines)).scroll((
        top.min(u16::MAX as usize) as u16,
        0,
    ));
    frame.render_widget(paragraph, inner);

    Metrics {
        top,
        max_top,
        viewport,
    }
}

fn push_message(
    lines: &mut Vec<Line<'static>>,
    message: &Message,
    inner_width: usize,
    body_gutter: usize,
    theme: &Theme,
) {
    let (name, marker, role_style) = match (message.role, message.is_error) {
        (Role::User, _) => (
            "You",
            theme.glyph("❯", ">"),
            Style::default()
                .fg(theme.text)
                .add_modifier(Modifier::BOLD),
        ),
        (Role::Assistant, false) => (
            "Filevo",
            theme.glyph("❯", ">"),
            Style::default()
                .fg(theme.primary)
                .add_modifier(Modifier::BOLD),
        ),
        (Role::Assistant, true) => (
            "Filevo",
            "!",
            Style::default()
                .fg(theme.red)
                .add_modifier(Modifier::BOLD),
        ),
        (Role::System, _) => (
            "System",
            theme.glyph("◈", "*"),
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

    let body_width = inner_width.saturating_sub(body_gutter).max(8);
    let body_style = if message.is_error {
        Style::default().fg(theme.red)
    } else if message.role == Role::System {
        Style::default().fg(theme.amber)
    } else {
        Style::default().fg(theme.text)
    };
    let body = wrap(&message.content, body_width);
    let show_owl = message.role == Role::Assistant && body_gutter > 2;
    for (row, text) in body.iter().enumerate() {
        let mut spans: Vec<Span<'static>> = Vec::new();
        if show_owl && row < OWL.len() {
            spans.push(Span::styled(
                format!(" {}", OWL[row]),
                Style::default()
                    .fg(theme.primary)
                    .add_modifier(Modifier::DIM),
            ));
            let owl_used = 1 + owl_width();
            if body_gutter > owl_used {
                spans.push(Span::raw(spaces(body_gutter - owl_used)));
            }
        } else {
            spans.push(Span::raw(spaces(body_gutter)));
        }
        spans.push(Span::styled(
            truncate(text, body_width),
            body_style,
        ));
        lines.push(Line::from(spans));
    }
}
