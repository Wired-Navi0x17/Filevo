//! Centralised palette and terminal-capability fallbacks.

use ratatui::style::{Color, Modifier, Style};
use ratatui::widgets::{Block, BorderType, Borders};
use std::env;

#[derive(Debug, Clone)]
pub struct Theme {
    pub bg: Color,
    pub panel_bg: Color,
    pub border: Color,
    pub border_focus: Color,
    pub primary: Color,
    pub secondary: Color,
    pub muted: Color,
    pub text: Color,
    pub text_dim: Color,
    pub green: Color,
    pub amber: Color,
    pub red: Color,
    pub selection_bg: Color,
    pub unicode: bool,
    pub colour: bool,
}

impl Default for Theme {
    fn default() -> Self {
        Self::detect()
    }
}

impl Theme {
    pub fn detect() -> Self {
        let unicode = env::var("FILEVO_ASCII").map(|v| v != "1").unwrap_or(true);
        let colour = env::var_os("NO_COLOR").is_none();
        let mut theme = Self {
            bg: Color::Rgb(2, 10, 16),
            panel_bg: Color::Rgb(4, 18, 27),
            border: Color::Rgb(14, 124, 140),
            border_focus: Color::Rgb(0, 213, 238),
            primary: Color::Rgb(0, 213, 238),
            secondary: Color::Rgb(23, 201, 231),
            muted: Color::Rgb(54, 134, 169),
            text: Color::Rgb(195, 216, 231),
            text_dim: Color::Rgb(119, 157, 181),
            green: Color::Rgb(0, 220, 163),
            amber: Color::Rgb(218, 184, 74),
            red: Color::Rgb(255, 100, 124),
            selection_bg: Color::Rgb(6, 56, 70),
            unicode,
            colour,
        };
        if !colour {
            theme.bg = Color::Reset;
            theme.panel_bg = Color::Reset;
            theme.border = Color::Reset;
            theme.border_focus = Color::Reset;
            theme.primary = Color::Reset;
            theme.secondary = Color::Reset;
            theme.muted = Color::Reset;
            theme.text = Color::Reset;
            theme.text_dim = Color::Reset;
            theme.green = Color::Reset;
            theme.amber = Color::Reset;
            theme.red = Color::Reset;
            theme.selection_bg = Color::Reset;
        }
        theme
    }

    pub fn border_type(&self) -> BorderType {
        if self.unicode {
            BorderType::Rounded
        } else {
            BorderType::Plain
        }
    }

    pub fn panel(&self) -> Block<'static> {
        Block::default()
            .borders(Borders::ALL)
            .border_type(self.border_type())
            .border_style(Style::default().fg(self.border))
            .style(Style::default().bg(self.panel_bg))
    }

    pub fn focused_panel(&self) -> Block<'static> {
        Block::default()
            .borders(Borders::ALL)
            .border_type(self.border_type())
            .border_style(Style::default().fg(self.border_focus))
            .style(Style::default().bg(self.panel_bg))
    }

    pub fn gauge_fill(&self) -> char {
        if self.unicode { '█' } else { '#' }
    }

    pub fn gauge_empty(&self) -> char {
        if self.unicode { '░' } else { '-' }
    }

    pub fn bullet(&self) -> &'static str {
        if self.unicode { "▪" } else { "*" }
    }

    pub fn diamond(&self) -> &'static str {
        if self.unicode { "◈" } else { "+" }
    }

    pub fn home_icon(&self) -> &'static str {
        if self.unicode { "⌂" } else { "H" }
    }

    pub fn doc_icon(&self) -> &'static str {
        if self.unicode { "▤" } else { "D" }
    }

    pub fn globe_icon(&self) -> &'static str {
        if self.unicode { "◍" } else { "@" }
    }

    pub fn gear_icon(&self) -> &'static str {
        if self.unicode { "⚙" } else { "*" }
    }

    pub fn prompt_icon(&self) -> &'static str {
        if self.unicode { "❯" } else { ">" }
    }

    pub fn arrow_left(&self) -> &'static str {
        if self.unicode { "‹" } else { "<" }
    }

    pub fn arrow_right(&self) -> &'static str {
        if self.unicode { "›" } else { ">" }
    }

    pub fn ellipsis(&self) -> &'static str {
        if self.unicode { "…" } else { "..." }
    }

    /// Pick a Unicode glyph when the terminal supports it, otherwise a plain
    /// ASCII fallback.  Keeps every panel usable over a serial console.
    pub fn glyph(&self, unicode: &'static str, ascii: &'static str) -> &'static str {
        if self.unicode { unicode } else { ascii }
    }

    pub fn healthy_style(&self) -> Style {
        Style::default().fg(self.green).add_modifier(Modifier::BOLD)
    }

    pub fn warning_style(&self) -> Style {
        Style::default().fg(self.amber)
    }

    pub fn error_style(&self) -> Style {
        Style::default().fg(self.red)
    }

    pub fn label_style(&self) -> Style {
        Style::default().fg(self.text_dim)
    }

    pub fn value_style(&self) -> Style {
        Style::default().fg(self.text)
    }
}
