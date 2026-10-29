//! Deterministic terminal artwork: the FILEVO wordmark, a braille landscape
//! and the assistant owl.
//!
//! Nothing here is random at render time.  The landscape is a hash of the
//! terminal cell coordinates, so resizing is stable and the same size always
//! produces the same picture.

use crate::ui::text::{letter_spaced, width};
use crate::ui::theme::Theme;
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

const LETTERS: [char; 6] = ['F', 'I', 'L', 'E', 'V', 'O'];

const F7: [&str; 7] = [
    "██████ ",
    "██     ",
    "██     ",
    "█████  ",
    "██     ",
    "██     ",
    "██     ",
];
const I7: [&str; 7] = [
    "██████",
    "  ██  ",
    "  ██  ",
    "  ██  ",
    "  ██  ",
    "  ██  ",
    "██████",
];
const L7: [&str; 7] = [
    "██     ",
    "██     ",
    "██     ",
    "██     ",
    "██     ",
    "██     ",
    "██████ ",
];
const E7: [&str; 7] = [
    "██████ ",
    "██     ",
    "██     ",
    "█████  ",
    "██     ",
    "██     ",
    "██████ ",
];
const V7: [&str; 7] = [
    "██    ██",
    "██    ██",
    "██    ██",
    "██    ██",
    " ██  ██ ",
    " ██  ██ ",
    "  ████  ",
];
const O7: [&str; 7] = [
    " ██████ ",
    "██    ██",
    "██    ██",
    "██    ██",
    "██    ██",
    "██    ██",
    " ██████ ",
];

const F5: [&str; 5] = ["████ ", "█    ", "████ ", "█    ", "█    "];
const I5: [&str; 5] = ["█████", "  █  ", "  █  ", "  █  ", "█████"];
const L5: [&str; 5] = ["█    ", "█    ", "█    ", "█    ", "█████"];
const E5: [&str; 5] = ["████ ", "█    ", "████ ", "█    ", "████ "];
const V5: [&str; 5] = ["█   █", "█   █", "█   █", " █ █ ", "  █  "];
const O5: [&str; 5] = [" ███ ", "█   █", "█   █", "█   █", " ███ "];

fn glyph7(ch: char) -> (&'static [&'static str; 7], usize) {
    match ch {
        'F' => (&F7, 7),
        'I' => (&I7, 6),
        'L' => (&L7, 7),
        'E' => (&E7, 7),
        'V' => (&V7, 8),
        'O' => (&O7, 8),
        _ => (&F7, 7),
    }
}

fn glyph5(ch: char) -> (&'static [&'static str; 5], usize) {
    match ch {
        'F' => (&F5, 5),
        'I' => (&I5, 5),
        'L' => (&L5, 5),
        'E' => (&E5, 5),
        'V' => (&V5, 5),
        'O' => (&O5, 5),
        _ => (&F5, 5),
    }
}

pub fn wordmark_rows(max_rows: usize) -> Vec<String> {
    if max_rows >= 7 {
        compose7()
    } else if max_rows >= 5 {
        compose5()
    } else {
        vec!["F I L E V O".to_string()]
    }
}

fn compose7() -> Vec<String> {
    let mut rows = vec![String::new(); 7];
    for (index, letter) in LETTERS.iter().enumerate() {
        if index > 0 {
            for row in &mut rows {
                row.push_str("  ");
            }
        }
        let (glyph, cell_width) = glyph7(*letter);
        for (row, text) in rows.iter_mut().zip(glyph.iter()) {
            row.push_str(text);
            let used = width(text);
            if used < cell_width {
                row.push_str(&" ".repeat(cell_width - used));
            }
        }
    }
    rows.into_iter()
        .map(|row| row.trim_end().to_string())
        .collect()
}

fn compose5() -> Vec<String> {
    let mut rows = vec![String::new(); 5];
    for (index, letter) in LETTERS.iter().enumerate() {
        if index > 0 {
            for row in &mut rows {
                row.push(' ');
            }
        }
        let (glyph, cell_width) = glyph5(*letter);
        for (row, text) in rows.iter_mut().zip(glyph.iter()) {
            row.push_str(text);
            let used = width(text);
            if used < cell_width {
                row.push_str(&" ".repeat(cell_width - used));
            }
        }
    }
    rows.into_iter()
        .map(|row| row.trim_end().to_string())
        .collect()
}

/// A six-line ASCII owl used in the assistant gutter.  Keep every line the
/// same display width so the message body stays aligned.
pub const OWL: [&str; 6] = [
    "  ,___,  ",
    "  (o,o)  ",
    "  /)_(\\  ",
    "  /   \\  ",
    "  ^^ ^^  ",
    "  ~~~~~  ",
];

pub fn owl_width() -> usize {
    9
}

#[derive(Clone, Copy)]
struct Cell {
    ch: char,
    style: Style,
}

impl Default for Cell {
    fn default() -> Self {
        Self {
            ch: ' ',
            style: Style::default(),
        }
    }
}

fn hash(x: u32, y: u32, seed: u32) -> u32 {
    let mut value = x
        .wrapping_mul(374_761_393)
        .wrapping_add(y.wrapping_mul(668_265_263))
        .wrapping_add(seed.wrapping_mul(2_246_822_519));
    value = (value ^ (value >> 13)).wrapping_mul(1_274_126_177);
    value ^ (value >> 16)
}

fn mix(a: Color, b: Color, t: f64) -> Color {
    let (Color::Rgb(ar, ag, ab), Color::Rgb(br, bg, bb)) = (a, b) else {
        return a;
    };
    let t = t.clamp(0.0, 1.0);
    let blend = |x: u8, y: u8| (x as f64 + (y as f64 - x as f64) * t).round() as u8;
    Color::Rgb(blend(ar, br), blend(ag, bg), blend(ab, bb))
}

fn wordmark_style(theme: &Theme, x: usize, total: usize, row: usize, rows: usize) -> Style {
    if !theme.colour {
        return Style::default().add_modifier(Modifier::BOLD);
    }
    let t = if total <= 1 {
        0.5
    } else {
        x as f64 / (total - 1) as f64
    };
    let wave = 0.5 + 0.5 * (t * std::f64::consts::PI * 2.0 - 1.1).sin();
    let vertical = if rows <= 1 {
        0.5
    } else {
        row as f64 / (rows - 1) as f64
    };
    let highlight = 0.42 + 0.42 * wave - 0.12 * vertical;
    let colour = mix(theme.primary, Color::Rgb(226, 250, 255), highlight);
    Style::default().fg(colour).add_modifier(Modifier::BOLD)
}

fn draw_landscape(
    grid: &mut [Vec<Cell>],
    width: usize,
    height: usize,
    hole: (usize, usize, usize, usize),
    theme: &Theme,
) {
    if height == 0 || width == 0 {
        return;
    }
    let (hole_x0, hole_x1, hole_y0, hole_y1) = hole;
    let sky = Style::default().fg(theme.muted);
    let ridge_style = Style::default().fg(theme.border);
    let ground_style = Style::default().fg(theme.border).add_modifier(Modifier::DIM);

    for x in 0..width {
        if x >= hole_x0 && x < hole_x1 {
            continue;
        }
        let fx = x as f64;
        let terrain = 0.56
            + 0.18 * (fx * 0.085 + 0.8).sin()
            + 0.10 * (fx * 0.23 + 2.4).sin()
            + 0.05 * (fx * 0.71 + 0.3).sin();
        let ridge = (height as f64 * terrain.clamp(0.18, 0.92)).round() as i32;

        for y in 0..height {
            let cell_hash = hash(x as u32, y as u32, 0xA11CE);
            let in_hole = y >= hole_y0 && y < hole_y1;
            if in_hole {
                continue;
            }
            let (ch, style) = if y as i32 == ridge {
                let ch = if !theme.unicode {
                    '_'
                } else if cell_hash % 7 == 0 {
                    '⣤'
                } else if cell_hash % 3 == 0 {
                    '⣀'
                } else {
                    '⠤'
                };
                (ch, ridge_style)
            } else if y as i32 > ridge {
                if cell_hash % 17 == 0 {
                    (if theme.unicode { '⠂' } else { '`' }, ground_style)
                } else if cell_hash % 71 == 0 {
                    (if theme.unicode { '⣿' } else { '#' }, ground_style)
                } else {
                    (' ', Style::default())
                }
            } else if cell_hash % 53 == 0 {
                (if theme.unicode { '·' } else { '.' }, sky)
            } else if cell_hash % 211 == 0 {
                (if theme.unicode { '✦' } else { '*' }, sky)
            } else {
                (' ', Style::default())
            };
            if ch != ' ' {
                grid[y][x] = Cell { ch, style };
            }
        }

        // A few sparse conifers on the ridges.
        if theme.unicode && height >= 6 && hash(x as u32, 7, 0xBEEF) % 37 == 0 {
            for step in 1..=3i32 {
                let y = ridge - step;
                if y > 0 && y as usize >= hole_y1 {
                    let ch = if step == 3 {
                        '⡇'
                    } else if step == 2 {
                        '⣿'
                    } else {
                        '⢸'
                    };
                    grid[y as usize][x] = Cell {
                        ch,
                        style: ridge_style,
                    };
                }
            }
        }
    }

    if theme.unicode && width > 90 && height > 4 {
        let moon_x = width * 86 / 100;
        let moon_y = 1usize;
        if moon_x < width && (moon_x < hole_x0 || moon_x >= hole_x1) {
            grid[moon_y][moon_x] = Cell {
                ch: '◯',
                style: Style::default().fg(theme.primary),
            };
        }
    }
}

/// Compose the entire header interior for an `width` x `height` rectangle.
pub fn header_lines(width: usize, height: usize, theme: &Theme) -> Vec<Line<'static>> {
    if width == 0 || height == 0 {
        return Vec::new();
    }

    let art = wordmark_rows(height);
    let art_width = art.iter().map(|row| width_of(row)).max().unwrap_or(0);
    let art_width = art_width.max(width_of("F I L E V O"));
    let subtitle_text = "Conversational Document Intelligence";
    let spaced_subtitle = letter_spaced(subtitle_text);
    let subtitle_width = width_of(&spaced_subtitle);
    let subtitle = if height > art.len() {
        if subtitle_width + 2 <= width {
            Some(spaced_subtitle)
        } else if width_of(subtitle_text) <= width {
            Some(subtitle_text.to_string())
        } else {
            None
        }
    } else {
        None
    };
    let block_height = art.len() + usize::from(subtitle.is_some());
    let top = height.saturating_sub(block_height) / 2;
    let art_start = width.saturating_sub(art_width) / 2;

    let mut grid = vec![vec![Cell::default(); width]; height];
    draw_landscape(
        &mut grid,
        width,
        height,
        (
            art_start.saturating_sub(2),
            (art_start + art_width + 2).min(width),
            top,
            (top + block_height).min(height),
        ),
        theme,
    );

    for (row, text) in art.iter().enumerate() {
        let y = top + row;
        if y >= height {
            break;
        }
        for (offset, ch) in text.chars().enumerate() {
            let x = art_start + offset;
            if x >= width {
                break;
            }
            if ch == ' ' {
                continue;
            }
            grid[y][x] = Cell {
                ch,
                style: wordmark_style(theme, offset, art_width, row, art.len()),
            };
        }
    }

    if let Some(subtitle) = subtitle {
        let y = top + art.len();
        if y < height {
            let start = width.saturating_sub(width_of(&subtitle)) / 2;
            let style = Style::default().fg(theme.text_dim);
            for (offset, ch) in subtitle.chars().enumerate() {
                let x = start + offset;
                if x >= width {
                    break;
                }
                grid[y][x] = Cell { ch, style };
            }
        }
    }

    grid.into_iter()
        .map(|row| {
            let mut spans: Vec<Span<'static>> = Vec::new();
            let mut run = String::new();
            let mut run_style: Option<Style> = None;
            for cell in row {
                match run_style {
                    Some(style) if style == cell.style => run.push(cell.ch),
                    Some(style) => {
                        spans.push(Span::styled(std::mem::take(&mut run), style));
                        run.push(cell.ch);
                        run_style = Some(cell.style);
                    }
                    None => {
                        run.push(cell.ch);
                        run_style = Some(cell.style);
                    }
                }
            }
            if let Some(style) = run_style {
                spans.push(Span::styled(run.trim_end().to_string(), style));
            }
            Line::from(spans)
        })
        .collect()
}

fn width_of(text: &str) -> usize {
    width(text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wordmark_has_the_expected_profile() {
        let large = wordmark_rows(8);
        assert_eq!(large.len(), 7);
        assert!(large.iter().all(|row| width(row) <= 53));
        let medium = wordmark_rows(5);
        assert_eq!(medium.len(), 5);
        assert!(medium.iter().all(|row| width(row) <= 35));
        assert_eq!(wordmark_rows(2), vec!["F I L E V O"]);
    }

    #[test]
    fn landscape_is_deterministic_and_width_safe() {
        let theme = Theme::detect();
        let first = header_lines(100, 12, &theme);
        let second = header_lines(100, 12, &theme);
        assert_eq!(first.len(), 12);
        assert_eq!(
            first.iter().map(|line| line.to_string()).collect::<Vec<_>>(),
            second
                .iter()
                .map(|line| line.to_string())
                .collect::<Vec<_>>()
        );
        for line in first {
            assert!(width(&line.to_string()) <= 100);
        }
    }

    #[test]
    fn ascii_fallback_contains_no_braille() {
        let mut theme = Theme::detect();
        theme.unicode = false;
        let lines = header_lines(96, 10, &theme);
        let rendered = lines
            .iter()
            .map|line| line.to_string()
            .collect::<Vec<_>>()
            .join("\n");
        assert!(!rendered.chars().any(|ch| ('\u{2800}'..='\u{28ff}').contains(&ch)));
        assert!(rendered.contains("FILEVO") || rendered.contains("F I L E V O"));
    }
}
