//! Responsive geometry.  Every region is derived from the live terminal
//! rectangle; there are no fixed screen coordinates.

use ratatui::layout::Rect;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LayoutMode {
    Spacious,
    Standard,
    Compact,
    TooSmall,
}

impl LayoutMode {
    pub fn label(self) -> &'static str {
        match self {
            Self::Spacious => "spacious",
            Self::Standard => "standard",
            Self::Compact => "compact",
            Self::TooSmall => "too-small",
        }
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub struct LayoutRects {
    pub mode: Option<LayoutMode>,
    pub header: Rect,
    pub model: Rect,
    pub nav: Rect,
    pub conversation: Rect,
    pub rlcd: Rect,
    pub references: Rect,
    pub documents: Rect,
    pub system: Rect,
    pub prompt: Rect,
    pub input: Rect,
    pub shortcuts: Rect,
}

pub fn choose_mode(width: u16, height: u16) -> LayoutMode {
    if width < 60 || height < 20 {
        LayoutMode::TooSmall
    } else if width < 110 || height < 38 {
        LayoutMode::Compact
    } else if width < 150 || height < 48 {
        LayoutMode::Standard
    } else {
        LayoutMode::Spacious
    }
}

fn inner_rect(area: Rect, margin: u16) -> Rect {
    let width = area.width.saturating_sub(margin.saturating_mul(2));
    let height = area.height.saturating_sub(margin.saturating_mul(2));
    Rect {
        x: area.x.saturating_add(margin),
        y: area.y.saturating_add(margin),
        width,
        height,
    }
}

fn horizontal_split(area: Rect, left_percent: u16, gap: u16) -> (Rect, Rect) {
    if area.width <= gap {
        return (area, Rect::default());
    }
    let usable = area.width.saturating_sub(gap);
    let left = ((usable as u32 * left_percent as u32) / 100) as u16;
    let left = left.max(1).min(usable.saturating_sub(1));
    let right_width = usable.saturating_sub(left);
    (
        Rect {
            x: area.x,
            y: area.y,
            width: left,
            height: area.height,
        },
        Rect {
            x: area.x + left + gap,
            y: area.y,
            width: right_width,
            height: area.height,
        },
    )
}

fn vertical_slice(area: Rect, y: &mut u16, height: u16) -> Rect {
    let remaining = area.height.saturating_sub(y.saturating_sub(area.y));
    let height = height.min(remaining);
    let rect = Rect {
        x: area.x,
        y: *y,
        width: area.width,
        height,
    };
    *y = y.saturating_add(height);
    rect
}

fn vertical_split(area: Rect, top_height: u16, gap: u16) -> (Rect, Rect) {
    let top_height = top_height.min(area.height);
    let top = Rect {
        height: top_height,
        ..area
    };
    let bottom_height = area.height.saturating_sub(top_height).saturating_sub(gap);
    let bottom = Rect {
        y: area.y + top_height + gap,
        height: bottom_height,
        ..area
    };
    (top, bottom)
}

pub fn compute(area: Rect) -> LayoutRects {
    let mode = choose_mode(area.width, area.height);
    let mut rects = LayoutRects {
        mode: Some(mode),
        ..LayoutRects::default()
    };
    if mode == LayoutMode::TooSmall {
        return rects;
    }

    if mode == LayoutMode::Compact {
        let margin = if area.width >= 80 && area.height >= 24 {
            1
        } else {
            0
        };
        let inner = inner_rect(area, margin);
        let header_height: u16 = if inner.height >= 30 {
            8
        } else if inner.height >= 22 {
            6
        } else {
            4
        };
        let nav_height: u16 = if inner.height >= 24 { 2 } else { 1 };
        let gap: u16 = if inner.height >= 22 { 1 } else { 0 };
        let input_height = 3;
        let fixed = header_height
            .saturating_add(nav_height)
            .saturating_add(input_height)
            .saturating_add(gap.saturating_mul(2));
        let main_height = inner.height.saturating_sub(fixed).max(1);
        let mut y = inner.y;
        rects.header = vertical_slice(inner, &mut y, header_height);
        rects.nav = vertical_slice(inner, &mut y, nav_height);
        y = y.saturating_add(gap);
        let main = vertical_slice(inner, &mut y, main_height);
        y = y.saturating_add(gap);
        rects.input = vertical_slice(inner, &mut y, input_height);
        rects.conversation = main;
        let (prompt, rest) = horizontal_split(rects.input, 3, 0);
        rects.prompt = prompt;
        rects.input = rest;
        rects.shortcuts = Rect::default();
        return rects;
    }

    let margin = 1;
    let inner = inner_rect(area, margin);
    let header_height: u16 = if inner.height >= 54 {
        14
    } else if inner.height >= 44 {
        10
    } else {
        8
    };
    let nav_height = 2;
    let input_height = 3;
    let fixed = header_height
        .saturating_add(nav_height)
        .saturating_add(input_height)
        .saturating_add(2);
    let main_height = inner.height.saturating_sub(fixed).max(1);

    let mut y = inner.y;
    rects.header = vertical_slice(inner, &mut y, header_height);
    rects.nav = vertical_slice(inner, &mut y, nav_height);
    y = y.saturating_add(1);
    let main = vertical_slice(inner, &mut y, main_height);
    y = y.saturating_add(1);
    rects.input = vertical_slice(inner, &mut y, input_height);

    let (left_header, right_header) = horizontal_split(rects.header, 60, 1);
    rects.header = left_header;
    rects.model = right_header;

    rects.conversation = main;
    rects.rlcd = Rect::default();
    rects.references = Rect::default();
    rects.documents = Rect::default();
    rects.system = Rect::default();

    let (prompt, rest) = horizontal_split(rects.input, 3, 0);
    rects.prompt = prompt;
    rects.input = rest;
    rects.shortcuts = Rect::default();
    rects
}

#[cfg(test)]
mod tests {
    use super::*;

    fn non_zero(rects: &[Rect]) -> Vec<Rect> {
        rects
            .iter()
            .copied()
            .filter(|rect| rect.width > 0 && rect.height > 0)
            .collect()
    }

    fn assert_inside(outer: Rect, inner: Rect) {
        assert!(inner.x >= outer.x, "{inner:?} starts before {outer:?}");
        assert!(inner.y >= outer.y, "{inner:?} starts above {outer:?}");
        assert!(
            inner.x.saturating_add(inner.width) <= outer.x.saturating_add(outer.width),
            "{inner:?} exceeds {outer:?}"
        );
        assert!(
            inner.y.saturating_add(inner.height) <= outer.y.saturating_add(outer.height),
            "{inner:?} exceeds {outer:?}"
        );
    }

    #[test]
    fn modes_are_selected_at_documented_thresholds() {
        assert_eq!(choose_mode(59, 60), LayoutMode::TooSmall);
        assert_eq!(choose_mode(60, 19), LayoutMode::TooSmall);
        assert_eq!(choose_mode(80, 24), LayoutMode::Compact);
        assert_eq!(choose_mode(120, 40), LayoutMode::Standard);
        assert_eq!(choose_mode(180, 60), LayoutMode::Spacious);
    }

    #[test]
    fn regions_stay_inside_and_do_not_overlap() {
        for (width, height) in [(180, 60), (160, 50), (130, 42), (100, 32), (72, 22)] {
            let area = Rect::new(0, 0, width, height);
            let rects = compute(area);
            let all = vec![
                rects.header,
                rects.model,
                rects.nav,
                rects.conversation,
                rects.rlcd,
                rects.references,
                rects.documents,
                rects.system,
                rects.prompt,
                rects.input,
                rects.shortcuts,
            ];
            for rect in non_zero(&all) {
                assert_inside(area, rect);
            }
            if rects.mode != Some(LayoutMode::TooSmall) {
                let mut checked: Vec<Rect> = Vec::new();
                for rect in non_zero(&all) {
                    for other in &checked {
                        let intersection = rect.intersection(*other);
                        assert!(
                            intersection.width == 0 || intersection.height == 0,
                            "regions overlap at {width}x{height}: {rect:?} and {other:?}"
                        );
                    }
                    checked.push(rect);
                }
                assert!(rects.input.height > 0, "input hidden at {width}x{height}");
            }
        }
    }

    #[test]
    fn compact_mode_does_not_render_sidebar() {
        let rects = compute(Rect::new(0, 0, 90, 30));
        assert_eq!(rects.mode, Some(LayoutMode::Compact));
        assert_eq!(rects.rlcd.width, 0);
        assert_eq!(rects.documents.width, 0);
        assert!(rects.conversation.height > 0);
    }

    #[test]
    fn too_small_is_safe() {
        let rects = compute(Rect::new(0, 0, 40, 12));
        assert_eq!(rects.mode, Some(LayoutMode::TooSmall));
        assert_eq!(rects.conversation.width, 0);
    }
}
