//! Decision Schema and Descriptive Metadata definitions.
//!
//! Provides rich, self-documenting schemas for the decision catalogue.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChoiceOption {
    pub id: String,
    pub label: String,
    pub description: String,
    pub visual_characteristics: String,
    pub recommended_when: String,
    pub limitations: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RubricLevel {
    pub value: f32,
    pub label: String,
    pub criteria: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScoreRubric {
    pub scale_min: f32,
    pub scale_max: f32,
    pub levels: Vec<RubricLevel>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NoulCondition {
    pub question: String,
    pub true_condition: String,
    pub false_condition: String,
    pub clarifying_criteria: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum DecisionSchema {
    Choice {
        id: String,
        domain: String,
        description: String,
        options: Vec<ChoiceOption>,
        default_fallback: String,
        dependencies: Vec<String>,
        #[serde(default)]
        selection_criteria: String,
        #[serde(default)]
        constraints: Vec<String>,
    },
    Score {
        id: String,
        domain: String,
        description: String,
        rubric: ScoreRubric,
        default_fallback: f32,
        dependencies: Vec<String>,
        #[serde(default)]
        selection_criteria: String,
        #[serde(default)]
        constraints: Vec<String>,
    },
    Noul {
        id: String,
        domain: String,
        description: String,
        condition: NoulCondition,
        default_fallback: bool,
        dependencies: Vec<String>,
        #[serde(default)]
        selection_criteria: String,
        #[serde(default)]
        constraints: Vec<String>,
    },
}

impl DecisionSchema {
    pub fn id(&self) -> &str {
        match self {
            Self::Choice { id, .. } | Self::Score { id, .. } | Self::Noul { id, .. } => id,
        }
    }

    pub fn domain(&self) -> &str {
        match self {
            Self::Choice { domain, .. } | Self::Score { domain, .. } | Self::Noul { domain, .. } => domain,
        }
    }

    pub fn description(&self) -> &str {
        match self {
            Self::Choice { description, .. }
            | Self::Score { description, .. }
            | Self::Noul { description, .. } => description,
        }
    }

    pub fn dependencies(&self) -> &[String] {
        match self {
            Self::Choice { dependencies, .. }
            | Self::Score { dependencies, .. }
            | Self::Noul { dependencies, .. } => dependencies,
        }
    }

    pub fn selection_criteria(&self) -> &str {
        match self {
            Self::Choice { selection_criteria, .. }
            | Self::Score { selection_criteria, .. }
            | Self::Noul { selection_criteria, .. } => selection_criteria,
        }
    }

    pub fn constraints(&self) -> &[String] {
        match self {
            Self::Choice { constraints, .. }
            | Self::Score { constraints, .. }
            | Self::Noul { constraints, .. } => constraints,
        }
    }
}
