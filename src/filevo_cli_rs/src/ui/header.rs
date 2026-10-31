//! Header: the FILEVO wordmark and deterministic landscape.

use crate::ui::art;
use crate::ui::theme::Theme;
use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::text::Text;
use ratatui::widgets::Paragraph;

pub fn render(frame: &mut Frame, area: Rect, tick: u64, theme: &Theme) {
    if area.width < 3 || area.height < 2 {
        return;
    }
    let inner = theme.panel().inner(area);
    frame.render_widget(theme.panel(), area);
    let lines = art::header_lines(inner.width as usize, inner.height as usize, tick, theme);
    frame.render_widget(Paragraph::new(Text::from(lines)), inner);
}
