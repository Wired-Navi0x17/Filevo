//! Learned parameters and the three Jev-style primitives.
//!
//! * `Noul`   a yes/no gate:            p = sigmoid(w . x)
//! * `Choice` one of several options:   p_o = softmax((w . x_o + b_o) / T)
//! * `Score`  an ordinal level 0..L-1:  P(y <= k) = sigmoid(theta_k - w . x)
//!
//! Features are named (`BTreeMap<String, f32>`), so the Python side can add
//! or remove features without breaking a saved policy: an unknown weight is
//! simply zero until it is learned.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};

pub type Features = BTreeMap<String, f32>;

fn one() -> f32 {
    1.0
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Family {
    #[serde(default)]
    pub weights: HashMap<String, f32>,
    /// Per-option bias for Choice families, keyed by option id.
    #[serde(default)]
    pub option_bias: HashMap<String, f32>,
    /// Ordered cut points for Score families (L - 1 of them).
    #[serde(default)]
    pub thresholds: Vec<f32>,
    #[serde(default = "one")]
    pub temperature: f32,
}

impl Default for Family {
    fn default() -> Self {
        Family {
            weights: HashMap::new(),
            option_bias: HashMap::new(),
            thresholds: Vec::new(),
            temperature: 1.0,
        }
    }
}

impl Family {
    pub fn dot(&self, x: &Features) -> f32 {
        x.iter()
            .map(|(k, v)| self.weights.get(k).copied().unwrap_or(0.0) * v)
            .sum()
    }

    fn thresholds_for(&self, levels: usize) -> Vec<f32> {
        let need = levels.saturating_sub(1);
        if self.thresholds.len() == need {
            return self.thresholds.clone();
        }
        // Evenly spaced cut points in [-1, 1] until learned.
        (0..need)
            .map(|k| if need == 1 { 0.0 } else { -1.0 + 2.0 * k as f32 / (need - 1) as f32 })
            .collect()
    }
}

pub fn sigmoid(z: f32) -> f32 {
    let z = z.clamp(-30.0, 30.0);
    1.0 / (1.0 + (-z).exp())
}

pub fn softmax(z: &[f32]) -> Vec<f32> {
    let m = z.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let e: Vec<f32> = z.iter().map(|v| (v - m).exp()).collect();
    let s: f32 = e.iter().sum();
    e.iter().map(|v| v / s.max(1e-12)).collect()
}

pub fn entropy(p: &[f32]) -> f32 {
    -p.iter().filter(|v| **v > 0.0).map(|v| v * v.ln()).sum::<f32>()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Policy {
    pub version: u32,
    pub families: HashMap<String, Family>,
    pub baseline: f32,
    pub baseline_decay: f32,
    pub learning_rate: f32,
    pub entropy_coef: f32,
    pub weight_clip: f32,
    pub episodes: u64,
    #[serde(default)]
    pub reward_history: Vec<f32>,
}

impl Default for Policy {
    fn default() -> Self {
        Policy {
            version: 1,
            families: HashMap::new(),
            baseline: 0.0,
            baseline_decay: 0.9,
            learning_rate: 0.05,
            entropy_coef: 0.01,
            weight_clip: 8.0,
            episodes: 0,
            reward_history: Vec::new(),
        }
    }
}

/// One decision taken while planning. Stored in the trajectory so that
/// `update` can compute the exact policy gradient later.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Step {
    Noul {
        family: String,
        x: Features,
        p: f32,
        chosen: bool,
    },
    Choice {
        family: String,
        options: Vec<(String, Features)>,
        probs: Vec<f32>,
        chosen: usize,
        temperature: f32,
    },
    Score {
        family: String,
        x: Features,
        probs: Vec<f32>,
        chosen: usize,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UpdateStats {
    pub reward: f32,
    pub advantage: f32,
    pub baseline: f32,
    pub steps: usize,
    pub grad_norm: f32,
    pub episodes: u64,
}

impl Policy {
    pub fn family(&self, name: &str) -> Family {
        self.families.get(name).cloned().unwrap_or_default()
    }

    pub fn noul_prob(&self, family: &str, x: &Features) -> f32 {
        sigmoid(self.families.get(family).map(|f| f.dot(x)).unwrap_or(0.0))
    }

    pub fn choice_probs(&self, family: &str, options: &[(String, Features)]) -> (Vec<f32>, f32) {
        let fam = self.family(family);
        let t = fam.temperature.max(0.05);
        let logits: Vec<f32> = options
            .iter()
            .map(|(id, x)| (fam.dot(x) + fam.option_bias.get(id).copied().unwrap_or(0.0)) / t)
            .collect();
        (softmax(&logits), t)
    }

    pub fn score_probs(&self, family: &str, x: &Features, levels: usize) -> Vec<f32> {
        let fam = self.family(family);
        let s = fam.dot(x);
        let th = fam.thresholds_for(levels);
        let mut cdf: Vec<f32> = th.iter().map(|t| sigmoid(t - s)).collect();
        cdf.push(1.0);
        let mut out = Vec::with_capacity(levels);
        let mut prev = 0.0;
        for c in cdf {
            out.push((c - prev).max(1e-6));
            prev = c;
        }
        let total: f32 = out.iter().sum();
        out.iter().map(|v| v / total).collect()
    }

    /// Merge a prior (`{family: {weights, option_bias, thresholds, temperature}}`).
    /// Only values that are not learned yet are filled in.
    pub fn apply_prior(&mut self, prior: &HashMap<String, Family>) {
        for (name, pf) in prior {
            let fam = self.families.entry(name.clone()).or_insert_with(|| Family {
                temperature: pf.temperature,
                ..Default::default()
            });
            for (k, v) in &pf.weights {
                fam.weights.entry(k.clone()).or_insert(*v);
            }
            for (k, v) in &pf.option_bias {
                fam.option_bias.entry(k.clone()).or_insert(*v);
            }
            if fam.thresholds.is_empty() && !pf.thresholds.is_empty() {
                fam.thresholds = pf.thresholds.clone();
            }
        }
    }

    /// REINFORCE with an EMA baseline and an entropy bonus, over a whole trajectory.
    pub fn update(&mut self, trajectory: &[Step], reward: f32) -> UpdateStats {
        let advantage = reward - self.baseline;
        let lr = self.learning_rate;
        let beta = self.entropy_coef;
        let clip = self.weight_clip;
        let mut sq = 0.0f32;

        for step in trajectory {
            match step {
                Step::Noul { family, x, p, chosen } => {
                    let a = if *chosen { 1.0 } else { 0.0 };
                    let p = p.clamp(1e-6, 1.0 - 1e-6);
                    // d log pi / dz and d H / dz for a Bernoulli gate.
                    let g = a - p;
                    let gh = p * (1.0 - p) * ((1.0 - p) / p).ln();
                    let fam = self.families.entry(family.clone()).or_default();
                    for (k, v) in x {
                        let d = lr * (advantage * g + beta * gh) * v;
                        let w = fam.weights.entry(k.clone()).or_insert(0.0);
                        *w = (*w + d).clamp(-clip, clip);
                        sq += (g * v) * (g * v);
                    }
                }
                Step::Choice { family, options, probs, chosen, temperature } => {
                    let t = temperature.max(0.05);
                    let h = entropy(probs);
                    let fam = self.families.entry(family.clone()).or_default();
                    for (o, (id, x)) in options.iter().enumerate() {
                        let p = probs[o];
                        let ind = if o == *chosen { 1.0 } else { 0.0 };
                        let g = (ind - p) / t;
                        let gh = -p * (p.max(1e-12).ln() + h) / t;
                        let coef = lr * (advantage * g + beta * gh);
                        let b = fam.option_bias.entry(id.clone()).or_insert(0.0);
                        *b = (*b + coef).clamp(-clip, clip);
                        for (k, v) in x {
                            let w = fam.weights.entry(k.clone()).or_insert(0.0);
                            *w = (*w + coef * v).clamp(-clip, clip);
                            sq += (g * v) * (g * v);
                        }
                    }
                }
                Step::Score { family, x, probs, chosen } => {
                    let levels = probs.len();
                    let fam = self.families.entry(family.clone()).or_default();
                    let mut th = fam.thresholds_for(levels);
                    let s = fam.dot(x);
                    let cdf = |k: isize, th: &Vec<f32>| -> f32 {
                        if k < 0 {
                            0.0
                        } else if k as usize >= th.len() {
                            1.0
                        } else {
                            sigmoid(th[k as usize] - s)
                        }
                    };
                    let k = *chosen as isize;
                    let fk = cdf(k, &th);
                    let fk1 = cdf(k - 1, &th);
                    let pk = (fk - fk1).max(1e-6);
                    let dk = fk * (1.0 - fk);
                    let dk1 = fk1 * (1.0 - fk1);
                    // d log P(y = k) / d s, and with respect to the two cut points around k.
                    let gs = (dk1 - dk) / pk;
                    for (name, v) in x {
                        let w = fam.weights.entry(name.clone()).or_insert(0.0);
                        *w = (*w + lr * advantage * gs * v).clamp(-clip, clip);
                        sq += (gs * v) * (gs * v);
                    }
                    if (k as usize) < th.len() {
                        th[k as usize] += lr * advantage * dk / pk;
                    }
                    if k >= 1 {
                        th[(k - 1) as usize] -= lr * advantage * dk1 / pk;
                    }
                    th.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                    for i in 1..th.len() {
                        if th[i] - th[i - 1] < 0.05 {
                            th[i] = th[i - 1] + 0.05;
                        }
                    }
                    fam.thresholds = th;
                }
            }
        }

        self.baseline = self.baseline_decay * self.baseline + (1.0 - self.baseline_decay) * reward;
        self.episodes += 1;
        self.reward_history.push(reward);
        if self.reward_history.len() > 200 {
            let cut = self.reward_history.len() - 200;
            self.reward_history.drain(..cut);
        }
        UpdateStats {
            reward,
            advantage,
            baseline: self.baseline,
            steps: trajectory.len(),
            grad_norm: sq.sqrt(),
            episodes: self.episodes,
        }
    }

    /// Fit one temperature for a Choice family by grid search on negative
    /// log-likelihood. `samples` are (logits, target index).
    pub fn fit_temperature(&mut self, family: &str, samples: &[(Vec<f32>, usize)]) -> f32 {
        if samples.is_empty() {
            return self.family(family).temperature;
        }
        let nll = |t: f32| -> f32 {
            samples
                .iter()
                .map(|(z, y)| {
                    let scaled: Vec<f32> = z.iter().map(|v| v / t).collect();
                    -softmax(&scaled)[*y].max(1e-12).ln()
                })
                .sum::<f32>()
                / samples.len() as f32
        };
        let mut best = (1.0, f32::INFINITY);
        let mut t = 0.25;
        while t <= 4.0 + 1e-6 {
            let v = nll(t);
            if v < best.1 {
                best = (t, v);
            }
            t += 0.05;
        }
        self.families.entry(family.to_string()).or_default().temperature = best.0;
        best.0
    }
}
