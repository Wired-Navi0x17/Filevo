//! Width-aware text helpers shared by every panel.
//!
//! Ratatui clips cells, but it does not word-wrap the pre-composed lines we
//! feed into `Paragraph` when scrolling must be measured exactly.  These
//! helpers keep the renderer honest on proportional and wide Unicode input.

use unicode_segmentation::UnicodeSegmentation;
use unicode_width::UnicodeWidthStr;

pub fn width(text: &str) -> usize {
    UnicodeWidthStr::width(text)
}

/// Collapse whitespace into word wrapping.  Explicit newlines are preserved so
/// conversation bodies keep their paragraphs.
pub fn wrap(text: &str, max_width: usize) -> Vec<String> {
    let max_width = max_width.max(1);
    let mut lines = Vec::new();
    for raw in text.split('\n') {
        wrap_line(raw, max_width, &mut lines);
    }
    if lines.is_empty() {
        lines.push(String::new());
    }
    lines
}

fn is_table_or_art_line(line: &str) -> bool {
    let trimmed = line.trim_start();
    trimmed.starts_with('┏')
        || trimmed.starts_with('┃')
        || trimmed.starts_with('┡')
        || trimmed.starts_with('┢')
        || trimmed.starts_with('┩')
        || trimmed.starts_with('└')
        || trimmed.starts_with('│')
        || trimmed.starts_with('┌')
        || trimmed.starts_with('├')
        || trimmed.starts_with('|')
        || trimmed.starts_with('+')
        || line.contains('┃')
        || line.contains('│')
        || line.contains('┏')
        || line.contains('━')
        || line.contains('─')
        || line.contains('└')
        || line.contains('┌')
}

fn wrap_line(raw: &str, max_width: usize, out: &mut Vec<String>) {
    let line = raw.trim_end();
    if line.is_empty() {
        out.push(String::new());
        return;
    }

    if is_table_or_art_line(line) {
        if width(line) <= max_width {
            out.push(line.to_string());
        } else {
            out.push(truncate(line, max_width));
        }
        return;
    }

    let mut current = String::new();
    let mut current_width = 0usize;
    for word in line.split_whitespace() {
        let word_width = width(word);
        if word_width > max_width {
            if !current.is_empty() {
                out.push(std::mem::take(&mut current));
                current_width = 0;
            }
            split_long_word(word, max_width, out, &mut current, &mut current_width);
            continue;
        }
        if current.is_empty() {
            current.push_str(word);
            current_width = word_width;
        } else if current_width + 1 + word_width <= max_width {
            current.push(' ');
            current.push_str(word);
            current_width += 1 + word_width;
        } else {
            out.push(std::mem::take(&mut current));
            current.push_str(word);
            current_width = word_width;
        }
    }
    if !current.is_empty() {
        out.push(current);
    }
}

fn split_long_word(
    word: &str,
    max_width: usize,
    out: &mut Vec<String>,
    current: &mut String,
    current_width: &mut usize,
) {
    for grapheme in word.graphemes(true) {
        let cell_width = width(grapheme);
        if *current_width + cell_width > max_width && !current.is_empty() {
            out.push(std::mem::take(current));
            *current_width = 0;
        }
        current.push_str(grapheme);
        *current_width += cell_width;
    }
}

/// Truncate to a terminal-cell budget, appending an ellipsis when possible.
pub fn truncate(text: &str, max_width: usize) -> String {
    if width(text) <= max_width {
        return text.to_string();
    }
    if max_width == 0 {
        return String::new();
    }
    let budget = max_width.saturating_sub(1);
    let mut out = String::new();
    let mut used = 0usize;
    for grapheme in text.graphemes(true) {
        let cell_width = width(grapheme);
        if used + cell_width > budget {
            break;
        }
        out.push_str(grapheme);
        used += cell_width;
    }
    out.push('…');
    out
}

/// Pad on the right to exactly `max_width` cells (clipping when necessary).
pub fn pad(text: &str, max_width: usize) -> String {
    let truncated = truncate(text, max_width);
    let used = width(&truncated);
    let mut out = truncated;
    out.push_str(&" ".repeat(max_width.saturating_sub(used)));
    out
}

pub fn spaces(count: usize) -> String {
    " ".repeat(count)
}

/// Space out a subtitle the way the reference header does, falling back to the
/// plain string when the terminal is too narrow.
pub fn letter_spaced(text: &str) -> String {
    let mut out = String::new();
    for (index, ch) in text.chars().enumerate() {
        if index > 0 && ch != ' ' {
            out.push(' ');
        }
        out.push(ch);
    }
    out
}

pub fn center_pad(text: &str, max_width: usize) -> String {
    let text_width = width(text);
    if text_width >= max_width {
        return truncate(text, max_width);
    }
    let left = (max_width - text_width) / 2;
    format!("{}{}", spaces(left), text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wrapping_never_exceeds_the_cell_budget() {
        let text = "A model can overfit when it learns noise instead of general patterns.";
        for budget in [12, 24, 40, 80] {
            for line in wrap(text, budget) {
                assert!(
                    width(&line) <= budget,
                    "{line:?} exceeds {budget}: {}",
                    width(&line)
                );
            }
        }
    }

    #[test]
    fn explicit_newlines_are_preserved() {
        assert_eq!(wrap("one\n\ntwo", 20), vec!["one", "", "two"]);
    }

    #[test]
    fn wide_graphemes_are_split_safely() {
        let lines = wrap("界界界界界", 4);
        assert!(lines.len() > 1);
        assert!(lines.iter().all(|line| width(line) <= 4));
    }

    #[test]
    fn truncation_marks_elision() {
        assert_eq!(truncate("abcdef", 4), "abc…");
        assert_eq!(truncate("abc", 4), "abc");
        assert_eq!(truncate("abc", 0), "");
    }
}
