//! Web reference panel.  Only real daemon references are shown; an empty
//! session explains how to obtain one rather than inventing links.

use crate::app::{App, Focus};
use crate::model::ReferenceInfo;
use crate::ui::text::{truncate, wrap};
use crate::ui::theme::Theme;
use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::Paragraph;

fn marker(index: usize, theme: &Theme) -> String {
    if theme.unicode && index < 20 {
        char::from_u32(0x2460 + index as u32)
            .map(|ch| ch.to_string())
            .unwrap_or_else(|| format!("[{}]", index + 1))
    } else {
        format!("[{}]", index + 1)
    }
}

fn push_reference(
    lines: &mut Vec<Line<'static>>,
    index: usize,
    reference: &ReferenceInfo,
    selected: bool,
    inner_width: usize,
    theme: &Theme,
) {
    let number = marker(index, theme);
    let prefix_width = 1 + number.chars().count() + 1;
    let title_budget = inner_width.saturating_sub(prefix_width).max(4);
    let title_style = if selected {
        Style::default()
            .bg(theme.selection_bg)
            .fg(theme.text)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(theme.text)
    };
    lines.push(Line::from(vec![
        Span::styled(" ", Style::default()),
        Span::styled(
            number,
            Style::default()
                .fg(if selected {
                    theme.primary
                } else {
                    theme.secondary
                })
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" ", Style::default()),
        Span::styled(truncate(&reference.title, title_budget), title_style),
    ]));
    lines.push(Line::from(vec![
        Span::styled(" ".repeat(prefix_width), Style::default()),
        Span::styled(
            truncate(
                &reference.domain,
                inner_width.saturating_sub(prefix_width).max(4),
            ),
            Style::default().fg(if selected {
                theme.primary
            } else {
                theme.text_dim
            }),
        ),
    ]));
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    if area.width < 8 || area.height < 2 {
        return;
    }
    let count = app.dashboard.references.len();
    let title = format!("{} References ({count}) ", theme.glyph("◈", "*"));
    let block = theme.panel().title(Span::styled(
        title,
        Style::default()
            .fg(theme.primary)
            .add_modifier(Modifier::BOLD),
    ));
    let inner = block.inner(area);
    frame.render_widget(block, area);
    if inner.width == 0 || inner.height == 0 {
        return;
    }
    let inner_width = inner.width as usize;
    let inner_height = inner.height as usize;
    let mut lines: Vec<Line<'static>> = Vec::new();

    if count == 0 {
        lines.push(Line::from(Span::styled(
            "No live references",
            Style::default().fg(theme.text_dim),
        )));
        if inner_height >= 3 {
            for line in wrap(
                "Use /research <topic> to ground a response in live sources.",
                inner_width,
            ) {
                lines.push(Line::from(Span::styled(
                    line,
                    Style::default().fg(theme.muted),
                )));
            }
        }
    } else {
        let compact = inner_height < count.saturating_mul(3)
            && inner_height >= count.saturating_mul(2).max(2);
        let slot = if compact { 2 } else { 3 };
        let visible = ((inner_height + slot - 1) / slot).max(1).min(count);
        let selected = app.ref_selected.min(count.saturating_sub(1));
        let start = if selected < visible {
            0
        } else {
            selected + 1 - visible
        };
        for (offset, reference) in app
            .dashboard
            .references
            .iter()
            .enumerate()
            .skip(start)
            .take(visible)
        {
            if !lines.is_empty() && !compact {
                lines.push(Line::default());
            }
            push_reference(
                &mut lines,
                offset,
                reference,
                false,
                inner_width,
                theme,
            );
        }
        let remaining = count.saturating_sub(start + visible);
        if remaining > 0 && lines.len() < inner_height {
            lines.push(Line::from(Span::styled(
                format!("  {remaining} more below"),
                Style::default().fg(theme.muted),
            )));
        }
    }

    lines.truncate(inner_height);
    frame.render_widget(
        Paragraph::new(Text::from(lines)).style(Style::default().bg(theme.panel_bg)),
        inner,
    );
}
