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

const F3: [&str; 3] = ["███ ", "██  ", "██  "];
const I3: [&str; 3] = ["███", " █ ", "███"];
const L3: [&str; 3] = ["██ ", "██ ", "███"];
const E3: [&str; 3] = ["███", "██ ", "███"];
const V3: [&str; 3] = ["█ █", "█ █", " █ "];
const O3: [&str; 3] = ["███", "█ █", "███"];

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

fn glyph3(ch: char) -> (&'static [&'static str; 3], usize) {
    match ch {
        'F' => (&F3, 4),
        'I' => (&I3, 3),
        'L' => (&L3, 3),
        'E' => (&E3, 3),
        'V' => (&V3, 3),
        'O' => (&O3, 3),
        _ => (&F3, 4),
    }
}

pub fn wordmark_rows(max_rows: usize) -> Vec<String> {
    if max_rows >= 7 {
        compose7()
    } else if max_rows >= 5 {
        compose5()
    } else if max_rows >= 3 {
        compose3()
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

fn compose3() -> Vec<String> {
    let mut rows = vec![String::new(); 3];
    for (index, letter) in LETTERS.iter().enumerate() {
        if index > 0 {
            for row in &mut rows {
                row.push(' ');
            }
        }
        let (glyph, cell_width) = glyph3(*letter);
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

/// Smooth braille/ASCII spinner for active operations
pub const SPINNERS: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/// Kinetic wave characters for telemetry bars
pub const WAVE_BARS: [&str; 8] = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"];

/// 12-stage high-density Braille harmonic flow activity indicator
pub fn activity_ticker(tick: u64) -> &'static str {
    const FRAMES: [&str; 12] = [
        "⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷",
        "⠋", "⠙", "⠹", "⠸",
    ];
    FRAMES[((tick / 2) as usize) % FRAMES.len()]
}

/// Rotating radar scanner glyph
pub fn radar_glyph(tick: u64) -> &'static str {
    const RADAR: [&str; 8] = ["⠋", "⠙", "⠚", "⠒", "⠂", "⠂", "⠒", "⠲"];
    RADAR[((tick / 3) as usize) % RADAR.len()]
}

/// High-resolution sub-pixel Braille wave generator.
/// Each Braille unicode character (U+2800..U+28FF) contains an exact 2x4 dot matrix.
/// This renders a continuous mathematical sinusoidal curve with sub-character resolution.
pub fn pulse_wave(tick: u64, width: usize) -> String {
    if width == 0 {
        return String::new();
    }
    let mut out = String::with_capacity(width * 4);
    let t = tick as f64 * 0.12;

    for cell in 0..width {
        let mut byte: u8 = 0;
        // Two sub-pixel columns per character cell
        for col in 0..2 {
            let sub_x = (cell * 2 + col) as f64;
            // Harmonic wave formula
            let wave_y = 1.5 + 1.35 * (t + sub_x * 0.22).sin() + 0.35 * (t * 0.7 - sub_x * 0.09).cos();
            let row = (wave_y.round() as i32).clamp(0, 3) as usize;

            // Map (col, row) to Braille dot bitmask:
            let bit = match (col, row) {
                (0, 0) => 0x01,
                (0, 1) => 0x02,
                (0, 2) => 0x04,
                (0, 3) => 0x40,
                (1, 0) => 0x08,
                (1, 1) => 0x10,
                (1, 2) => 0x20,
                (1, 3) => 0x80,
                _ => 0,
            };
            byte |= bit;
        }
        let ch = if byte == 0 {
            '\u{2800}' // Empty Braille pattern
        } else {
            char::from_u32(0x2800 + byte as u32).unwrap_or('·')
        };
        out.push(ch);
    }
    out
}

/// Animated Braille Cat with synchronized blinking, ear twitching, and tail wagging.
pub fn cat_animation_lines(tick: u64, theme: &Theme) -> Vec<Line<'static>> {
    let frame = (tick / 2) % 16;
    let is_blink = frame == 7 || frame == 8;
    let is_squint = frame == 9;
    let is_wink = frame == 14;
    let twitch_left_ear = frame == 4;
    let twitch_right_ear = frame == 11;
    let tail_wag = frame >= 10 && frame <= 13;
    let purr = frame == 2 || frame == 3;

    // Ear row (0)
    let row0 = if twitch_left_ear {
        "⠀⠀⠀⠀⢠⡶⠒⢷⣤⡀⠀⠀⠀⠀⠀⣲⡶⠛⠻⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀"
    } else if twitch_right_ear {
        "⠀⠀⠀⠀⢠⡶⠚⢷⣤⡀⠀⠀⠀⠀⠀⣲⡶⠒⠻⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀"
    } else {
        "⠀⠀⠀⠀⢠⡶⠚⢷⣤⡀⠀⠀⠀⠀⠀⣲⡶⠛⠻⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀"
    };

    let row1 = "⠀⠀⠀⢠⡿⠁⠀⠀⠙⣷⣄⠀⢀⣴⡟⠁⠀⠀⢷⢹⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀";
    let row2 = "⠀⠀⠀⣾⠃⠀⠠⠶⠚⠛⠛⠛⠛⠋⠀⠀⣀⡀⢸⠈⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀";
    let row3 = "⠀⠀⢸⣏⡔⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠚⠉⠉⣿⠀⢹⠀⠀⠀⠀⠀⠀⠀⠀⠀";
    let row4 = "⠀⠀⢾⠏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀";

    // Eyes rows (5 and 6)
    let (row5, row6) = if is_blink {
        (
            "⠀⢠⣿⠀⣀⣀⠀⠀⠀⠀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
            "⢒⡾⠁⠀⠉⠉⠀⠀⠀⠀⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
        )
    } else if is_squint {
        (
            "⠀⢠⣿⠀⢀⣀⠀⠀⠀⠀⢀⣀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
            "⢒⡾⠁⠀⠚⠉⠀⠀⠀⠀⠚⠉⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
        )
    } else if is_wink {
        (
            "⠀⢠⣿⢠⣶⡆⠀⠀⠀⠀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
            "⢒⡾⠁⠘⠟⠁⠀⠀⠀⠀⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
        )
    } else {
        (
            "⠀⢠⣿⢠⣶⡆⠀⠀⠀⠀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
            "⢒⡾⠁⠘⠟⠁⠀⠀⠀⠀⣿⣿⡆⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀⠀",
        )
    };

    // Mouth / whisker row (7)
    let row7 = if purr {
        "⠉⣧⠀⠀⠀⠀⠃⠀⠀⠀⠈⠉⠠⣔⠀⠀⠀⠀⠀⠀⣸⡇⢀⣤⠶⠛⠛⠻⢦⣄"
    } else if tail_wag {
        "⠉⣧⠀⠀⠀⠀⠃⠀⠀⠀⠈⠉⠠⣍⠀⠀⠀⠀⠀⠀⣸⡇⢀⣤⠶⠛⠛⠻⣦⡀"
    } else {
        "⠉⣧⠀⠀⠀⠀⠃⠀⠀⠀⠈⠉⠠⣍⠀⠀⠀⠀⠀⠀⣸⡇⢀⣤⠶⠛⠛⠻⢦⣄"
    };

    // Body & Tail rows (8..17)
    let row8 = if tail_wag {
        "⠀⠸⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⡟⣴⠟⠁⠀⠀⠐⠒⠚⣧"
    } else {
        "⠀⠸⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⡟⣴⠟⠁⠀⠀⠀⠀⠀⢻"
    };

    let row9 = if tail_wag {
        "⠀⠀⠀⠛⣷⡦⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣤⡴⠞⠋⢠⡟⠀⠀⠀⠀⠀⠀⠀⣸"
    } else {
        "⠀⠀⠀⠛⣷⡦⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⣤⡴⠞⠋⢠⡟⠀⠀⠀⠀⠀⠀⢀⡾"
    };

    let row10 = if tail_wag {
        "⠀⠀⠀⢰⡿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠀⠀⠀⠀⣾⠁⠀⠀⠀⠀⠀⢠⡾⠃"
    } else {
        "⠀⠀⠀⢰⡿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠉⠀⠀⠀⠀⣾⠁⠀⠀⠀⠀⠀⢠⡿⠁"
    };

    let row11 = if tail_wag {
        "⠀⠀⠀⣾⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⡄⠀⠀⠀⠀⣠⡿⠁⠀"
    } else {
        "⠀⠀⠀⣾⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢿⡄⠀⠀⠀⠀⣠⡟⠁⠀"
    };

    let row12 = "⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⣶⣤⣤⡶⠋⠀⠀⠀";
    let row13 = "⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀";
    let row14 = "⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀";
    let row15 = "⠀⠀⠀⢻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀";
    let row16 = "⠀⠀⠀⠀⠻⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀";
    let row17 = "⠀⠀⠀⠀⠀⠈⠙⠳⠶⠶⠶⠶⠶⠶⠶⠶⠶⠶⠶⠶⠶⠖⠀⠀⠀⠀⠀⠀⠀";

    let rows = [
        row0, row1, row2, row3, row4, row5, row6, row7, row8, row9, row10, row11, row12, row13, row14, row15, row16, row17,
    ];

    let cat_style = Style::default().fg(theme.primary);
    rows.into_iter()
        .map(|r| Line::from(vec![Span::raw("   "), Span::styled(r, cat_style)]))
        .collect()
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

fn wordmark_style(
    theme: &Theme,
    x: usize,
    total: usize,
    row: usize,
    rows: usize,
    tick: u64,
) -> Style {
    if !theme.colour {
        return Style::default().add_modifier(Modifier::BOLD);
    }
    let t = if total <= 1 {
        0.5
    } else {
        x as f64 / (total - 1) as f64
    };
    // Gentle kinetic shimmer wave travelling across wordmark
    let shimmer_phase = (tick as f64 * 0.08) % (std::f64::consts::PI * 2.0);
    let wave = 0.5 + 0.5 * (t * std::f64::consts::PI * 2.0 - 1.1 + shimmer_phase).sin();
    let vertical = if rows <= 1 {
        0.5
    } else {
        row as f64 / (rows - 1) as f64
    };
    let highlight = (0.32 + 0.45 * wave - 0.10 * vertical).clamp(0.0, 1.0);
    let colour = mix(theme.primary, Color::Rgb(215, 230, 245), highlight);
    Style::default().fg(colour).add_modifier(Modifier::BOLD)
}

fn draw_landscape(
    grid: &mut [Vec<Cell>],
    width: usize,
    height: usize,
    hole: (usize, usize),
    tick: u64,
    theme: &Theme,
) {
    if height == 0 || width == 0 {
        return;
    }
    let (hole_x0, hole_x1) = hole;
    let sky = Style::default().fg(theme.muted);
    let ridge_style = Style::default().fg(theme.border);
    let tree_style = Style::default().fg(theme.secondary);
    let ground_style = Style::default()
        .fg(theme.border)
        .add_modifier(Modifier::DIM);

    // A smooth, deterministic skyline. Two Gaussian peaks frame the
    // wordmark, with slower swells underneath so resizing stays organic.
    let span = width as f64;
    let ridge_at = |x: usize| -> i32 {
        let fx = x as f64;
        let base = 0.78 + 0.08 * (fx * 0.075 + 0.6).sin() + 0.04 * (fx * 0.21 + 2.2).sin();
        let peaks = 0.58 * (-((fx - span * 0.16) / (span * 0.10)).powi(2)).exp()
            + 0.42 * (-((fx - span * 0.86) / (span * 0.13)).powi(2)).exp();
        let terrain =
            (base - peaks + 0.04 * (fx * 0.57 + 1.1).sin()).clamp(0.08, 0.86) * height as f64;
        terrain.round() as i32
    };
    let ridges: Vec<i32> = (0..width).map(ridge_at).collect();

    for x in 0..width {
        if x >= hole_x0 && x < hole_x1 {
            continue;
        }
        let ridge = ridges[x];
        let next = ridges.get(x + 1).copied().unwrap_or(ridge);

        // Sky: dynamic twinkling stars and drifting constellations
        for y in 0..ridge.max(0) as usize {
            let cell_hash = hash(x as u32, y as u32, 0xA11CE);
            let twinkle_phase = ((tick / 3).wrapping_add(cell_hash as u64) % 60) as usize;
            let (ch, style) = if cell_hash % 149 == 0 {
                let star_ch = match twinkle_phase % 4 {
                    0 => if theme.unicode { '✦' } else { '*' },
                    1 => if theme.unicode { '✧' } else { '+' },
                    2 => if theme.unicode { '⋆' } else { '*' },
                    _ => if theme.unicode { '·' } else { '.' },
                };
                let col = if twinkle_phase < 15 {
                    theme.primary
                } else if twinkle_phase < 35 {
                    theme.secondary
                } else {
                    theme.muted
                };
                (star_ch, Style::default().fg(col))
            } else if cell_hash % 37 == 0 {
                let dust_ch = if (twinkle_phase + x) % 2 == 0 { '·' } else { '.' };
                (if theme.unicode { dust_ch } else { '.' }, sky)
            } else {
                continue;
            };
            grid[y][x] = Cell { ch, style };
        }

        // Ridge and the vertical step that connects it to the next column.
        let start = ridge.min(next);
        let end = ridge.max(next);
        for y in start..=end {
            if y < 0 || y as usize >= height {
                continue;
            }
            let ch = if !theme.unicode {
                if ridge == next { '_' } else { '|' }
            } else if ridge == next {
                '⠒'
            } else if (x + y as usize) % 2 == 0 {
                '⡇'
            } else {
                '⢸'
            };
            grid[y as usize][x] = Cell {
                ch,
                style: ridge_style,
            };
        }

        // Stippled mountain body under the ridge.
        for y in (ridge.max(0) as usize + 1)..height {
            let cell_hash = hash(x as u32, y as u32, 0xA11CE);
            let near_ridge = y as i32 == ridge + 1;
            let (ch, style) = if cell_hash % 31 == 0 {
                (if theme.unicode { '⣿' } else { '#' }, ground_style)
            } else if cell_hash % if near_ridge { 4 } else { 7 } == 0 {
                (if theme.unicode { '⠂' } else { '`' }, ground_style)
            } else {
                continue;
            };
            grid[y][x] = Cell { ch, style };
        }

        // Slim conifers clustered on the near ridges.
        if theme.unicode && height >= 6 && ridge > 2 && hash(x as u32, 7, 0xBEEF) % 9 == 0 {
            let tree_height = 3 + (hash(x as u32, 11, 0xF00D) % 3) as i32;
            for step in 1..=tree_height {
                let y = ridge - step;
                if y < 0 {
                    break;
                }
                let ch = if step == tree_height {
                    '⡇'
                } else if step >= tree_height - 1 {
                    '⣿'
                } else {
                    '⢸'
                };
                grid[y as usize][x] = Cell {
                    ch,
                    style: tree_style,
                };
            }
        }
    }

    if theme.unicode && width > 90 && height > 4 {
        let moon_x = width * 86 / 100;
        let moon_y = 1usize;
        if moon_x < width && (moon_x < hole_x0 || moon_x >= hole_x1) {
            let moon_col = if (tick / 8) % 2 == 0 {
                theme.primary
            } else {
                theme.secondary
            };
            grid[moon_y][moon_x] = Cell {
                ch: '◯',
                style: Style::default().fg(moon_col),
            };
        }
    }
}

/// Compose the entire header interior for an `width` x `height` rectangle.
pub fn header_lines(
    width: usize,
    height: usize,
    tick: u64,
    theme: &Theme,
) -> Vec<Line<'static>> {
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
        ),
        tick,
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
                style: wordmark_style(theme, offset, art_width, row, art.len(), tick),
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
        let first = header_lines(100, 12, 0, &theme);
        let second = header_lines(100, 12, 0, &theme);
        assert_eq!(first.len(), 12);
        assert_eq!(
            first
                .iter()
                .map(|line| line.to_string())
                .collect::<Vec<_>>(),
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
        let lines = header_lines(96, 10, 0, &theme);
        let rendered = lines
            .iter()
            .map(|line| line.to_string())
            .collect::<Vec<_>>()
            .join("\n");
        assert!(
            !rendered
                .chars()
                .any(|ch| ('\u{2800}'..='\u{28ff}').contains(&ch))
        );
        assert!(!rendered.trim().is_empty());
        assert!(rendered.contains("█"));
    }
}
