//! Invariant Validator for DocumentSpec.
//!
//! Validates geometric boundaries, color contrast, and font compatibility.

use crate::spec::DocumentSpec;
use thiserror::Error;

#[derive(Error, Debug, PartialEq)]
pub enum ValidationError {
    #[error("Margins exceed printable page dimensions: printable width {0} twips is under minimum 3600 twips (2.5 inches)")]
    InvalidGeometry(u32),
    #[error("Color contrast insufficient: {0} against {1}")]
    InsufficientContrast(String, String),
    #[error("Incompatible font pairing: '{0}' body with '{1}' heading")]
    IncompatibleFontPair(String, String),
}

pub struct SpecValidator;

impl SpecValidator {
    pub fn validate(spec: &DocumentSpec) -> Result<(), ValidationError> {
        // 1. Validate Geometry Invariants (Horizontal and Vertical)
        let total_horiz_margin = spec.geometry.left_margin_twips + spec.geometry.right_margin_twips + spec.geometry.gutter_twips;
        if spec.geometry.width_twips <= total_horiz_margin + 3600 {
            let printable = spec.geometry.width_twips.saturating_sub(total_horiz_margin);
            return Err(ValidationError::InvalidGeometry(printable));
        }

        let total_vert_margin = spec.geometry.top_margin_twips + spec.geometry.bottom_margin_twips;
        if spec.geometry.height_twips <= total_vert_margin + 3600 {
            let printable_h = spec.geometry.height_twips.saturating_sub(total_vert_margin);
            return Err(ValidationError::InvalidGeometry(printable_h));
        }

        // 2. Validate Font Pairings
        let b = spec.typography.body_font.to_lowercase();
        let h = spec.typography.heading_font.to_lowercase();
        if b.contains("times") && h.contains("arial") {
            return Err(ValidationError::IncompatibleFontPair(
                spec.typography.body_font.clone(),
                spec.typography.heading_font.clone(),
            ));
        }

        // 3. Validate Color Contrast
        if let Some(ratio) = calculate_contrast_ratio(&spec.visual.primary_accent, "FFFFFF") {
            if ratio < 3.0 {
                return Err(ValidationError::InsufficientContrast(
                    spec.visual.primary_accent.clone(),
                    "FFFFFF".to_string(),
                ));
            }
        }

        Ok(())
    }
}

fn parse_hex_color(hex: &str) -> Option<(f32, f32, f32)> {
    let clean = hex.trim().trim_start_matches('#');
    if clean.len() != 6 {
        return None;
    }
    let r = u8::from_str_radix(&clean[0..2], 16).ok()?;
    let g = u8::from_str_radix(&clean[2..4], 16).ok()?;
    let b = u8::from_str_radix(&clean[4..6], 16).ok()?;
    Some((r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0))
}

fn relative_luminance(r: f32, g: f32, b: f32) -> f32 {
    let f = |c: f32| {
        if c <= 0.03928 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).powf(2.4)
        }
    };
    0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

fn calculate_contrast_ratio(hex1: &str, hex2: &str) -> Option<f32> {
    let (r1, g1, b1) = parse_hex_color(hex1)?;
    let (r2, g2, b2) = parse_hex_color(hex2)?;
    let l1 = relative_luminance(r1, g1, b1);
    let l2 = relative_luminance(r2, g2, b2);
    let lighter = l1.max(l2);
    let darker = l1.min(l2);
    Some((lighter + 0.05) / (darker + 0.05))
}
