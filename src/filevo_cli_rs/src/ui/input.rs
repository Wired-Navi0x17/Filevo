//! Prompt, input editor, completion popup and keyboard-shortcut legend.

use crate::app::{App, Focus, TaskState};
use crate::ui::text::{truncate, width};
use crate::ui::theme::Theme;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, Clear, Paragraph};
use ratatui::Frame;

const SPINNER: [&str; 8] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧"];

pub fn render(
    frame: &mut Frame,
    prompt: Rect,
    input: Rect,
    shortcuts: Rect,
    app: &App,
    theme: &Theme,
) {
    if prompt.width > 0 && prompt.height > 0 {
        let y = prompt.y + prompt.height / 2;
        let rect = Rect {
            x: prompt.x,
            y,
            width: prompt.width,
            height: 1,
        };
        frame.render_widget(
            Paragraph::new(Text::from(vec![Line::from(Span::styled(
                theme.prompt_icon(),
                Style::default()
                    .fg(theme.primary)
                    .add_modifier(Modifier::BOLD),
            ))]))
            .alignment(ratatui::layout::Alignment::Center),
            rect,
        );
    }

    if input.width >= 3 && input.height >= 3 {
        render_input(frame, input, app, theme);
    }
    if shortcuts.width >= 20 && shortcuts.height > 0 {
        render_shortcuts(frame, shortcuts, app, theme);
    }
}

fn render_input(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    let block = Block::default()
        .borders(ratatui::widgets::Borders::ALL)
        .border_type(theme.border_type())
        .border_style(Style::default().fg(if app.focus == Focus::Input {
            theme.border_focus
        } else {
            theme.border
        }))
        .style(Style::default().bg(theme.panel_bg));
    let inner = block.inner(area);
    frame.render_widget(block, area);
    if inner.width == 0 || inner.height == 0 {
        return;
    }
    let y = inner.y + inner.height / 2;
    let line_rect = Rect {
        y,
        height: 1,
        ..inner
    };

    if let TaskState::Running {
        label,
        started,
        cancelling,
    } = &app.task
    {
        let frame_char = if theme.unicode {
            SPINNER[(app.tick as usize) % SPINNER.len()]
        } else {
            "*"
        };
        let elapsed = started.elapsed().as_secs();
        let status = if *cancelling {
            "cancelling…".to_string()
        } else {
            format!("{label}… {elapsed}s · Ctrl+C to cancel")
        };
        let text = format!("{frame_char} {status}");
        frame.render_widget(
            Paragraph::new(Line::from(vec![
                Span::styled(
                    format!("{frame_char} "),
                    Style::default().fg(theme.primary),
                ),
                Span::styled(
                    truncate(&text[frame_char.len_utf8() + 1..], inner.width as usize),
                    Style::default().fg(theme.amber),
                ),
            ])),
            line_rect,
        );
        return;
    }

    if app.input.is_empty() {
        let placeholder = "Type a message or /command...";
        frame.render_widget(
            Paragraph::new(Line::from(Span::styled(
                truncate(placeholder, inner.width as usize),
                Style::default().fg(theme.muted),
            ))),
            line_rect,
        );
    } else {
        let (visible, _) = app.visible_window(inner.width as usize);
        frame.render_widget(
            Paragraph::new(Line::from(Span::styled(
                visible,
                Style::default().fg(theme.text),
            ))),
            line_rect,
        );
    }

    if app.focus == Focus::Input {
        let (visible, cursor_cells) = app.visible_window(inner.width as usize);
        let _ = visible;
        let max_x = inner.x + inner.width.saturating_sub(1);
        let cursor_x = (inner.x + cursor_cells as u16).min(max_x);
        frame.set_cursor_position((cursor_x, y));
    }

    if let Some(menu) = &app.input.completion {
        if !menu.items.is_empty() {
            render_completion(frame, frame.area(), area, app, theme);
        }
    }
}

fn render_completion(
    frame: &mut Frame,
    screen: Rect,
    input: Rect,
    app: &App,
    theme: &Theme,
) {
    let Some(menu) = &app.input.completion else {
        return;
    };
    let widest = menu
        .items
        .iter()
        .map(|item| width(item))
        .max()
        .unwrap_or(10);
    let popup_width = (widest as u16 + 6).min(screen.width).max(12);
    let max_height = input.y.saturating_sub(screen.y).max(0);
    let desired_height = menu.items.len() as u16 + 2;
    let height = desired_height.min(max_height).max(3);
    if max_height < 3 {
        return;
    }
    let x = input.x.min(screen.x + screen.width.saturating_sub(popup_width));
    let y = input.y.saturating_sub(height);
    let popup = Rect {
        x,
        y,
        width: popup_width,
        height,
    };
    frame.render_widget(Clear, popup);
    let block = theme
        .panel()
        .title(Span::styled(" Commands ", Style::default().fg(theme.primary)));
    let inner = block.inner(popup);
    frame.render_widget(block, popup);
    if inner.height == 0 {
        return;
    }
    let visible = inner.height as usize;
    let start = if menu.selected >= visible {
        menu.selected + 1 - visible
    } else {
        0
    };
    let lines: Vec<Line<'static>> = menu
        .items
        .iter()
        .enumerate()
        .skip(start)
        .take(visible)
        .map(|(index, item)| {
            let selected = index == menu.selected;
            Line::from(Span::styled(
                format!(
                    " {} ",
                    truncate(item, inner.width.saturating_sub(2) as usize)
                ),
                if selected {
                    Style::default()
                        .bg(theme.primary)
                        .fg(theme.bg)
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(theme.text)
                },
            ))
        })
        .collect();
    frame.render_widget(Paragraph::new(Text::from(lines)), inner);
}

fn render_shortcuts(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    let compact = area.width < 55;
    let parts: Vec<(&str, &str)> = if app.task.is_running() {
        vec![("Ctrl+C", "Cancel"), ("Ctrl+Q", "Quit")]
    } else if compact {
        vec![("Enter", "Send"), ("Tab", "Complete"), ("^C", "Cancel")]
    } else {
        vec![
            ("Enter", "Send"),
            ("Tab", "Autocomplete"),
            ("Ctrl+C", "Cancel"),
        ]
    };
    let mut spans: Vec<Span<'static>> = Vec::new();
    for (index, (key, label)) in parts.iter().enumerate() {
        if index > 0 {
            spans.push(Span::styled("   ", Style::default()));
        }
        spans.push(Span::styled(
            (*key).to_string(),
            Style::default()
                .fg(theme.text)
                .add_modifier(Modifier::BOLD),
        ));
        spans.push(Span::styled(
            format!(": {label}"),
            Style::default().fg(theme.text_dim),
        ));
    }
    let line = Line::from(spans);
    let text_width = width(&line.to_string());
    if text_width > area.width as usize {
        return;
    }
    let y = area.y + area.height.saturating_sub(1) / 2;
    frame.render_widget(
        Paragraph::new(Text::from(vec![line])),
        Rect { y, height: 1, ..area },
    );
}
