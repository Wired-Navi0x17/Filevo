//! DocumentSpec: How the document looks (Presentation Specification).
//!
//! Strongly-typed, fully validated configuration controlling geometry,
//! typography, headings, tables, visual identity, and headers/footers.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum PaperFormat {
    Letter,
    A4,
    Legal,
    A3,
    A5,
    Custom,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum PageOrientation {
    Portrait,
    Landscape,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum HorizontalAlignment {
    Left,
    Center,
    Right,
    Justified,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum LineSpacingMode {
    Single,
    OnePointOneFive,
    OnePointFive,
    Double,
    Exact(u32),
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum TableBorderStyle {
    HorizontalRulesOnly,
    MinimalGrid,
    FullGrid,
    Borderless,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum CellVerticalAlignment {
    Top,
    Center,
    Bottom,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum ImageAlignment {
    Left,
    Center,
    Right,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum CaptionPosition {
    Above,
    Below,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum LayoutDensity {
    Compact,
    Standard,
    Spacious,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeadingLevelStyle {
    pub level: usize,
    pub font_family: String,
    pub size_half_points: u32,
    pub bold: bool,
    pub italic: bool,
    pub color: String,
    pub space_before_twips: u32,
    pub space_after_twips: u32,
    pub keep_with_next: bool,
    pub page_break_before: bool,
    pub numbering: bool,
    pub border_bottom: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DocumentSpec {
    pub archetype: String,
    pub geometry: PageGeometrySpec,
    pub typography: TypographySpec,
    pub paragraphs: ParagraphFormattingSpec,
    pub headings: HeadingHierarchySpec,
    pub visual: VisualIdentitySpec,
    pub tables: TableSpec,
    pub figures: FigureSpec,
    pub headers_footers: HeaderFooterSpec,
    pub navigation: NavigationSpec,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PageGeometrySpec {
    pub paper_size: String,
    pub format: PaperFormat,
    pub orientation: PageOrientation,
    pub width_twips: u32,
    pub height_twips: u32,
    pub top_margin_twips: u32,
    pub bottom_margin_twips: u32,
    pub left_margin_twips: u32,
    pub right_margin_twips: u32,
    pub column_count: u8,
    pub gutter_twips: u32,
}

impl PageGeometrySpec {
    pub fn printable_width_twips(&self) -> u32 {
        self.width_twips
            .saturating_sub(self.left_margin_twips + self.right_margin_twips + self.gutter_twips)
    }

    pub fn printable_height_twips(&self) -> u32 {
        self.height_twips
            .saturating_sub(self.top_margin_twips + self.bottom_margin_twips)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TypographySpec {
    pub body_font: String,
    pub heading_font: String,
    pub code_font: String,
    pub body_size_half_points: u32, // 22 = 11pt
    pub line_spacing_twips: u32,    // 276 = 1.15 line pitch
    pub line_spacing_mode: LineSpacingMode,
    pub font_color: String,         // Hex RRGGBB
    pub font_fallback: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ParagraphFormattingSpec {
    pub alignment: String, // Left, Justified, Center
    pub align_mode: HorizontalAlignment,
    pub space_before_twips: u32,
    pub space_after_twips: u32,
    pub first_line_indent_twips: u32,
    pub widow_orphan_control: bool,
    pub keep_with_next: bool,
    pub keep_lines_together: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeadingHierarchySpec {
    pub title_size_half_points: u32, // 48 = 24pt
    pub title_color: String,
    pub h1_size_half_points: u32,    // 32 = 16pt
    pub h1_color: String,
    pub h1_spacing_before_twips: u32,
    pub h1_spacing_after_twips: u32,
    pub h2_size_half_points: u32,    // 28 = 14pt
    pub h2_color: String,
    pub h2_spacing_before_twips: u32,
    pub h2_spacing_after_twips: u32,
    pub levels: Vec<HeadingLevelStyle>,
}

impl HeadingHierarchySpec {
    pub fn style_for_level(&self, level: usize) -> Option<&HeadingLevelStyle> {
        self.levels.iter().find(|l| l.level == level)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct VisualIdentitySpec {
    pub primary_accent: String,
    pub secondary_accent: String,
    pub neutral_dark: String,
    pub neutral_light: String,
    pub background_fill: String,
    pub border_color: String,
    pub density: String, // Compact, Standard, Spacious
    pub density_mode: LayoutDensity,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TableSpec {
    pub border_style: String, // HorizontalRulesOnly, MinimalGrid, FullGrid
    pub border_style_enum: TableBorderStyle,
    pub border_color: String,
    pub zebra_shading: bool,
    pub zebra_fill_color: String,
    pub header_fill_color: String,
    pub repeat_header_row: bool,
    pub cant_split: bool,
    pub cell_padding_top_twips: u32,
    pub cell_padding_bottom_twips: u32,
    pub cell_padding_left_twips: u32,
    pub cell_padding_right_twips: u32,
    pub vertical_alignment: CellVerticalAlignment,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FigureSpec {
    pub default_width_inches: f32,
    pub default_height_inches: Option<f32>,
    pub caption_position: String, // Below, Above
    pub caption_position_enum: CaptionPosition,
    pub caption_italic: bool,
    pub alignment: ImageAlignment,
    pub border: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeaderFooterSpec {
    pub different_first_page: bool,
    pub include_page_numbers: bool,
    pub header_left_text: String,
    pub header_right_text: String,
    pub footer_left_text: String,
    pub footer_center_text: String,
    pub footer_right_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NavigationSpec {
    pub include_toc: bool,
    pub toc_depth: u8,
    pub section_numbering: bool,
}
