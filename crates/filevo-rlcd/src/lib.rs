//! RLCD tree policy for Filevo.
//!
//! A Jev-style probabilistic program over three primitives (Noul, Choice,
//! Score) that walks a knowledge tree and decides what to put in a document
//! and how much of it. See `planner.rs` for the decision tree and `policy.rs`
//! for the maths. Python reaches it through the `filevo_rlcd` extension
//! module (feature `python`); everything crosses the boundary as JSON.

pub mod planner;
pub mod policy;

pub use planner::{plan, PlanRequest, PlanResult, PlannedTopic};
pub use policy::{Family, Features, Policy, Step, UpdateStats};

use std::collections::HashMap;
use std::path::Path;

pub fn load_policy(path: &Path) -> Result<Policy, String> {
    match std::fs::read_to_string(path) {
        Ok(s) => serde_json::from_str(&s).map_err(|e| format!("bad policy file {}: {e}", path.display())),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Policy::default()),
        Err(e) => Err(e.to_string()),
    }
}

pub fn save_policy(policy: &Policy, path: &Path) -> Result<(), String> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    }
    let tmp = path.with_extension("json.tmp");
    let body = serde_json::to_string_pretty(policy).map_err(|e| e.to_string())?;
    std::fs::write(&tmp, body).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, path).map_err(|e| e.to_string())
}

pub fn parse_prior(json: &str) -> Result<HashMap<String, Family>, String> {
    serde_json::from_str(json).map_err(|e| format!("bad prior: {e}"))
}

#[cfg(feature = "python")]
mod python {
    use super::*;
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    #[pyclass(name = "TreePolicy")]
    pub struct PyTreePolicy {
        inner: Policy,
    }

    fn err(e: impl ToString) -> PyErr {
        PyValueError::new_err(e.to_string())
    }

    #[pymethods]
    impl PyTreePolicy {
        #[new]
        fn new() -> Self {
            PyTreePolicy { inner: Policy::default() }
        }

        /// Load from a JSON file; a missing file gives a fresh policy.
        #[staticmethod]
        fn load(path: &str) -> PyResult<Self> {
            Ok(PyTreePolicy { inner: load_policy(Path::new(path)).map_err(err)? })
        }

        fn save(&self, path: &str) -> PyResult<()> {
            save_policy(&self.inner, Path::new(path)).map_err(err)
        }

        fn apply_prior(&mut self, prior_json: &str) -> PyResult<()> {
            self.inner.apply_prior(&parse_prior(prior_json).map_err(err)?);
            Ok(())
        }

        /// Plan a document. Takes and returns JSON (see `PlanRequest` / `PlanResult`).
        fn plan(&self, py: Python<'_>, request_json: &str) -> PyResult<String> {
            let req: PlanRequest = serde_json::from_str(request_json).map_err(err)?;
            let policy = &self.inner;
            let out = py.allow_threads(|| plan(policy, &req));
            serde_json::to_string(&out).map_err(err)
        }

        /// Apply one REINFORCE update from a trajectory returned by `plan`.
        fn update(&mut self, trajectory_json: &str, reward: f32) -> PyResult<String> {
            let traj: Vec<Step> = serde_json::from_str(trajectory_json).map_err(err)?;
            let stats = self.inner.update(&traj, reward.clamp(-1.0, 1.0));
            serde_json::to_string(&stats).map_err(err)
        }

        fn fit_temperature(&mut self, family: &str, samples_json: &str) -> PyResult<f32> {
            let samples: Vec<(Vec<f32>, usize)> = serde_json::from_str(samples_json).map_err(err)?;
            Ok(self.inner.fit_temperature(family, &samples))
        }

        fn noul_prob(&self, family: &str, features_json: &str) -> PyResult<f32> {
            let x: Features = serde_json::from_str(features_json).map_err(err)?;
            Ok(self.inner.noul_prob(family, &x))
        }

        fn to_json(&self) -> PyResult<String> {
            serde_json::to_string(&self.inner).map_err(err)
        }

        #[staticmethod]
        fn from_json(json: &str) -> PyResult<Self> {
            Ok(PyTreePolicy { inner: serde_json::from_str(json).map_err(err)? })
        }

        #[getter]
        fn episodes(&self) -> u64 {
            self.inner.episodes
        }

        #[getter]
        fn baseline(&self) -> f32 {
            self.inner.baseline
        }
    }

    #[pymodule]
    fn filevo_rlcd(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_class::<PyTreePolicy>()?;
        m.add("__version__", env!("CARGO_PKG_VERSION"))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn feats(pairs: &[(&str, f32)]) -> Features {
        pairs.iter().map(|(k, v)| (k.to_string(), *v)).collect()
    }

    fn topic(id: i64, relevance: f32, n_facts: usize, children: Vec<planner::TopicIn>) -> planner::TopicIn {
        planner::TopicIn {
            id,
            cost: 5.0,
            features: feats(&[("relevance", relevance)]),
            facts: (0..n_facts)
                .map(|i| planner::FactIn {
                    id: id * 100 + i as i64,
                    kind: "definition".into(),
                    cost: 40.0,
                    features: feats(&[("relevance", relevance)]),
                })
                .collect(),
            children,
        }
    }

    fn request(candidates: Vec<planner::TopicIn>, budget: f32) -> PlanRequest {
        PlanRequest {
            global: BTreeMap::new(),
            genres: vec![],
            themes: vec![],
            candidates,
            budget_words: budget,
            hard_cap_ratio: 1.15,
            max_depth: 3,
            detail_levels: 3,
            gates: vec!["include_toc".into()],
            seed: 7,
            greedy: true,
        }
    }

    fn policy_with(prior: &[(&str, &[(&str, f32)])]) -> Policy {
        let mut p = Policy::default();
        let mut map = HashMap::new();
        for (fam, w) in prior {
            map.insert(
                fam.to_string(),
                Family { weights: w.iter().map(|(k, v)| (k.to_string(), *v)).collect(), ..Default::default() },
            );
        }
        p.apply_prior(&map);
        p
    }

    #[test]
    fn excluded_parent_skips_children() {
        let pol = policy_with(&[
            ("include_topic", &[("relevance", 10.0), ("bias", -5.0)]),
            ("expand_children", &[("bias", 10.0)]),
            ("include_fact", &[("bias", 10.0)]),
        ]);
        let child = topic(2, 1.0, 1, vec![]);
        let parent = topic(1, 0.0, 1, vec![child]);
        let out = plan(&pol, &request(vec![parent], 1000.0));
        assert!(out.topics.is_empty(), "parent with low relevance must be excluded");
        // Only the parent's include_topic decision plus the gate were taken.
        let topic_steps = out
            .trajectory
            .iter()
            .filter(|s| matches!(s, Step::Noul { family, .. } if family == "include_topic"))
            .count();
        assert_eq!(topic_steps, 1, "children of an excluded topic are never visited");
    }

    #[test]
    fn budget_stops_expansion() {
        let pol = policy_with(&[
            ("include_topic", &[("bias", 10.0)]),
            ("expand_children", &[("bias", 10.0)]),
            ("include_fact", &[("bias", 10.0)]),
        ]);
        let cands: Vec<_> = (1..=10).map(|i| topic(i, 1.0, 5, vec![])).collect();
        let out = plan(&pol, &request(cands, 300.0));
        assert!(out.words_planned <= 300.0 * 1.15 + 1e-3, "planned {} words", out.words_planned);
        assert!(out.topics.len() < 10);
    }

    #[test]
    fn same_seed_same_plan() {
        let pol = Policy::default();
        let mut req = request((1..=6).map(|i| topic(i, 0.5, 3, vec![topic(i * 10, 0.5, 2, vec![])])).collect(), 900.0);
        req.greedy = false;
        let a = plan(&pol, &req);
        let b = plan(&pol, &req);
        assert_eq!(serde_json::to_string(&a.topics).unwrap(), serde_json::to_string(&b.topics).unwrap());
        req.seed = 99;
        let c = plan(&pol, &req);
        assert_eq!(a.decisions > 0, c.decisions > 0);
    }

    #[test]
    fn positive_reward_raises_chosen_gate() {
        let mut pol = Policy::default();
        let x = feats(&[("bias", 1.0), ("relevance", 1.0)]);
        let before = pol.noul_prob("include_topic", &x);
        let traj = vec![Step::Noul { family: "include_topic".into(), x: x.clone(), p: before, chosen: true }];
        let stats = pol.update(&traj, 1.0);
        assert!(stats.advantage > 0.0);
        assert!(pol.noul_prob("include_topic", &x) > before);
        // Punishing the same choice lowers it again.
        let mid = pol.noul_prob("include_topic", &x);
        pol.baseline = 0.0;
        pol.update(&[Step::Noul { family: "include_topic".into(), x: x.clone(), p: mid, chosen: true }], -1.0);
        assert!(pol.noul_prob("include_topic", &x) < mid);
    }

    #[test]
    fn choice_gradient_moves_toward_rewarded_option() {
        let mut pol = Policy::default();
        let opts = vec![("a".to_string(), feats(&[("sim", 0.2)])), ("b".to_string(), feats(&[("sim", 0.8)]))];
        let (p0, t) = pol.choice_probs("genre", &opts);
        pol.update(&[Step::Choice { family: "genre".into(), options: opts.clone(), probs: p0.clone(), chosen: 1, temperature: t }], 1.0);
        let (p1, _) = pol.choice_probs("genre", &opts);
        assert!(p1[1] > p0[1]);
    }

    #[test]
    fn score_update_shifts_level() {
        let mut pol = Policy::default();
        let x = feats(&[("bias", 1.0)]);
        let p0 = pol.score_probs("detail", &x, 3);
        for _ in 0..50 {
            let p = pol.score_probs("detail", &x, 3);
            pol.update(&[Step::Score { family: "detail".into(), x: x.clone(), probs: p, chosen: 2 }], 1.0);
            pol.baseline = 0.0;
        }
        let p1 = pol.score_probs("detail", &x, 3);
        assert!(p1[2] > p0[2], "deep level should become more likely: {:?} -> {:?}", p0, p1);
        assert!((p1.iter().sum::<f32>() - 1.0).abs() < 1e-4);
    }

    #[test]
    fn save_load_round_trip() {
        let mut pol = Policy::default();
        let x = feats(&[("bias", 1.0)]);
        pol.update(&[Step::Noul { family: "include_fact".into(), x: x.clone(), p: 0.5, chosen: true }], 0.7);
        let dir = std::env::temp_dir().join(format!("filevo_rlcd_test_{}", std::process::id()));
        let path = dir.join("policy.json");
        save_policy(&pol, &path).unwrap();
        let back = load_policy(&path).unwrap();
        assert_eq!(back.episodes, 1);
        assert!((back.noul_prob("include_fact", &x) - pol.noul_prob("include_fact", &x)).abs() < 1e-6);
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn temperature_fit_softens_overconfident_logits() {
        let mut pol = Policy::default();
        // Very confident logits that are right only 60% of the time.
        let mut samples = Vec::new();
        for i in 0..100 {
            samples.push((vec![6.0, 0.0], if i % 5 < 3 { 0 } else { 1 }));
        }
        let t = pol.fit_temperature("genre", &samples);
        assert!(t > 1.5, "expected a softening temperature, got {t}");
    }
}
