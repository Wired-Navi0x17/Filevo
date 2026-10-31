//! Recent generated-document table.  Sizes and timestamps are real filesystem
//! metadata forwarded by the daemon.

use crate::app::{App, Focus};
use crate::model::{format_epoch_document, format_size};
use crate::ui::text::{spaces, truncate, width};
use crate::ui::theme::Theme;
use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::Paragraph;

fn push_row(
    lines: &mut Vec<Line<'static>>,
    index: usize,
    document: &crate::model::DocumentInfo,
    selected: bool,
    inner_width: usize,
    theme: &Theme,
) {
    let show_date = inner_width >= 64;
    let show_size = inner_width >= 42;
    let date_width = 16;
    let size_width = 8;
    let mut reserved = 0;
    if show_date {
        reserved += date_width + 2;
    }
    if show_size {
        reserved += size_width + 1;
    }
    let prefix = format!(" {} {:>2}. ", theme.glyph("▤", "D"), index + 1);
    let prefix_width = width(&prefix);
    let name_width = inner_width.saturating_sub(prefix_width + reserved).max(8);
    let name = truncate(&document.name, name_width);
    let row_bg = if selected {
        Style::default().bg(theme.selection_bg)
    } else {
        Style::default()
    };
    let mut spans = vec![
        Span::styled(
            prefix,
            Style::default()
                .fg(if selected {
                    theme.primary
                } else {
                    theme.secondary
                })
                .bg(if selected {
                    theme.selection_bg
                } else {
                    theme.panel_bg
                }),
        ),
        Span::styled(
            name.clone(),
            row_bg.fg(theme.text).add_modifier(if selected {
                Modifier::BOLD
            } else {
                Modifier::empty()
            }),
        ),
    ];
    let used = prefix_width + width(&name);
    let mut gap = inner_width.saturating_sub(used + reserved);
    if show_size {
        spans.push(Span::styled(spaces(gap + 1), row_bg));
        spans.push(Span::styled(
            format!(
                "{:>width$}",
                format_size(document.size_bytes),
                width = size_width
            ),
            row_bg.fg(theme.text_dim),
        ));
        gap = 0;
    }
    if show_date {
        spans.push(Span::styled(spaces(gap + 2), row_bg));
        spans.push(Span::styled(
            format_epoch_document(document.modified),
            row_bg.fg(theme.muted),
        ));
    }
    lines.push(Line::from(spans));
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    if area.width < 8 || area.height < 2 {
        return;
    }
    let count = app.dashboard.documents.len();
    let block = if app.focus == Focus::Documents {
        theme.focused_panel()
    } else {
        theme.panel()
    }
    .title(Span::styled(
        format!("{} Recent Documents ", theme.glyph("▤", "D")),
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
            "No generated documents",
            Style::default().fg(theme.text_dim),
        )));
        if inner_height >= 2 {
            lines.push(Line::from(Span::styled(
                "/create <topic> generates a Word document.",
                Style::default().fg(theme.muted),
            )));
        }
    } else {
        let visible = inner_height.max(1).min(count);
        let selected = app.doc_selected.min(count.saturating_sub(1));
        let start = if selected < visible {
            0
        } else {
            selected + 1 - visible
        };
        for (offset, document) in app
            .dashboard
            .documents
            .iter()
            .enumerate()
            .skip(start)
            .take(visible)
        {
            push_row(
                &mut lines,
                offset,
                document,
                app.focus == Focus::Documents && offset == selected,
                inner_width,
                theme,
            );
        }
        let remaining = count.saturating_sub(start + visible);
        if remaining > 0 && lines.len() < inner_height {
            lines.push(Line::from(Span::styled(
                format!("  … {remaining} more"),
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
