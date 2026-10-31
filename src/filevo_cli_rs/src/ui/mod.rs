//! Renderer orchestration.  This module owns geometry only: all state lives in
//! `app`, all backend I/O lives in `backend`, and each panel is a small module.

pub mod art;
pub mod conversation;
pub mod details;
pub mod documents;
pub mod header;
pub mod input;
pub mod layout;
pub mod model_session;
pub mod navigation;
pub mod references;
pub mod rlcd;
pub mod system_status;
pub mod text;
pub mod theme;

use crate::app::{App, ToastKind, View};
use crate::ui::layout::LayoutMode;
use crate::ui::theme::Theme;
use ratatui::Frame;
use ratatui::layout::{Alignment, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, Paragraph};

fn union_visible(rects: &[Rect]) -> Option<Rect> {
    let mut result: Option<Rect> = None;
    for rect in rects
        .iter()
        .copied()
        .filter(|rect| rect.width > 0 && rect.height > 0)
    {
        result = Some(match result {
            None => rect,
            Some(current) => {
                let x = current.x.min(rect.x);
                let y = current.y.min(rect.y);
                let right = (current.x + current.width).max(rect.x + rect.width);
                let bottom = (current.y + current.height).max(rect.y + rect.height);
                Rect {
                    x,
                    y,
                    width: right - x,
                    height: bottom - y,
                }
            }
        });
    }
    result
}

fn render_too_small(frame: &mut Frame, theme: &Theme, width: u16, height: u16) {
    let area = frame.area();
    let block = Block::default()
        .borders(ratatui::widgets::Borders::ALL)
        .border_type(theme.border_type())
        .border_style(Style::default().fg(theme.amber));
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let lines = vec![
        Line::from(Span::styled(
            "Terminal too small",
            Style::default()
                .fg(theme.amber)
                .add_modifier(Modifier::BOLD),
        )),
        Line::default(),
        Line::from(Span::styled(
            format!("Current size: {width}×{height} cells"),
            Style::default().fg(theme.text_dim),
        )),
        Line::from(Span::styled(
            "Filevo needs at least 60×20 cells.",
            Style::default().fg(theme.text_dim),
        )),
        Line::from(Span::styled(
            "Resize the window, or press Ctrl+Q to quit.",
            Style::default().fg(theme.muted),
        )),
    ];
    let block_height = lines.len() as u16;
    let y = inner.y + inner.height.saturating_sub(block_height) / 2;
    let rect = Rect {
        y,
        height: block_height.min(inner.height),
        ..inner
    };
    frame.render_widget(
        Paragraph::new(Text::from(lines)).alignment(Alignment::Center),
        rect,
    );
}

fn render_toast(frame: &mut Frame, app: &App, theme: &Theme, anchor: Rect) {
    let Some(toast) = app.active_toast() else {
        return;
    };
    if anchor.width < 12 || anchor.height < 4 {
        return;
    }
    let (colour, background) = match toast.kind {
        ToastKind::Info => (theme.text, theme.selection_bg),
        ToastKind::Success => (theme.green, theme.selection_bg),
        ToastKind::Warning => (theme.amber, theme.selection_bg),
        ToastKind::Error => (theme.red, theme.selection_bg),
    };
    let available = anchor.width.saturating_sub(4) as usize;
    let text = text::truncate(&toast.text, available);
    let width = (text::width(&text) + 4) as u16;
    let rect = Rect {
        x: anchor.x + anchor.width.saturating_sub(width + 1),
        y: anchor.y + anchor.height.saturating_sub(2),
        width,
        height: 1,
    };
    frame.render_widget(
        Paragraph::new(Line::from(Span::styled(
            format!(" {} ", text),
            Style::default()
                .fg(colour)
                .bg(background)
                .add_modifier(Modifier::BOLD),
        ))),
        rect,
    );
}

pub fn draw(frame: &mut Frame, app: &mut App) {
    let theme = theme::Theme::detect();
    let area = frame.area();
    frame.render_widget(Block::default().style(Style::default().bg(theme.bg)), area);
    let rects = layout::compute(area);
    app.last_layout = rects;
    let mode = rects.mode.unwrap_or(LayoutMode::TooSmall);
    if mode == LayoutMode::TooSmall {
        render_too_small(frame, &theme, area.width, area.height);
        return;
    }

    header::render(frame, rects.header, app.tick, &theme);
    if rects.model.width > 0 {
        model_session::render(frame, rects.model, app, &theme);
    }
    navigation::render(frame, rects.nav, app, &theme);

    let detail_area = if mode == LayoutMode::Compact {
        rects.conversation
    } else {
        union_visible(&[
            rects.conversation,
            rects.rlcd,
            rects.documents,
        ])
        .unwrap_or(rects.conversation)
    };

    if app.view != View::Home {
        let metrics = details::render(frame, detail_area, app, &theme);
        app.note_detail_metrics(metrics.max_scroll, metrics.viewport);
    } else {
        let metrics = conversation::render(frame, rects.conversation, app, &theme);
        app.note_conversation_metrics(metrics.top, metrics.max_top, metrics.viewport);
        if rects.rlcd.width > 0 {
            rlcd::render(frame, rects.rlcd, app, &theme);
        }
        if rects.documents.width > 0 {
            documents::render(frame, rects.documents, app, &theme);
        }
        render_toast(frame, app, &theme, rects.conversation);
    }

    input::render(
        frame,
        rects.prompt,
        rects.input,
        rects.shortcuts,
        app,
        &theme,
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app::App;
    use ratatui::Terminal;
    use ratatui::backend::TestBackend;
    use ratatui::buffer::Buffer;

    fn screen(app: &mut App, width: u16, height: u16) -> String {
        let backend = TestBackend::new(width, height);
        let mut terminal = Terminal::new(backend).expect("terminal");
        terminal
            .draw(|frame| draw(frame, app))
            .expect("draw should succeed");
        let buffer: &Buffer = terminal.backend().buffer();
        let area = buffer.area;
        let mut out = String::new();
        for y in 0..area.height {
            for x in 0..area.width {
                out.push_str(buffer[(x, y)].symbol());
            }
            out.push('\n');
        }
        out
    }

    #[test]
    fn spacious_demo_renders_clean_conversation_layout() {
        let mut app = App::new(true);
        let text = screen(&mut app, 180, 60);
        for expected in [
            "Model",
            "HOME",
            "CREATE",
            "ANALYZE",
            "TRAIN",
            "MODEL",
            "SETTINGS",
            "HELP",
            "Demo",
            "Type a message",
        ] {
            assert!(text.contains(expected), "missing {expected:?}\n{text}");
        }
        assert!(!text.contains("RLCD Decision"));
        assert!(!text.contains("Recent Documents"));
        assert!(app.last_viewport > 0);
    }

    #[test]
    fn standard_layout_keeps_conversation_visible() {
        let mut app = App::new(true);
        let text = screen(&mut app, 120, 40);
        for expected in [
            "Model",
            "C o n v e r s a t i o n a l",
        ] {
            assert!(text.contains(expected), "missing {expected:?}\n{text}");
        }
        assert!(!text.contains("RLCD Decision"));
        assert!(!text.contains("Recent Documents"));
    }

    #[test]
    fn compact_layout_prioritises_the_conversation() {
        let mut app = App::new(true);
        let text = screen(&mut app, 80, 24);
        assert!(text.contains("Filevo"));
        assert!(text.contains("HOME"));
        assert!(text.contains("Type a message"));
        assert!(!text.contains("RLCD Decision"));
    }

    #[test]
    fn too_small_prints_a_diagnostic_and_never_panics() {
        let mut app = App::new(true);
        let text = screen(&mut app, 42, 12);
        assert!(text.contains("Terminal too small"));
        assert!(text.contains("60×20"));
    }

    #[test]
    fn live_mode_hides_the_backend_prior() {
        let mut app = App::new(false);
        app.dashboard.decision = crate::model::Decision {
            available: false,
            values: [Some(0.12), Some(0.71), Some(0.08), Some(0.05), Some(0.04)],
            confidence: Some(0.713),
            entropy: Some(0.58),
            risk: crate::model::Risk::Low,
            source: "backend_default_prior".to_string(),
        };
        let text = screen(&mut app, 180, 60);
        assert!(!text.contains("RLCD Decision"));
        assert!(!text.contains("71.3%"));
        assert!(!text.contains("0.71"));
    }

    #[test]
    fn all_detail_views_render() {
        for view in [View::Model, View::Settings, View::Help] {
            let mut app = App::new(true);
            app.view = view;
            let text = screen(&mut app, 140, 46);
            assert!(!text.trim().is_empty());
            match view {
                View::Model => assert!(text.contains("Model Telemetry")),
                View::Settings => assert!(text.contains("Settings")),
                View::Help => assert!(text.contains("Command Reference")),
                View::Home => {}
            }
        }
    }
}
