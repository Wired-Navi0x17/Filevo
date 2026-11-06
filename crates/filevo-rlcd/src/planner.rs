//! The decision tree walked over the knowledge tree.
//!
//! ```text
//! Choice genre            over the genre files Python passes in
//! Choice theme            over the theme files
//! for each candidate topic (and recursively its children):
//!     Noul  include_topic?          -- children are only visited when yes
//!       Score detail                 brief .. deep
//!       for each fact:  Noul include_fact?
//!       Noul  expand_children?      -- recurse one level deeper when yes
//! Noul include_toc / include_references / cover_page
//! ```
//!
//! Nothing here knows about any subject, genre or theme. All of that arrives
//! as named features computed from the database; the policy weights decide.
//! The only fixed rules are structural guarantees: a hard word cap, a maximum
//! depth, and "a child is only considered when its parent was included".

use crate::policy::{Features, Policy, Step};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OptionIn {
    pub id: String,
    #[serde(default)]
    pub features: Features,
    /// Word budget to use when this option is chosen and the request gave none.
    #[serde(default)]
    pub budget_words: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FactIn {
    pub id: i64,
    pub kind: String,
    /// Estimated words this fact takes on the page.
    pub cost: f32,
    #[serde(default)]
    pub features: Features,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TopicIn {
    pub id: i64,
    /// Words taken by the heading itself.
    #[serde(default)]
    pub cost: f32,
    #[serde(default)]
    pub features: Features,
    #[serde(default)]
    pub facts: Vec<FactIn>,
    #[serde(default)]
    pub children: Vec<TopicIn>,
}

fn default_cap() -> f32 {
    1.15
}
fn default_depth() -> u32 {
    3
}
fn default_levels() -> u32 {
    3
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanRequest {
    #[serde(default)]
    pub global: Features,
    #[serde(default)]
    pub genres: Vec<OptionIn>,
    #[serde(default)]
    pub themes: Vec<OptionIn>,
    #[serde(default)]
    pub candidates: Vec<TopicIn>,
    pub budget_words: f32,
    #[serde(default = "default_cap")]
    pub hard_cap_ratio: f32,
    #[serde(default = "default_depth")]
    pub max_depth: u32,
    #[serde(default = "default_levels")]
    pub detail_levels: u32,
    #[serde(default)]
    pub gates: Vec<String>,
    #[serde(default)]
    pub seed: u64,
    #[serde(default)]
    pub greedy: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlannedTopic {
    pub id: i64,
    pub depth: u32,
    pub detail: u32,
    pub facts: Vec<i64>,
    pub children: Vec<PlannedTopic>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanResult {
    pub genre: Option<String>,
    pub genre_probs: Vec<(String, f32)>,
    pub theme: Option<String>,
    pub theme_probs: Vec<(String, f32)>,
    pub gates: BTreeMap<String, bool>,
    pub gate_probs: BTreeMap<String, f32>,
    pub topics: Vec<PlannedTopic>,
    pub words_planned: f32,
    pub budget_words: f32,
    pub decisions: usize,
    pub log_prob: f32,
    pub trajectory: Vec<Step>,
}

/// SplitMix64: small, fast and deterministic for a given seed.
struct Rng(u64);
impl Rng {
    fn next_f32(&mut self) -> f32 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
        (z >> 40) as f32 / (1u64 << 24) as f32
    }
}

struct Walker<'a> {
    policy: &'a Policy,
    req: &'a PlanRequest,
    budget: f32,
    rng: Rng,
    used: f32,
    traj: Vec<Step>,
    log_prob: f32,
    genre: Option<String>,
}

fn merged(a: &Features, b: &Features) -> Features {
    let mut out = a.clone();
    for (k, v) in b {
        out.insert(k.clone(), *v);
    }
    out
}

/// Resolve genre-conditional features: `name@<genre>` becomes `name` when
/// `<genre>` is the chosen genre and is dropped otherwise. This is how a value
/// that depends on the genre (for example how much a genre wants formulas)
/// reaches a decision taken after the genre was chosen.
fn resolve_conditional(x: Features, genre: Option<&str>) -> Features {
    let mut out = Features::new();
    for (k, v) in x {
        match k.split_once('@') {
            Some((name, g)) => {
                if Some(g) == genre {
                    out.insert(name.to_string(), v);
                }
            }
            None => {
                out.insert(k, v);
            }
        }
    }
    out
}

impl<'a> Walker<'a> {
    fn budget_left(&self) -> f32 {
        if self.budget <= 0.0 {
            return 0.0;
        }
        (1.0 - self.used / self.budget).clamp(-1.0, 1.0)
    }

    fn cap(&self) -> f32 {
        self.budget * self.req.hard_cap_ratio.max(1.0)
    }

    fn dynamic(&self, depth: u32) -> Features {
        let mut d = Features::new();
        d.insert("bias".into(), 1.0);
        d.insert("budget_left".into(), self.budget_left());
        d.insert("used_frac".into(), (self.used / self.budget.max(1.0)).min(2.0));
        d.insert("depth".into(), depth as f32 / self.req.max_depth.max(1) as f32);
        if let Some(g) = &self.genre {
            d.insert(format!("genre:{g}"), 1.0);
        }
        d
    }

    fn noul(&mut self, family: &str, x: Features) -> bool {
        let p = self.policy.noul_prob(family, &x);
        let chosen = if self.req.greedy { p >= 0.5 } else { self.rng.next_f32() < p };
        self.log_prob += if chosen { p.max(1e-6).ln() } else { (1.0 - p).max(1e-6).ln() };
        self.traj.push(Step::Noul { family: family.into(), x, p, chosen });
        chosen
    }

    fn choice(&mut self, family: &str, options: Vec<(String, Features)>) -> (usize, Vec<f32>) {
        let (probs, t) = self.policy.choice_probs(family, &options);
        let chosen = self.pick(&probs);
        self.log_prob += probs[chosen].max(1e-6).ln();
        self.traj.push(Step::Choice {
            family: family.into(),
            options,
            probs: probs.clone(),
            chosen,
            temperature: t,
        });
        (chosen, probs)
    }

    fn score(&mut self, family: &str, x: Features, levels: usize) -> usize {
        let probs = self.policy.score_probs(family, &x, levels);
        let chosen = self.pick(&probs);
        self.log_prob += probs[chosen].max(1e-6).ln();
        self.traj.push(Step::Score { family: family.into(), x, probs, chosen });
        chosen
    }

    fn pick(&mut self, probs: &[f32]) -> usize {
        if self.req.greedy {
            return probs
                .iter()
                .enumerate()
                .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
                .map(|(i, _)| i)
                .unwrap_or(0);
        }
        let r = self.rng.next_f32();
        let mut acc = 0.0;
        for (i, p) in probs.iter().enumerate() {
            acc += p;
            if r < acc {
                return i;
            }
        }
        probs.len().saturating_sub(1)
    }

    fn topic(&mut self, t: &TopicIn, depth: u32, siblings: usize, rank: usize) -> Option<PlannedTopic> {
        if self.used + t.cost > self.cap() {
            return None;
        }
        let mut dynf = self.dynamic(depth);
        dynf.insert("sibling_rank".into(), rank as f32 / siblings.max(1) as f32);
        let x = resolve_conditional(merged(&t.features, &dynf), self.genre.as_deref());
        if !self.noul("include_topic", x.clone()) {
            return None;
        }
        self.used += t.cost;

        let levels = self.req.detail_levels.max(1) as usize;
        let detail = if levels > 1 { self.score("detail", x.clone(), levels) } else { 0 };
        let detail_norm = if levels > 1 { detail as f32 / (levels - 1) as f32 } else { 0.0 };

        let mut facts = Vec::new();
        let mut kind_counts: BTreeMap<&str, u32> = BTreeMap::new();
        for f in &t.facts {
            if self.used + f.cost > self.cap() {
                continue;
            }
            let seen = *kind_counts.get(f.kind.as_str()).unwrap_or(&0);
            let mut fx = resolve_conditional(merged(&f.features, &self.dynamic(depth)), self.genre.as_deref());
            fx.insert("detail".into(), detail_norm);
            fx.insert("first_of_kind".into(), if seen == 0 { 1.0 } else { 0.0 });
            fx.insert("kind_repeat".into(), seen as f32);
            fx.insert(format!("kind:{}", f.kind), 1.0);
            if self.noul("include_fact", fx) {
                self.used += f.cost;
                facts.push(f.id);
                *kind_counts.entry(f.kind.as_str()).or_insert(0) += 1;
            }
        }

        let mut children = Vec::new();
        if depth + 1 < self.req.max_depth && !t.children.is_empty() {
            let mut ex = resolve_conditional(merged(&t.features, &self.dynamic(depth)), self.genre.as_deref());
            ex.insert("detail".into(), detail_norm);
            ex.insert("facts_taken".into(), facts.len() as f32 / t.facts.len().max(1) as f32);
            if self.noul("expand_children", ex) {
                let n = t.children.len();
                for (i, c) in t.children.iter().enumerate() {
                    if let Some(pc) = self.topic(c, depth + 1, n, i) {
                        children.push(pc);
                    }
                }
            }
        }
        if facts.is_empty() && children.is_empty() {
            // Structural guarantee: a heading with nothing under it never
            // reaches the document. Its words are given back to the budget.
            self.used -= t.cost;
            return None;
        }
        Some(PlannedTopic { id: t.id, depth, detail: detail as u32, facts, children })
    }
}

pub fn plan(policy: &Policy, req: &PlanRequest) -> PlanResult {
    let mut w = Walker {
        policy,
        req,
        budget: req.budget_words,
        rng: Rng(req.seed ^ 0xA076_1D64_78BD_642F),
        used: 0.0,
        traj: Vec::new(),
        log_prob: 0.0,
        genre: None,
    };

    let mut genre_probs = Vec::new();
    if !req.genres.is_empty() {
        let opts: Vec<(String, Features)> = req
            .genres
            .iter()
            .map(|o| (o.id.clone(), merged(&req.global, &o.features)))
            .collect();
        let (i, probs) = w.choice("genre", opts);
        w.genre = Some(req.genres[i].id.clone());
        if req.budget_words <= 0.0 {
            if let Some(b) = req.genres[i].budget_words {
                w.budget = b;
            }
        }
        genre_probs = req.genres.iter().map(|o| o.id.clone()).zip(probs).collect();
    }

    let mut theme = None;
    let mut theme_probs = Vec::new();
    if !req.themes.is_empty() {
        let g = w.genre.clone();
        let opts: Vec<(String, Features)> = req
            .themes
            .iter()
            .map(|o| {
                let mut x = merged(&req.global, &o.features);
                if let Some(g) = &g {
                    // Genre x theme interaction, learnable per pair.
                    x.insert(format!("pair:{g}|{}", o.id), 1.0);
                }
                (o.id.clone(), x)
            })
            .collect();
        let (i, probs) = w.choice("theme", opts);
        theme = Some(req.themes[i].id.clone());
        theme_probs = req.themes.iter().map(|o| o.id.clone()).zip(probs).collect();
    }

    let n = req.candidates.len();
    let mut topics = Vec::new();
    for (i, c) in req.candidates.iter().enumerate() {
        if let Some(pt) = w.topic(c, 0, n, i) {
            topics.push(pt);
        }
    }

    let mut gates = BTreeMap::new();
    let mut gate_probs = BTreeMap::new();
    let n_topics = count(&topics) as f32;
    for gate in &req.gates {
        let mut x = merged(&req.global, &w.dynamic(0));
        x.insert("n_topics".into(), (1.0 + n_topics).ln());
        x.insert("planned_frac".into(), (w.used / w.budget.max(1.0)).min(2.0));
        let family = format!("gate:{gate}");
        let p = policy.noul_prob(&family, &x);
        let chosen = w.noul(&family, x);
        gates.insert(gate.clone(), chosen);
        gate_probs.insert(gate.clone(), p);
    }

    PlanResult {
        genre: w.genre.clone(),
        genre_probs,
        theme,
        theme_probs,
        gates,
        gate_probs,
        topics,
        words_planned: w.used,
        budget_words: w.budget,
        decisions: w.traj.len(),
        log_prob: w.log_prob,
        trajectory: w.traj,
    }
}

fn count(ts: &[PlannedTopic]) -> usize {
    ts.iter().map(|t| 1 + count(&t.children)).sum()
}
