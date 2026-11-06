//! DocumentSpec Compiler.
//!
//! Compiles structured DecisionResults and DesignProfiles into a validated DocumentSpec.

use crate::spec::*;
use crate::validator::{SpecValidator, ValidationError};
use filevo_decision::{DecisionResult, DesignProfile};
use std::collections::HashMap;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum CompileError {
    #[error("Validation failed during compilation: {0}")]
    Validation(#[from] ValidationError),
    #[error("Compilation error: {0}")]
    General(String),
}

pub struct SpecCompiler;

impl SpecCompiler {
    pub fn compile(
        decisions: &[DecisionResult],
        profile: DesignProfile,
    ) -> Result<DocumentSpec, CompileError> {
        let mut choice_map: HashMap<&str, &str> = HashMap::new();
        let mut noul_map: HashMap<&str, f32> = HashMap::new();

        for d in decisions {
            match d {
                DecisionResult::Choice { id, selected_option, .. } => {
                    choice_map.insert(id.as_str(), selected_option.as_str());
                }
                DecisionResult::Score { id: _, score_value: _, .. } => {
                    // Score values can map to continuous properties
                }
                DecisionResult::Noul { id, probability } => {
                    noul_map.insert(id.as_str(), *probability);
                }
            }
        }

        // 1. Geometry Compilation
        let paper = choice_map.get("page_geometry:paper_size").copied().unwrap_or("Letter");
        let orient_str = choice_map.get("page_geometry:orientation").copied().unwrap_or("Portrait");
        let orientation = match orient_str {
            "Landscape" => PageOrientation::Landscape,
            _ => PageOrientation::Portrait,
        };

        let (mut w_twips, mut h_twips, paper_format) = match paper {
            "A4" => (11906, 16838, PaperFormat::A4),
            "Legal" => (12240, 20160, PaperFormat::Legal),
            _ => (12240, 15840, PaperFormat::Letter),
        };

        if orientation == PageOrientation::Landscape {
            std::mem::swap(&mut w_twips, &mut h_twips);
        }

        let margin_choice = choice_map.get("page_geometry:margins").copied().unwrap_or("Standard");
        let margin_twips = match margin_choice {
            "Compact" => 1080,  // 0.75 in
            "Spacious" => 1800, // 1.25 in
            _ => 1440,          // 1.0 in
        };

        let col_choice = choice_map.get("page_geometry:column_count").copied().unwrap_or("1");
        let column_count = if col_choice == "2" { 2 } else { 1 };

        let geometry = PageGeometrySpec {
            paper_size: paper.to_string(),
            format: paper_format,
            orientation,
            width_twips: w_twips,
            height_twips: h_twips,
            top_margin_twips: margin_twips,
            bottom_margin_twips: margin_twips,
            left_margin_twips: margin_twips,
            right_margin_twips: margin_twips,
            column_count,
            gutter_twips: 0,
        };

        // 2. Typography Compilation
        let body_font = choice_map.get("typography:body_font").copied().unwrap_or("Aptos");
        let heading_font = choice_map.get("typography:heading_font").copied().unwrap_or("Aptos Display");
        let code_font = choice_map.get("typography:code_font").copied().unwrap_or("Consolas");

        let body_size_str = choice_map.get("typography:body_size").copied().unwrap_or("11pt");
        let body_size_half_points = match body_size_str {
            "10pt" => 20,
            "12pt" => 24,
            _ => 22, // 11pt
        };

        let line_spacing_str = choice_map.get("typography:line_spacing").copied().unwrap_or("1.15");
        let (line_spacing_twips, line_spacing_mode) = match line_spacing_str {
            "1.0" => (240, LineSpacingMode::Single),
            "1.5" => (360, LineSpacingMode::OnePointFive),
            _ => (276, LineSpacingMode::OnePointOneFive),
        };

        let typography = TypographySpec {
            body_font: body_font.to_string(),
            heading_font: heading_font.to_string(),
            code_font: code_font.to_string(),
            body_size_half_points,
            line_spacing_twips,
            line_spacing_mode,
            font_color: "334155".to_string(),
            font_fallback: "Arial, sans-serif".to_string(),
        };

        // 3. Paragraphs Compilation
        let align = choice_map.get("paragraphs:alignment").copied().unwrap_or("Left");
        let align_mode = match align {
            "Justified" => HorizontalAlignment::Justified,
            "Center" => HorizontalAlignment::Center,
            "Right" => HorizontalAlignment::Right,
            _ => HorizontalAlignment::Left,
        };

        let widow_orphan = noul_map.get("paragraphs:widow_orphan_control").copied().unwrap_or(1.0) >= 0.5;

        let paragraphs = ParagraphFormattingSpec {
            alignment: align.to_string(),
            align_mode,
            space_before_twips: 0,
            space_after_twips: 140,
            first_line_indent_twips: if align == "Justified" { 360 } else { 0 },
            widow_orphan_control: widow_orphan,
            keep_with_next: false,
            keep_lines_together: false,
        };

        // 4. Visual Identity Compilation
        let primary = choice_map.get("visual:primary_accent").copied().unwrap_or("1F4E79");
        let visual = VisualIdentitySpec {
            primary_accent: primary.to_string(),
            secondary_accent: "64748B".to_string(),
            neutral_dark: "0F172A".to_string(),
            neutral_light: "F8FAFC".to_string(),
            background_fill: "FFFFFF".to_string(),
            border_color: "CBD5E1".to_string(),
            density: "Standard".to_string(),
            density_mode: LayoutDensity::Standard,
        };

        // 5. Headings Hierarchy Compilation
        let h1_size_str = choice_map.get("headings:h1_size").copied().unwrap_or("16pt");
        let h1_sz = match h1_size_str {
            "18pt" => 36,
            "20pt" => 40,
            _ => 32, // 16pt
        };

        let h2_size_str = choice_map.get("headings:h2_size").copied().unwrap_or("14pt");
        let h2_sz = match h2_size_str {
            "13pt" => 26,
            "15pt" => 30,
            _ => 28, // 14pt
        };

        let keep_next = noul_map.get("headings:keep_with_next").copied().unwrap_or(1.0) >= 0.5;

        let mut levels = Vec::new();
        // H1
        levels.push(HeadingLevelStyle {
            level: 1,
            font_family: heading_font.to_string(),
            size_half_points: h1_sz,
            bold: true,
            italic: false,
            color: primary.to_string(),
            space_before_twips: 280,
            space_after_twips: 140,
            keep_with_next: keep_next,
            page_break_before: false,
            numbering: true,
            border_bottom: true,
        });
        // H2
        levels.push(HeadingLevelStyle {
            level: 2,
            font_family: heading_font.to_string(),
            size_half_points: h2_sz,
            bold: true,
            italic: false,
            color: "334155".to_string(),
            space_before_twips: 200,
            space_after_twips: 100,
            keep_with_next: keep_next,
            page_break_before: false,
            numbering: true,
            border_bottom: false,
        });
        // H3
        levels.push(HeadingLevelStyle {
            level: 3,
            font_family: heading_font.to_string(),
            size_half_points: 24, // 12pt
            bold: true,
            italic: false,
            color: "475569".to_string(),
            space_before_twips: 160,
            space_after_twips: 80,
            keep_with_next: keep_next,
            page_break_before: false,
            numbering: false,
            border_bottom: false,
        });
        // H4-H6
        for lvl in 4..=6 {
            levels.push(HeadingLevelStyle {
                level: lvl,
                font_family: heading_font.to_string(),
                size_half_points: 22, // 11pt
                bold: true,
                italic: lvl % 2 == 1,
                color: "64748B".to_string(),
                space_before_twips: 120,
                space_after_twips: 60,
                keep_with_next: keep_next,
                page_break_before: false,
                numbering: false,
                border_bottom: false,
            });
        }

        let headings = HeadingHierarchySpec {
            title_size_half_points: 48, // 24pt
            title_color: "0F172A".to_string(),
            h1_size_half_points: h1_sz,
            h1_color: primary.to_string(),
            h1_spacing_before_twips: 280,
            h1_spacing_after_twips: 140,
            h2_size_half_points: h2_sz,
            h2_color: "334155".to_string(),
            h2_spacing_before_twips: 200,
            h2_spacing_after_twips: 100,
            levels,
        };

        // 6. Tables Compilation
        let tbl_style = choice_map.get("tables:border_style").copied().unwrap_or("HorizontalRulesOnly");
        let tbl_style_enum = match tbl_style {
            "MinimalGrid" => TableBorderStyle::MinimalGrid,
            "FullGrid" => TableBorderStyle::FullGrid,
            "Borderless" => TableBorderStyle::Borderless,
            _ => TableBorderStyle::HorizontalRulesOnly,
        };

        let zebra_prob = noul_map.get("tables:zebra_shading").copied().unwrap_or(0.5);
        let repeat_hdr = noul_map.get("tables:repeat_header").copied().unwrap_or(1.0) >= 0.5;
        let cant_split = noul_map.get("tables:cant_split").copied().unwrap_or(1.0) >= 0.5;

        let tables = TableSpec {
            border_style: tbl_style.to_string(),
            border_style_enum: tbl_style_enum,
            border_color: "CBD5E1".to_string(),
            zebra_shading: zebra_prob >= 0.5,
            zebra_fill_color: "F8FAFC".to_string(),
            header_fill_color: "F1F5F9".to_string(),
            repeat_header_row: repeat_hdr,
            cant_split,
            cell_padding_top_twips: 120,
            cell_padding_bottom_twips: 120,
            cell_padding_left_twips: 180,
            cell_padding_right_twips: 180,
            vertical_alignment: CellVerticalAlignment::Top,
        };

        // 7. Figures Compilation
        let figures = FigureSpec {
            default_width_inches: 5.5,
            default_height_inches: None,
            caption_position: "Below".to_string(),
            caption_position_enum: CaptionPosition::Below,
            caption_italic: true,
            alignment: ImageAlignment::Center,
            border: false,
        };

        // 8. Headers & Footers
        let diff_first = noul_map.get("headers_footers:different_first_page").copied().unwrap_or(1.0) >= 0.5;
        let inc_page_num = noul_map.get("headers_footers:include_page_numbers").copied().unwrap_or(1.0) >= 0.5;

        let headers_footers = HeaderFooterSpec {
            different_first_page: diff_first,
            include_page_numbers: inc_page_num,
            header_left_text: "".to_string(),
            header_right_text: "Filevo Autonomous Document Intelligence".to_string(),
            footer_left_text: "".to_string(),
            footer_center_text: "Filevo Autonomous Document Intelligence".to_string(),
            footer_right_text: "Page {PAGE} of {NUMPAGES}".to_string(),
        };

        // 9. Navigation
        let toc_prob = noul_map.get("navigation:include_toc").copied().unwrap_or(0.5);
        let navigation = NavigationSpec {
            include_toc: toc_prob >= 0.5,
            toc_depth: 3,
            section_numbering: true,
        };

        let archetype_name = match profile {
            DesignProfile::AcademicMonograph => "Academic Monograph",
            DesignProfile::TechnicalReport => "Technical Report",
            DesignProfile::ExecutiveSummary => "Executive Summary",
            DesignProfile::MinimalistModern => "Technical Report",
            DesignProfile::ResearchPublication => "Academic Monograph",
        };

        let spec = DocumentSpec {
            archetype: archetype_name.to_string(),
            geometry,
            typography,
            paragraphs,
            headings,
            visual,
            tables,
            figures,
            headers_footers,
            navigation,
        };

        // Validate Invariants
        SpecValidator::validate(&spec)?;

        Ok(spec)
    }
}
