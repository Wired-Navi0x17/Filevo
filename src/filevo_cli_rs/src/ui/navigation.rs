//! Navigation bar.  The eight labels are part of the product contract and are
//! never abbreviated; at very narrow widths the separators collapse instead.

use crate::app::{App, BackendState, Focus, NavTab};
use crate::ui::text::width;
use crate::ui::theme::Theme;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

fn backend_span(app: &App, theme: &Theme) -> Span<'static> {
    let (dot, label, colour) = match &app.backend {
        BackendState::Demo => ("●", "Demo", theme.amber),
        BackendState::Connecting => ("◌", "Connecting", theme.amber),
        BackendState::Online => ("●", "Live", theme.green),
        BackendState::Offline(_) => ("●", "Offline", theme.red),
    };
    Span::styled(
        format!("{dot} {label}"),
        Style::default().fg(colour).add_modifier(Modifier::BOLD),
    )
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    if area.width == 0 || area.height == 0 {
        return;
    }

    let status = backend_span(app, theme);
    let status_width = width(&status.content) + 1;
    let show_status = area.width as usize >= 108;
    let nav_area = if show_status {
        Rect {
            width: area.width.saturating_sub(status_width as u16 + 1),
            ..area
        }
    } else {
        area
    };

    let compact = (nav_area.width as usize) < 78;
    let separator = if compact { " " } else { " │ " };
    let mut spans: Vec<Span<'static>> = Vec::new();
    spans.push(Span::raw(" "));
    for (index, tab) in NavTab::ALL.iter().enumerate() {
        if index > 0 {
            spans.push(Span::styled(separator, Style::default().fg(theme.border)));
        }
        let active = *tab == app.active_tab;
        let selected =
            app.focus == Focus::Navigation && app.nav_selected == *tab && !active;
        if active {
            let mut text = String::new();
            if *tab == NavTab::Home {
                text.push_str(theme.home_icon());
                text.push(' ');
            }
            text.push_str(tab.label());
            spans.push(Span::styled(
                format!(" {text} "),
                Style::default()
                    .bg(theme.primary)
                    .fg(theme.bg)
                    .add_modifier(Modifier::BOLD),
            ));
        } else {
            let style = if selected {
                Style::default()
                    .fg(theme.primary)
                    .add_modifier(Modifier::BOLD | Modifier::UNDERLINED)
            } else {
                Style::default()
                    .fg(theme.secondary)
                    .add_modifier(Modifier::BOLD)
            };
            let mut text = String::new();
            if *tab == NavTab::Home {
                text.push_str(theme.home_icon());
                text.push(' ');
            }
            text.push_str(tab.label());
            spans.push(Span::styled(text, style));
        }
    }

    let line = Line::from(spans);
    // Vertically centre the single line in the two-row navigation band.
    let y = area.y + area.height.saturating_sub(1) / 2;
    let nav_rect = Rect { y, height: 1, ..nav_area };
    frame.render_widget(
        Paragraph::new(Text::from(vec![line])).style(Style::default().bg(theme.bg)),
        nav_rect,
    );

    if show_status {
        let status_rect = Rect {
            x: area.x + area.width.saturating_sub(status_width as u16),
            y,
            width: status_width as u16,
            height: 1,
        };
        frame.render_widget(
            Paragraph::new(Text::from(vec![Line::from(vec![status])])),
            status_rect,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_label_is_present() {
        let labels: Vec<&str> = NavTab::ALL.iter().map(|tab| tab.label()).collect();
        assert_eq!(
            labels,
            vec![
                "HOME", "CREATE", "ANALYZE", "INDEX", "TRAIN", "MODEL", "STATUS", "HELP"
            ]
        );
    }

    #[test]
    fn layout_preserves_the_nav_band() {
        let _ = Layout::default()
            .constraints([Constraint::Length(1)])
            .split(Rect::new(0, 0, 80, 1));
    }
}
