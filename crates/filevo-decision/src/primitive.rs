//! Decision primitives: Choice, Score, and Noul.
//!
//! Implements structured, typed outputs for parallel evaluation.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Result of evaluating a structured decision primitive.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type")]
pub enum DecisionResult {
    /// Choice: Discrete selection among mutually exclusive alternatives.
    Choice {
        id: String,
        selected_option: String,
        choice_index: usize,
        probabilities: HashMap<String, f32>,
        confidence: f32,
    },
    /// Score: Evaluation along an ordered descriptive rubric.
    Score {
        id: String,
        score_value: f32,
        probabilities: Vec<f32>,
        confidence: f32,
    },
    /// Noul: Binary proposition probability P(Yes) in [0.0, 1.0].
    /// Does not carry a separate confidence field; probability indicates strength.
    Noul {
        id: String,
        probability: f32,
    },
}

impl DecisionResult {
    pub fn id(&self) -> &str {
        match self {
            Self::Choice { id, .. } | Self::Score { id, .. } | Self::Noul { id, .. } => id,
        }
    }

    pub fn as_choice(&self) -> Option<(&str, usize, f32)> {
        match self {
            Self::Choice {
                selected_option,
                choice_index,
                confidence,
                ..
            } => Some((selected_option.as_str(), *choice_index, *confidence)),
            _ => None,
        }
    }

    pub fn as_score(&self) -> Option<(f32, f32)> {
        match self {
            Self::Score {
                score_value,
                confidence,
                ..
            } => Some((*score_value, *confidence)),
            _ => None,
        }
    }

    pub fn as_noul(&self) -> Option<f32> {
        match self {
            Self::Noul { probability, .. } => Some(*probability),
            _ => None,
        }
    }

    pub fn is_noul_true(&self, threshold: f32) -> bool {
        match self {
            Self::Noul { probability, .. } => *probability >= threshold,
            _ => false,
        }
    }
}
