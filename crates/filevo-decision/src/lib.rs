//! Filevo Structured Decision Engine.
//!
//! Provides granular decision catalogue, typed decision primitives (Choice, Score, Noul),
//! baseline design profiles, and parallel evaluation scheduling.

pub mod catalogue;
pub mod engine;
pub mod primitive;
pub mod profiles;
pub mod schema;

pub use catalogue::build_catalogue;
pub use engine::{DecisionEngine, DecisionError};
pub use primitive::DecisionResult;
pub use profiles::DesignProfile;
pub use schema::{ChoiceOption, DecisionSchema, NoulCondition, RubricLevel, ScoreRubric};

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_primitives_representation() {
        let choice = DecisionResult::Choice {
            id: "typography:body_font".into(),
            selected_option: "Georgia".into(),
            choice_index: 2,
            probabilities: HashMap::new(),
            confidence: 0.95,
        };
        assert_eq!(choice.id(), "typography:body_font");
        let (opt, idx, conf) = choice.as_choice().unwrap();
        assert_eq!(opt, "Georgia");
        assert_eq!(idx, 2);
        assert!((conf - 0.95).abs() < 1e-4);

        let noul = DecisionResult::Noul {
            id: "navigation:include_toc".into(),
            probability: 0.88,
        };
        assert_eq!(noul.id(), "navigation:include_toc");
        assert!(noul.is_noul_true(0.5));
    }

    #[test]
    fn test_parallel_decision_evaluation() {
        let engine = DecisionEngine::new();
        let overrides = HashMap::new();
        let results = engine
            .evaluate("Technical Report on Plant Root Systems", DesignProfile::TechnicalReport, &overrides)
            .expect("Evaluation should succeed");

        assert!(results.len() >= 7);
        let ids: Vec<&str> = results.iter().map(|r| r.id()).collect();
        assert!(ids.contains(&"page_geometry:paper_size"));
        assert!(ids.contains(&"typography:body_font"));
        assert!(ids.contains(&"typography:heading_font"));
        assert!(ids.contains(&"tables:border_style"));
    }

    #[test]
    fn test_font_pairing_dependency_resolution() {
        let engine = DecisionEngine::new();
        let mut overrides = HashMap::new();
        overrides.insert("typography:body_font".into(), "Times New Roman".into());

        let results = engine
            .evaluate("Academic Monograph", DesignProfile::AcademicMonograph, &overrides)
            .expect("Evaluation should succeed");

        let heading_res = results.iter().find(|r| r.id() == "typography:heading_font").unwrap();
        let (heading_font, _, _) = heading_res.as_choice().unwrap();
        // Times New Roman body pairs with Georgia heading
        assert_eq!(heading_font, "Georgia");
    }

    #[test]
    fn test_dag_validation_and_granularity() {
        let engine = DecisionEngine::new();
        assert!(engine.validate_dependency_graph().is_ok());

        let results = engine
            .evaluate("Systems Specification", DesignProfile::TechnicalReport, &HashMap::new())
            .unwrap();

        let h2_res = results.iter().find(|r| r.id() == "headings:h2_size").unwrap();
        let (h2_size, _, _) = h2_res.as_choice().unwrap();
        assert_eq!(h2_size, "14pt");

        let kw_res = results.iter().find(|r| r.id() == "headings:keep_with_next").unwrap();
        assert!(kw_res.is_noul_true(0.5));
    }
}
