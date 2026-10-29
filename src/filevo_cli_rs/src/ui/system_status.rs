//! System status panel: real model readiness, web capability, conversation
//! memory, GPU utilisation and filesystem usage.  Nothing here is decorative.

use crate::app::App;
use crate::model::format_size;
use crate::ui::theme::Theme;
use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, Paragraph};
use ratatui::Frame;

fn gauge(
    ratio: Option<f64>,
    gauge_width: usize,
    fill: ratatui::style::Color,
    theme: &Theme,
) -> Vec<Span<'static>> {
    let gauge_width = gauge_width.max(1);
    let filled = ratio
        .map(|value| {
            let count = ((value.clamp(0.0, 1.0) * gauge_width as f64).round() as usize)
                .min(gauge_width);
            if value > 0.0 { count.max(1) } else { count }
        })
        .unwrap_or(0);
    vec![
        Span::styled(
            theme.gauge_fill().to_string().repeat(filled),
            Style::default().fg(fill),
        ),
        Span::styled(
            theme
                .gauge_empty()
                .to_string()
                .repeat(gauge_width - filled),
            Style::default().fg(theme.selection_bg),
        ),
    ]
}

fn metric_line(
    icon: &'static str,
    label: &str,
    value: &str,
    ratio: Option<f64>,
    column_width: usize,
    fill: ratatui::style::Color,
    theme: &Theme,
) -> Line<'static> {
    let label_budget = column_width.saturating_sub(2 + 1 + value.len()).max(3);
    let label = crate::ui::text::truncate(label, label_budget);
    let used = 2 + crate::ui::text::width(&label) + 1 + value.len();
    let gauge_width = column_width.saturating_sub(used).clamp(0, 12);
    let mut spans = vec![
        Span::styled(
            format!("{icon} "),
            Style::default().fg(theme.primary).add_modifier(Modifier::BOLD),
        ),
        Span::styled(label.to_string(), Style::default().fg(theme.text_dim)),
    ];
    if gauge_width >= 2 {
        spans.push(Span::styled(" ", Style::default()));
        spans.extend(gauge(ratio, gauge_width, fill, theme));
    }
    spans.push(Span::styled(" ", Style::default()));
    spans.push(Span::styled(
        value.to_string(),
        Style::default().fg(theme.text),
    ));
    Line::from(spans)
}

pub fn render(frame: &mut Frame, area: Rect, app: &App, theme: &Theme) {
    if area.width < 8 || area.height < 2 {
        return;
    }
    let block = theme.panel().title(Line::from(vec![
        Span::styled(
            format!("{} ", theme.glyph("⚙", "*")),
            Style::default().fg(theme.primary),
        ),
        Span::styled(
            "System Status ",
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

    let dashboard = &app.dashboard;
    let received = app.demo
        || dashboard.generated_at.is_some()
        || !dashboard.model.id.is_empty()
        || matches!(app.backend, crate::app::BackendState::Online);
    let width = inner.width as usize;
    let two_columns = width >= 34;
    let column_width = if two_columns {
        (width.saturating_sub(1)) / 2
    } else {
        width
    };
    let wide_column = column_width >= 30;
    let gpu_label = if wide_column {
        dashboard
            .telemetry
            .gpu
            .as_ref()
            .and_then(|gpu| gpu.name.rsplit("RTX").next())
            .map(|rest| {
                let number = rest.split_whitespace().next().unwrap_or("").trim();
                if number.is_empty() {
                    "GPU".to_string()
                } else {
                    format!("GPU (RTX {number})")
                }
            })
            .unwrap_or_else(|| "GPU".to_string())
    } else {
        "GPU".to_string()
    };

    let model_ready = dashboard.telemetry.model_ready || dashboard.model.loaded;
    let model_ratio = if received {
        Some(if model_ready { 1.0 } else { 0.0 })
    } else {
        None
    };
    let model_value = match model_ratio {
        Some(ratio) if ratio > 0.0 => "100%",
        Some(_) => "0%",
        None => "—",
    };
    let web = &dashboard.telemetry.web;
    let web_ratio = if received {
        Some(if web.enabled { 1.0 } else { 0.0 })
    } else {
        None
    };
    let web_value = match web_ratio {
        Some(ratio) if ratio > 0.0 => "Enabled",
        Some(_) => "Disabled",
        None => "—",
    };
    let memory_ratio = if dashboard.session.memory_limit > 0 {
        Some(dashboard.session.memory_used as f64 / dashboard.session.memory_limit as f64)
    } else {
        None
    };
    let memory_value = if dashboard.session.memory_limit > 0 {
        if wide_column {
            format!(
                "{}/{} turns",
                dashboard.session.memory_used, dashboard.session.memory_limit
            )
        } else {
            format!(
                "{}/{}",
                dashboard.session.memory_used, dashboard.session.memory_limit
            )
        }
    } else {
        "—".to_string()
    };
    let (gpu_ratio, gpu_value) = match &dashboard.telemetry.gpu {
        Some(gpu) => (
            Some((gpu.utilization / 100.0).clamp(0.0, 1.0)),
            format!("{:.0}%", gpu.utilization),
        ),
        None => (None, "—".to_string()),
    };
    let (disk_ratio, disk_value) = match &dashboard.telemetry.disk {
        Some(disk) if disk.total > 0 => {
            let ratio = disk.used as f64 / disk.total as f64;
            let label = if column_width >= 34 {
                format!("{} / {}", format_size(disk.used), format_size(disk.total))
            } else {
                format!("{:.0}%", ratio * 100.0)
            };
            (Some(ratio), label)
        }
        _ => (None, "—".to_string()),
    };

    let left = vec![
        metric_line(
            theme.glyph("◈", "*"),
            "Model",
            model_value,
            model_ratio,
            column_width,
            theme.primary,
            theme,
        ),
        metric_line(
            theme.glyph("◍", "@"),
            if wide_column { "Web Search" } else { "Web" },
            web_value,
            web_ratio,
            column_width,
            theme.green,
            theme,
        ),
        metric_line(
            theme.glyph("⌂", "T"),
            if wide_column { "Memory" } else { "Mem" },
            &memory_value,
            memory_ratio,
            column_width,
            theme.primary,
            theme,
        ),
    ];
    let right = vec![
        metric_line(
            theme.glyph("▣", "D"),
            &gpu_label,
            &gpu_value,
            gpu_ratio,
            column_width,
            theme.primary,
            theme,
        ),
        metric_line(
            theme.glyph("▤", "S"),
            if wide_column { "Disk Usage" } else { "Disk" },
            &disk_value,
            disk_ratio,
            column_width,
            theme.primary,
            theme,
        ),
    ];

    let rows = inner.height as usize;
    if two_columns {
        let left_width = column_width as u16;
        let right_x = inner.x + left_width + 1;
        let right_width = inner.width.saturating_sub(left_width + 1);
        let left_rect = Rect {
            width: left_width,
            height: inner.height,
            ..inner
        };
        let right_rect = Rect {
            x: right_x,
            width: right_width,
            ..inner
        };
        let left_lines: Vec<Line<'static>> = left.into_iter().take(rows).collect();
        let right_lines: Vec<Line<'static>> = right.into_iter().take(rows).collect();
        frame.render_widget(Paragraph::new(Text::from(left_lines)), left_rect);
        frame.render_widget(Paragraph::new(Text::from(right_lines)), right_rect);
    } else {
        let mut lines = left;
        lines.extend(right);
        lines.truncate(rows);
        frame.render_widget(Paragraph::new(Text::from(lines)), inner);
    }
}
