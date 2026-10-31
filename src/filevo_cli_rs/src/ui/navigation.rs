//! Navigation bar.  The eight labels are part of the product contract and are
//! never abbreviated; at very narrow widths the separators collapse instead.

use crate::app::{App, BackendState, Focus, NavTab};
use crate::ui::text::width;
use crate::ui::theme::Theme;
use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::Paragraph;

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

    let mut spans: Vec<Span<'static>> = Vec::new();
    spans.push(Span::raw(" "));
    for (index, tab) in NavTab::ALL.iter().enumerate() {
        if index > 0 {
            spans.push(Span::styled("│", Style::default().fg(theme.border)));
        }
        let active = *tab == app.active_tab;
        let selected = app.focus == Focus::Navigation && app.nav_selected == *tab && !active;

        let mut text = String::new();
        if *tab == NavTab::Home {
            text.push_str(theme.home_icon());
            text.push(' ');
        }
        text.push_str(tab.label());

        let button_text = format!(" {text} ");

        let style = if active {
            Style::default()
                .bg(theme.primary)
                .fg(theme.bg)
                .add_modifier(Modifier::BOLD)
        } else if selected {
            Style::default()
                .bg(theme.selection_bg)
                .fg(theme.primary)
                .add_modifier(Modifier::BOLD | Modifier::UNDERLINED)
        } else {
            Style::default()
                .bg(theme.panel_bg)
                .fg(theme.secondary)
                .add_modifier(Modifier::BOLD)
        };

        spans.push(Span::styled(button_text, style));
    }

    let line = Line::from(spans);
    // Vertically centre the single line in the two-row navigation band.
    let y = area.y + area.height.saturating_sub(1) / 2;
    let nav_rect = Rect {
        y,
        height: 1,
        ..nav_area
    };
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

/// Precise geometry slot for a navigation tab button.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TabSlot {
    pub tab: NavTab,
    pub start_x: u16,
    pub end_x: u16,
}

/// Calculate the exact rendered column width for a tab button pill (`" {text} "`).
#[inline]
pub fn tab_button_width(tab: NavTab) -> u16 {
    let label_len = tab.label().len() as u16;
    if tab == NavTab::Home {
        // " ⌂ HOME " -> 1 (space) + 1 (icon) + 1 (space) + 4 (HOME) + 1 (space) = 8
        label_len + 4
    } else {
        // " LABEL " -> 1 (space) + label + 1 (space)
        label_len + 2
    }
}

/// Computes the exact screen coordinate hitboxes for all navigation buttons.
/// Both `render` and `nav_tab_at` share this single source of truth.
pub fn compute_tab_slots(nav_x: u16) -> [TabSlot; NavTab::ALL.len()] {
    let mut slots = [TabSlot {
        tab: NavTab::Home,
        start_x: 0,
        end_x: 0,
    }; NavTab::ALL.len()];

    let mut current_x = nav_x + 1; // 1 space margin on the left
    let all = NavTab::ALL;
    for (i, &tab) in all.iter().enumerate() {
        let btn_w = tab_button_width(tab);
        let start_x = if i == 0 { nav_x } else { current_x }; // expand first button to left margin
        let end_x = if i + 1 < all.len() {
            current_x + btn_w // covers button plus separator boundary to eliminate dead zones
        } else {
            current_x + btn_w + 3 // generous right boundary for last button (HELP)
        };
        slots[i] = TabSlot {
            tab,
            start_x,
            end_x,
        };
        current_x = current_x + btn_w + 1; // +1 for the separator "│"
    }
    slots
}

/// Finds which navigation button was clicked, with generous zero-deadzone hitboxes.
pub fn nav_tab_at(x: u16, nav_area: Rect) -> Option<NavTab> {
    if x < nav_area.x {
        return None;
    }
    let slots = compute_tab_slots(nav_area.x);
    for slot in &slots {
        if x >= slot.start_x && x <= slot.end_x {
            return Some(slot.tab);
        }
    }
    None
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
                "HOME", "CREATE", "ANALYZE", "TRAIN", "MODEL", "SETTINGS", "HELP"
            ]
        );
    }

    #[test]
    fn every_tab_is_clickable_at_its_rendered_position() {
        let nav_area = Rect {
            x: 1,
            y: 8,
            width: 120,
            height: 2,
        };
        let slots = compute_tab_slots(nav_area.x);
        for slot in &slots {
            // Click right at the start of the button
            assert_eq!(
                nav_tab_at(slot.start_x, nav_area),
                Some(slot.tab),
                "Failed clicking start of {:?}",
                slot.tab
            );
            // Click right at the middle of the button
            let mid = (slot.start_x + slot.end_x) / 2;
            assert_eq!(
                nav_tab_at(mid, nav_area),
                Some(slot.tab),
                "Failed clicking middle of {:?}",
                slot.tab
            );
            // Click right at the end of the button
            assert_eq!(
                nav_tab_at(slot.end_x, nav_area),
                Some(slot.tab),
                "Failed clicking end of {:?}",
                slot.tab
            );
        }
    }

    #[test]
    fn click_coverage_has_no_dead_zones() {
        let nav_area = Rect {
            x: 1,
            y: 8,
            width: 120,
            height: 2,
        };
        let slots = compute_tab_slots(nav_area.x);
        let max_x = slots.last().unwrap().end_x;
        for x in nav_area.x..=max_x {
            assert!(
                nav_tab_at(x, nav_area).is_some(),
                "Dead zone found at x = {x}"
            );
        }
    }
}
