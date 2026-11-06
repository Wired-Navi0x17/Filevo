//! Parallel Decision Engine and Dependency Scheduler.

use crate::catalogue::build_catalogue;
use crate::primitive::DecisionResult;
use crate::profiles::DesignProfile;
use crate::schema::DecisionSchema;
use rayon::prelude::*;
use std::collections::HashMap;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum DecisionError {
    #[error("Evaluation error for decision '{0}': {1}")]
    EvaluationFailed(String, String),
    #[error("Unsatisfied dependency: '{0}' requires '{1}'")]
    UnsatisfiedDependency(String, String),
}

pub struct DecisionEngine {
    catalogue: Vec<DecisionSchema>,
}

impl DecisionEngine {
    pub fn new() -> Self {
        Self {
            catalogue: build_catalogue(),
        }
    }

    /// Validates that the decision dependency graph is a valid Directed Acyclic Graph (DAG)
    /// without missing dependencies or circular cycles.
    pub fn validate_dependency_graph(&self) -> Result<(), DecisionError> {
        let all_ids: std::collections::HashSet<&str> = self.catalogue.iter().map(|d| d.id()).collect();

        // Check for missing dependencies
        for schema in &self.catalogue {
            for dep in schema.dependencies() {
                if !all_ids.contains(dep.as_str()) {
                    return Err(DecisionError::UnsatisfiedDependency(
                        schema.id().to_string(),
                        dep.clone(),
                    ));
                }
            }
        }

        // Check for circular dependencies using cycle detection
        let mut visited = HashMap::new(); // 0 = unvisited, 1 = visiting, 2 = visited
        for schema in &self.catalogue {
            visited.insert(schema.id(), 0);
        }

        fn has_cycle<'a>(
            node: &'a str,
            catalogue_map: &HashMap<&'a str, &'a DecisionSchema>,
            visited: &mut HashMap<&'a str, u8>,
        ) -> bool {
            visited.insert(node, 1);
            if let Some(schema) = catalogue_map.get(node) {
                for dep in schema.dependencies() {
                    let dep_str = dep.as_str();
                    let state = visited.get(dep_str).copied().unwrap_or(0);
                    if state == 1 {
                        return true; // Cycle detected
                    }
                    if state == 0 && has_cycle(dep_str, catalogue_map, visited) {
                        return true;
                    }
                }
            }
            visited.insert(node, 2);
            false
        }

        let cat_map: HashMap<&str, &DecisionSchema> = self.catalogue.iter().map(|s| (s.id(), s)).collect();
        for schema in &self.catalogue {
            if visited.get(schema.id()).copied().unwrap_or(0) == 0 {
                if has_cycle(schema.id(), &cat_map, &mut visited) {
                    return Err(DecisionError::EvaluationFailed(
                        schema.id().to_string(),
                        "Circular dependency cycle detected in decision catalogue".to_string(),
                    ));
                }
            }
        }

        Ok(())
    }

    /// Evaluates all decision domains for a given topic and profile.
    ///
    /// Evaluates decisions staged topologically across the dependency DAG:
    /// Independent decisions in each topological tier run in parallel via Rayon.
    /// Dependent decisions resolve deterministically based on their resolved inputs.
    pub fn evaluate(
        &self,
        topic: &str,
        profile: DesignProfile,
        explicit_overrides: &HashMap<String, String>,
    ) -> Result<Vec<DecisionResult>, DecisionError> {
        self.validate_dependency_graph()?;

        let baselines = profile.baseline_decisions();
        let mut resolved_map: HashMap<String, DecisionResult> = HashMap::new();
        let mut remaining: Vec<&DecisionSchema> = self.catalogue.iter().collect();

        // Staged topological resolution loop
        while !remaining.is_empty() {
            // Find all schemas whose dependencies are satisfied by resolved_map
            let (ready, pending): (Vec<&DecisionSchema>, Vec<&DecisionSchema>) = remaining
                .into_iter()
                .partition(|s| s.dependencies().iter().all(|dep| resolved_map.contains_key(dep)));

            if ready.is_empty() {
                let unresolvable = pending.first().map(|s| s.id().to_string()).unwrap_or_default();
                return Err(DecisionError::UnsatisfiedDependency(
                    unresolvable,
                    "Deadlock or unresolvable dependency in decision graph".into(),
                ));
            }

            // Evaluate ready decisions in parallel using Rayon
            let stage_results: Vec<DecisionResult> = ready
                .par_iter()
                .map(|schema| {
                    let id = schema.id();
                    if let Some(val) = explicit_overrides.get(id) {
                        Self::evaluate_choice(schema, val, 1.0)
                    } else if id == "typography:heading_font" {
                        // Font-pairing deterministic compatibility logic
                        let dep_val = schema
                            .dependencies()
                            .first()
                            .and_then(|dep| resolved_map.get(dep))
                            .and_then(|r| r.as_choice())
                            .map(|(opt, _, _)| opt)
                            .unwrap_or("Aptos");

                        let chosen = match dep_val {
                            "Times New Roman" => "Georgia",
                            "Georgia" => "Georgia",
                            "Calibri" => "Aptos Display",
                            _ => "Aptos Display",
                        };
                        Self::evaluate_choice(schema, chosen, 0.95)
                    } else if id == "headings:h2_size" {
                        // Proportional heading size rule
                        let h1_val = schema
                            .dependencies()
                            .first()
                            .and_then(|dep| resolved_map.get(dep))
                            .and_then(|r| r.as_choice())
                            .map(|(opt, _, _)| opt)
                            .unwrap_or("16pt");

                        let chosen = match h1_val {
                            "18pt" | "20pt" => "14pt",
                            "16pt" => "14pt",
                            _ => "13pt",
                        };
                        Self::evaluate_choice(schema, chosen, 0.95)
                    } else if let Some(val) = baselines.get(id) {
                        Self::evaluate_choice(schema, val, 0.95)
                    } else {
                        Self::evaluate_default(schema)
                    }
                })
                .collect();

            for res in stage_results {
                resolved_map.insert(res.id().to_string(), res);
            }

            remaining = pending;
        }

        // Add contextual Noul decisions based on topic & profile if not overridden
        let t_lower = topic.to_lowercase();
        let zebra_prob = if explicit_overrides.contains_key("tables:zebra_shading") {
            let ov = explicit_overrides.get("tables:zebra_shading").unwrap();
            if ov == "true" { 0.95 } else { 0.05 }
        } else if t_lower.contains("data") || t_lower.contains("report") || t_lower.contains("spec") {
            0.85
        } else {
            0.40
        };
        resolved_map.insert(
            "tables:zebra_shading".into(),
            DecisionResult::Noul {
                id: "tables:zebra_shading".into(),
                probability: zebra_prob,
            },
        );

        let toc_prob = if explicit_overrides.contains_key("navigation:include_toc") {
            let ov = explicit_overrides.get("navigation:include_toc").unwrap();
            if ov == "true" { 0.95 } else { 0.05 }
        } else if profile == DesignProfile::ExecutiveSummary {
            0.10
        } else {
            0.90
        };
        resolved_map.insert(
            "navigation:include_toc".into(),
            DecisionResult::Noul {
                id: "navigation:include_toc".into(),
                probability: toc_prob,
            },
        );

        let mut results: Vec<DecisionResult> = resolved_map.into_values().collect();
        results.sort_by(|a, b| a.id().cmp(b.id()));
        Ok(results)
    }

    fn evaluate_choice(schema: &DecisionSchema, selected: &str, confidence: f32) -> DecisionResult {
        let (id, opts) = match schema {
            DecisionSchema::Choice { id, options, .. } => (id.clone(), options),
            _ => (schema.id().to_string(), &vec![]),
        };

        let idx = opts.iter().position(|o| o.id == selected).unwrap_or(0);
        let mut probs = HashMap::new();
        for (i, opt) in opts.iter().enumerate() {
            let p = if i == idx { confidence } else { (1.0 - confidence) / (opts.len().max(2) - 1) as f32 };
            probs.insert(opt.id.clone(), p);
        }

        DecisionResult::Choice {
            id,
            selected_option: selected.to_string(),
            choice_index: idx,
            probabilities: probs,
            confidence,
        }
    }

    fn evaluate_default(schema: &DecisionSchema) -> DecisionResult {
        match schema {
            DecisionSchema::Choice { id: _, default_fallback, options: _, .. } => {
                Self::evaluate_choice(schema, default_fallback, 0.85)
            }
            DecisionSchema::Score { id, default_fallback, rubric: _, .. } => DecisionResult::Score {
                id: id.clone(),
                score_value: *default_fallback,
                probabilities: vec![1.0],
                confidence: 0.90,
            },
            DecisionSchema::Noul { id, default_fallback, .. } => DecisionResult::Noul {
                id: id.clone(),
                probability: if *default_fallback { 0.85 } else { 0.15 },
            },
        }
    }
}
