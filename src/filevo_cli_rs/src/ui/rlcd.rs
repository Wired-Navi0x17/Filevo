//! RLCD decision panel.
//!
//! The backend ships with a default prior.  That prior is *not* a live
//! calibration of the user's prompt, so it is never drawn as a distribution.
//! A distribution is only plotted after `RLCDDecisionEngine.evaluate_intent`
//! actually ran and the five probabilities passed validation.

use crate::app::App;
use crate::model::{DistributionError, Risk};
use crate::ui::text::{truncate, width, wrap};
use crate::ui::theme::Theme;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, Paragraph};
use ratatui::Frame;

const LABEL_WIDTH: usize = 18;

fn risk_style(risk: Risk, theme: &Theme) -> Style {
    match risk {
        Risk::Low => Style::default()
            .fg(theme.green)
            .add_modifier(Modifier::BOLD),
        Risk::Medium => Style::default().fg(theme.amber).add_modifier(Modifier::BOLD),
        Risk::High => Style::default().fg(theme.red).add_modifier(Modifier::BOLD),
        Risk::Unknown => Style::default().fg(theme.text_dim),
    }
}

fn gauge(value: f64, gauge_width: usize, theme: &Theme, bold: bool) -> Vec<Span<'static>> {
    let gauge_width = gauge_width.max(1);
    let filled = ((value.clamp(0.0, 1.0) * gauge_width as f64).round() as usize)
        .min(gauge_width);
    let filled = if value > 0.0 { filled.max(1) } else { filled };
    let fill_style = if bold {
        Style::default()
            .fg(theme.primary)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(theme.secondary)
    };
    vec![
        Span::styled("█".repeat(filled), fill_style),
        Span::styled(
            "░".repeat(gauge_width - filled),
            Style::default().fg(theme.selection_bg),
        ),
    ]
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    if area.width < 10 || area.height < 3 {
        return;
    }
    let block = theme.panel().title(Line::from(vec![
        Span::styled(
            format!("{} ", theme.glyph("◈", "*")),
            Style::default().fg(theme.primary),
        ),
        Span::styled(
            "RLCD Decision ",
            Style::default()
                .fg(theme.primary)
                .add_modifier(Modifier::BOLD),
        ),
    ]));
    let inner = block.inner(area);
    frame.render_widget(block, area);
    if inner.width == 0 || inner.height == 0 {
        return;
    }
    let inner_width = inner.width as usize;
    let inner_height = inner.height as usize;
    let decision = &app.dashboard.decision;
    let mut lines: Vec<Line<'static>> = Vec::new();

    match decision.validate() {
        Ok(()) => {
            let gauge_width = inner_width
                .saturating_sub(2 + LABEL_WIDTH + 1 + 1 + 4)
                .clamp(3, 14);
            let winner = decision.winning_intent();
            for (index, name) in crate::model::INTENTS.iter().enumerate() {
                let value = decision.values[index].unwrap_or(0.0);
                let is_winner = winner == Some(*name);
                let label_style = if is_winner {
                    Style::default()
                        .fg(theme.text)
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(theme.text)
                };
                let mut spans = vec![
                    Span::styled(
                        format!("{} ", theme.glyph("◈", "*")),
                        Style::default().fg(theme.primary),
                    ),
                    Span::styled(
                        format!("{:<LABEL_WIDTH$}", truncate(name, LABEL_WIDTH)),
                        label_style,
                    ),
                    Span::styled(" ", Style::default()),
                ];
                spans.extend(gauge(value, gauge_width, theme, is_winner));
                spans.push(Span::styled(" ", Style::default()));
                spans.push(Span::styled(
                    format!("{value:.2}"),
                    if is_winner {
                        Style::default()
                            .fg(theme.primary)
                            .add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(theme.text_dim)
                    },
                ));
                lines.push(Line::from(spans));
            }
            if inner_height >= 8 {
                lines.push(Line::default());
            }
            let confidence = decision
                .confidence
                .filter(|value| value.is_finite())
                .map(|value| format!("{:.1}%", value * 100.0))
                .unwrap_or_else(|| "Unavailable".to_string());
            lines.push(Line::from(vec![
                Span::styled("Confidence: ", Style::default().fg(theme.text_dim)),
                Span::styled(
                    confidence,
                    Style::default()
                        .fg(theme.primary)
                        .add_modifier(Modifier::BOLD),
                ),
            ]));
            let entropy = decision
                .entropy
                .filter(|value| value.is_finite())
                .map(|value| format!("{value:.2}"))
                .unwrap_or_else(|| "—".to_string());
            lines.push(Line::from(vec![
                Span::styled("Entropy: ", Style::default().fg(theme.text_dim)),
                Span::styled(entropy, Style::default().fg(theme.text)),
                Span::styled("   Risk: ", Style::default().fg(theme.text_dim)),
                Span::styled(decision.risk.label(), risk_style(decision.risk, theme)),
            ]));
            if inner_height >= 10 {
                lines.push(Line::default());
                for footer in wrap(
                    "Confidence = P(selected intent) · H = normalized Shannon entropy (log2)",
                    inner_width,
                ) {
                    lines.push(Line::from(Span::styled(
                        footer,
                        Style::default().fg(theme.muted),
                    )));
                }
            }
            if app.demo && lines.len() < inner_height {
                lines.push(Line::from(Span::styled(
                    "Demo fixture · not a live calibration",
                    Style::default()
                        .fg(theme.amber)
                        .add_modifier(Modifier::BOLD),
                )));
            }
        }
        Err(error) => {
            let headline = match error {
                DistributionError::Missing => "No live distribution",
                DistributionError::NotFinite => "Distribution rejected",
                DistributionError::OutOfRange => "Distribution rejected",
                DistributionError::BadSum => "Distribution rejected",
            };
            lines.push(Line::from(Span::styled(
                headline,
                Style::default()
                    .fg(theme.amber)
                    .add_modifier(Modifier::BOLD),
            )));
            let detail = if error == DistributionError::Missing {
                "RLCD scores the next prompt you submit. The backend's default prior is withheld because it is not a calibration."
                    .to_string()
            } else {
                format!("{} Values are not normalised or plotted.", error.message())
            };
            for line in wrap(&detail, inner_width) {
                lines.push(Line::from(Span::styled(
                    line,
                    Style::default().fg(theme.text_dim),
                )));
            }
            if inner_height >= 8 {
                lines.push(Line::default());
                lines.push(Line::from(Span::styled(
                    "Type a message to calibrate an intent.",
                    Style::default().fg(theme.muted),
                )));
            }
        }
    }

    lines.truncate(inner_height);
    frame.render_widget(
        Paragraph::new(Text::from(lines)).style(Style::default().bg(theme.panel_bg)),
        inner,
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Decision;
    use std::collections::HashMap;

    #[test]
    fn bars_stay_inside_their_budget() {
        for gauge_width in 3..=14 {
            let spans = gauge(0.71, gauge_width, &Theme::detect(), true);
            let text: String = spans.iter().map(|span| span.content.as_ref()).collect();
            assert_eq!(width(&text), gauge_width);
        }
    }

    #[test]
    fn incomplete_distribution_is_missing_not_zeroed() {
        let decision = Decision::from_map(
            false,
            &HashMap::new(),
            None,
            None,
            None,
            "backend_default_prior",
        );
        assert_eq!(decision.validate(), Err(DistributionError::Missing));
    }
}
