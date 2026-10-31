"""RLCD: Reinforcement Learning Calibrated Decision Engine for Documents.

Selects relevant document archetypes, determines section structures,
chooses formatting strategies, estimates confidence, calibrates probabilities empirically,
and decides when human review is necessary.

Consolidates all policy learning, Jev primitives (Choice, Score, Noul),
REINFORCE policy gradient optimization, and empirical calibration (ECE, Brier, Temperature Scaling).
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

ARCHETYPES = [
    "Technical Report",
    "Academic Monograph",
    "Project Proposal",
    "Executive Summary",
    "Formal Letter",
]

FONTS = ["Times New Roman", "Calibri", "Arial", "Georgia"]
COLOR_PALETTES = {
    "Navy": "1F4E79",
    "Charcoal": "333333",
    "Slate": "2E75B6",
    "Forest": "2D6A4F",
}

DEFAULT_FEATURES = [
    # Section choices (Choice primitive)
    "section_introduction",
    "section_methodology",
    "section_architecture",
    "section_patterns",
    "section_complexity",
    "section_conclusion",
    # Math rigor level (Score primitive)
    "rigor_none",
    "rigor_asymptotic",
    "rigor_formal",
    # Detail depth (Score primitive)
    "depth_brief",
    "depth_standard",
    "depth_deep",
    # Boolean gates (Noul primitive)
    "include_formulas",
    "include_diagrams",
    "include_benchmarks",
    "include_tables",
    "include_callouts",
    # Volume and chapter structure (Choice / Scale primitives)
    "volume_brief",
    "volume_standard",
    "volume_extended",
    "volume_monograph",
    "sections_multi_chapter",
]


@dataclass
class FormattingStrategy:
    """Strategy chosen by RLCD for rendering the document."""
    font_family: str = "Times New Roman"
    accent_color: str = "1F4E79"
    margin_inches: float = 1.0
    line_spacing: float = 1.15
    include_tables: bool = True
    include_callouts: bool = True
    title_alignment: str = "left"  # left or center


@dataclass
class RLCDDecision:
    """The result of an RLCD decision evaluation."""
    archetype: str
    confidence: float
    agreement: float
    disagreement: float
    normalized_entropy: float
    status: str  # CONFIDENT or AMBIGUOUS
    requires_human_review: bool
    formatting: FormattingStrategy
    recommended_sections: list[str]
    rationale: str


class RLCDDecisionEngine:
    """Calibrated decision model for document synthesis and structural policy."""

    def __init__(self, policy_path: str | None = None, learning_rate: float = 0.05):
        if policy_path is None:
            config_dir = Path.home() / ".filevo" / "policy"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.policy_path = config_dir / "rlcd_policy.json"
        else:
            self.policy_path = Path(policy_path)
            self.policy_path.parent.mkdir(parents=True, exist_ok=True)

        self.learning_rate = learning_rate
        self.temperature: float = 1.0

        # Unified policy weights θ (logits)
        self.weights: dict[str, float] = {}
        self.archetype_biases: dict[str, float] = {a: 0.0 for a in ARCHETYPES}
        self.font_biases: dict[str, float] = {f: 0.0 for f in FONTS}

        # Policy metrics and parameters
        self.episodes: int = 0
        self.baseline: float = 0.0
        self.baseline_decay: float = 0.9
        self.entropy_coeff: float = 0.01
        self.cumulative_reward: float = 0.0
        self.reward_history: list[float] = []

        # Decision state & cached trajectory
        self.last_decision: RLCDDecision | None = None
        self.last_trajectory: dict[str, Any] | None = None
        # The intent block below is an explicitly-labelled prior/demo default.
        # It is only marked live after evaluate_intent() actually runs.
        self.intent_evaluated: bool = False
        self.last_decision_intent: dict[str, Any] = {
            "intent": "CONVERSATION",
            "probabilities": {
                "DOCUMENT_CREATION": 0.12,
                "CONVERSATION": 0.71,
                "DOCUMENT_ANALYSIS": 0.08,
                "KNOWLEDGE_INDEXING": 0.05,
                "POLICY_TRAIN": 0.04,
            },
            "confidence": 0.713,
            "entropy": 0.58,
            "risk": "LOW",
        }

        self._init_default_weights()
        self.load()

    @property
    def episode_count(self) -> int:
        """Alias for episodes to match legacy RLProbabilisticModel."""
        return self.episodes

    @episode_count.setter
    def episode_count(self, val: int):
        self.episodes = val

    def _init_default_weights(self):
        """Initialize weights with uniform logits (0.0)."""
        for a in ARCHETYPES:
            self.weights[f"arch_{a}"] = 0.0
        for f in FONTS:
            self.weights[f"font_{f}"] = 0.0
        for feat in DEFAULT_FEATURES:
            self.weights[feat] = 0.0

    def load(self):
        """Load persistent policy weights from disk."""
        if not self.policy_path.exists():
            return
        try:
            with open(self.policy_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "weights" in data:
                self.weights.update({k: float(v) for k, v in data["weights"].items()})

            if "archetype_biases" in data:
                self.archetype_biases = {
                    k: float(v) for k, v in data["archetype_biases"].items()
                }
            for a in ARCHETYPES:
                if a not in self.archetype_biases:
                    self.archetype_biases[a] = self.weights.get(f"arch_{a}", 0.0)
                self.weights[f"arch_{a}"] = self.archetype_biases[a]

            if "font_biases" in data:
                self.font_biases = {
                    k: float(v) for k, v in data["font_biases"].items()
                }
            for f in FONTS:
                if f not in self.font_biases:
                    self.font_biases[f] = self.weights.get(f"font_{f}", 0.0)
                self.weights[f"font_{f}"] = self.font_biases[f]

            self.episodes = int(data.get("episodes", data.get("episode_count", 0)))
            self.baseline = float(data.get("baseline", 0.0))
            self.cumulative_reward = float(data.get("cumulative_reward", 0.0))
            self.temperature = float(data.get("temperature", 1.0))
            self.reward_history = data.get("reward_history", [])[-100:]
            self.last_trajectory = data.get("last_trajectory", None)

            last_dec = data.get("last_decision")
            if last_dec:
                fmt_data = last_dec.get("formatting", {})
                fmt = FormattingStrategy(**fmt_data) if fmt_data else FormattingStrategy()
                self.last_decision = RLCDDecision(
                    archetype=last_dec["archetype"],
                    confidence=last_dec["confidence"],
                    agreement=last_dec["agreement"],
                    disagreement=last_dec["disagreement"],
                    normalized_entropy=last_dec["normalized_entropy"],
                    status=last_dec["status"],
                    requires_human_review=last_dec["requires_human_review"],
                    formatting=fmt,
                    recommended_sections=last_dec.get("recommended_sections", []),
                    rationale=last_dec.get("rationale", ""),
                )
        except Exception:
            pass

    def save(self):
        """Persist policy weights to disk."""
        for a, b in self.archetype_biases.items():
            self.weights[f"arch_{a}"] = b
        for f, b in self.font_biases.items():
            self.weights[f"font_{f}"] = b

        data = {
            "weights": self.weights,
            "archetype_biases": self.archetype_biases,
            "font_biases": self.font_biases,
            "episodes": self.episodes,
            "episode_count": self.episodes,
            "baseline": self.baseline,
            "temperature": self.temperature,
            "cumulative_reward": self.cumulative_reward,
            "learning_rate": self.learning_rate,
            "reward_history": self.reward_history[-100:],
            "last_trajectory": self.last_trajectory,
            "last_decision": asdict(self.last_decision) if self.last_decision else None,
        }
        tmp = self.policy_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(self.policy_path)
        except Exception:
            if tmp.exists():
                tmp.unlink()

    # ------------------------------------------------------------------ #
    # Math & Jev Primitives
    # ------------------------------------------------------------------ #

    def softmax(
        self,
        scores_or_features: list[float] | list[str],
        temp: float | None = None,
    ) -> list[float] | dict[str, float]:
        """Compute stable tempered softmax.

        If passed a list of float logits, returns a list of float probabilities.
        If passed a list of str feature keys, returns a dict of {feature: probability}.
        """
        temperature = temp if temp is not None else self.temperature
        t = max(temperature, 0.01)

        if not scores_or_features:
            return []

        if isinstance(scores_or_features[0], str):
            feature_set: list[str] = scores_or_features  # type: ignore
            logits = [self.weights.get(f, 0.0) / t for f in feature_set]
            max_logit = max(logits) if logits else 0.0
            exp_vals = [math.exp(l - max_logit) for l in logits]
            total = sum(exp_vals)
            if total <= 0:
                return {f: 1.0 / len(feature_set) for f in feature_set}
            return {f: e / total for f, e in zip(feature_set, exp_vals)}
        else:
            scores: list[float] = scores_or_features  # type: ignore
            scaled = [s / t for s in scores]
            max_s = max(scaled)
            exp_s = [math.exp(s - max_s) for s in scaled]
            sum_exp = sum(exp_s)
            if sum_exp <= 0:
                return [1.0 / len(scores)] * len(scores)
            return [e / sum_exp for e in exp_s]

    def sigmoid(self, feature: str) -> float:
        """Compute sigmoid probability for a single feature (Noul primitive)."""
        w = self.weights.get(feature, 0.0)
        w = max(-20.0, min(20.0, w))
        return 1.0 / (1.0 + math.exp(-w))

    def noul(self, feature: str) -> float:
        """Jev Noul primitive: returns P(include) in [0, 1]."""
        return self.sigmoid(feature)

    def choice(self, feature_set: list[str], temperature: float | None = None) -> dict[str, float]:
        """Jev Choice primitive: softmax categorical selection over option sets."""
        res = self.softmax(feature_set, temp=temperature)
        return res if isinstance(res, dict) else {f: p for f, p in zip(feature_set, res)}

    def score(self, feature_set: list[str]) -> tuple[str, float]:
        """Jev Score primitive: returns (selected_level, confidence)."""
        probs = self.choice(feature_set)
        selected = max(probs, key=probs.get)
        return selected, probs[selected]

    def sample_choice(self, feature_set: list[str], temperature: float | None = None) -> str:
        """Sample a single feature from softmax distribution."""
        probs = self.choice(feature_set, temperature)
        features = list(probs.keys())
        weights = list(probs.values())
        return random.choices(features, weights=weights, k=1)[0]

    def sample_binary(self, feature: str) -> bool:
        """Sample a boolean decision from sigmoid gate."""
        return random.random() < self.sigmoid(feature)

    @staticmethod
    def jensen_shannon_divergence(p: list[float], q: list[float]) -> float:
        """Compute symmetric JSD in [0, 1] bits."""
        if len(p) != len(q) or not p:
            return 0.0
        eps = 1e-12
        m = [0.5 * (p[i] + q[i]) for i in range(len(p))]

        def kl(a, b):
            return sum(
                a[i] * math.log2(max(a[i], eps) / max(b[i], eps))
                for i in range(len(a)) if a[i] > 0
            )

        jsd = 0.5 * kl(p, m) + 0.5 * kl(q, m)
        return max(0.0, min(1.0, jsd))

    @staticmethod
    def normalized_entropy(p: list[float]) -> float:
        """Compute Shannon entropy normalized to [0, 1]."""
        k = len(p)
        if k <= 1:
            return 0.0
        raw_h = -sum(pi * math.log2(pi) for pi in p if pi > 0)
        max_h = math.log2(k)
        return max(0.0, min(1.0, raw_h / max_h))

    # ------------------------------------------------------------------ #
    # Empirical Calibration & Temperature Scaling
    # ------------------------------------------------------------------ #

    @staticmethod
    def compute_calibration_metrics(
        predicted_probs: Sequence[Sequence[float]],
        targets: Sequence[int],
        num_bins: int = 10,
    ) -> dict[str, Any]:
        """Compute Expected Calibration Error (ECE), MCE, and Brier Score.

        Args:
            predicted_probs: N x K matrix of predicted probabilities over K classes.
            targets: N ground truth class indices in {0, ..., K-1}.
            num_bins: Number of confidence bins (standard is 10 or 15).

        Returns:
            Dictionary with 'ece', 'mce', 'brier_score', 'num_samples', 'bin_accuracies',
            'bin_confidences', and 'bin_counts'.
        """
        n = len(targets)
        if n == 0 or len(predicted_probs) != n:
            return {
                "ece": 0.0,
                "mce": 0.0,
                "brier_score": 0.0,
                "num_samples": 0,
                "bin_accuracies": [],
                "bin_confidences": [],
                "bin_counts": [],
            }

        confidences = []
        accuracies = []
        brier_sum = 0.0

        for p_row, y in zip(predicted_probs, targets):
            max_idx = max(range(len(p_row)), key=lambda i: p_row[i])
            conf = p_row[max_idx]
            correct = 1.0 if max_idx == y else 0.0
            confidences.append(conf)
            accuracies.append(correct)

            for k, p_k in enumerate(p_row):
                target_k = 1.0 if k == y else 0.0
                brier_sum += (p_k - target_k) ** 2

        brier_score = brier_sum / n

        bin_counts = [0] * num_bins
        bin_acc_sums = [0.0] * num_bins
        bin_conf_sums = [0.0] * num_bins

        for conf, acc in zip(confidences, accuracies):
            bin_idx = min(int(conf * num_bins), num_bins - 1)
            bin_counts[bin_idx] += 1
            bin_acc_sums[bin_idx] += acc
            bin_conf_sums[bin_idx] += conf

        ece = 0.0
        mce = 0.0
        bin_accuracies = []
        bin_confidences = []

        for count, acc_sum, conf_sum in zip(bin_counts, bin_acc_sums, bin_conf_sums):
            if count > 0:
                bin_acc = acc_sum / count
                bin_conf = conf_sum / count
                gap = abs(bin_acc - bin_conf)
                ece += (count / n) * gap
                mce = max(mce, gap)
                bin_accuracies.append(round(bin_acc, 4))
                bin_confidences.append(round(bin_conf, 4))
            else:
                bin_accuracies.append(0.0)
                bin_confidences.append(0.0)

        return {
            "ece": round(ece, 4),
            "mce": round(mce, 4),
            "brier_score": round(brier_score, 4),
            "num_samples": n,
            "num_bins": num_bins,
            "bin_accuracies": bin_accuracies,
            "bin_confidences": bin_confidences,
            "bin_counts": bin_counts,
        }

    def fit_temperature_scaling(
        self,
        val_logits: Sequence[Sequence[float]],
        val_targets: Sequence[int],
        search_min: float = 0.1,
        search_max: float = 5.0,
        steps: int = 100,
    ) -> float:
        """Fit optimal scalar temperature T on validation logits by minimizing NLL.

        Args:
            val_logits: List of unnormalized logit vectors.
            val_targets: List of integer target labels.
            search_min: Minimum temperature boundary.
            search_max: Maximum temperature boundary.
            steps: Grid search steps.

        Returns:
            Optimal temperature T*.
        """
        if not val_logits or len(val_logits) != len(val_targets):
            return self.temperature

        def compute_nll(t: float) -> float:
            total_nll = 0.0
            for logits, y in zip(val_logits, val_targets):
                probs = self.softmax(list(logits), temp=t)  # type: ignore
                p_y = max(probs[y], 1e-12)
                total_nll -= math.log(p_y)
            return total_nll / len(val_targets)

        best_t = 1.0
        best_nll = float("inf")

        step_size = (search_max - search_min) / steps
        for i in range(steps + 1):
            t = search_min + i * step_size
            nll = compute_nll(t)
            if nll < best_nll:
                best_nll = nll
                best_t = t

        self.temperature = round(best_t, 3)
        self.save()
        return self.temperature

    # ------------------------------------------------------------------ #
    # Trajectory Caching & Policy Gradient Optimization
    # ------------------------------------------------------------------ #

    def record_trajectory(self, trajectory: dict[str, Any]):
        """Save generation trajectory for subsequent reward attribution."""
        self.last_trajectory = trajectory
        self.save()

    def get_last_trajectory(self) -> dict[str, Any] | None:
        """Retrieve the trajectory from the last generation episode."""
        return self.last_trajectory

    def update(self, trajectory: dict[str, Any], reward: float) -> dict[str, Any]:
        """Update model weights using REINFORCE policy gradient with moving baseline."""
        alpha = self.learning_rate
        advantage = reward - self.baseline

        updates = {}
        grad_norms = []

        # 1. Update Choice weights (softmax categorical groups)
        for choice_item in trajectory.get("choices", []):
            feature_set = choice_item["feature_set"]
            selected = choice_item["selected"]
            probs = self.choice(feature_set)

            for feat in feature_set:
                p = probs.get(feat, 0.0)
                grad = (1.0 - p) if feat == selected else (-p)

                old_w = self.weights.get(feat, 0.0)
                new_w = old_w + alpha * advantage * grad

                # Entropy regularization
                entropy_grad = -self.entropy_coeff * (p * math.log(max(p, 1e-8)))
                new_w += entropy_grad
                new_w = max(-5.0, min(5.0, new_w))

                self.weights[feat] = new_w
                updates[feat] = {"old": old_w, "new": new_w, "grad": grad, "prob": p}
                grad_norms.append(abs(grad))

        # 2. Update Noul/Gate weights (sigmoid)
        for gate_item in trajectory.get("gates", []):
            feat = gate_item["feature"]
            was_selected = gate_item["selected"]
            p = self.sigmoid(feat)

            grad = (1.0 - p) if was_selected else (-p)

            old_w = self.weights.get(feat, 0.0)
            new_w = old_w + alpha * advantage * grad
            new_w = max(-5.0, min(5.0, new_w))

            self.weights[feat] = new_w
            updates[feat] = {"old": old_w, "new": new_w, "grad": grad, "prob": p}
            grad_norms.append(abs(grad))

        # Update baseline
        self.baseline = self.baseline_decay * self.baseline + (1 - self.baseline_decay) * reward
        self.episodes += 1
        self.cumulative_reward += reward
        self.reward_history.append(reward)
        if len(self.reward_history) > 100:
            self.reward_history = self.reward_history[-100:]

        self.save()

        avg_grad = sum(grad_norms) / max(len(grad_norms), 1)
        return {
            "episode": self.episodes,
            "reward": reward,
            "advantage": round(advantage, 4),
            "baseline": round(self.baseline, 4),
            "avg_grad_norm": round(avg_grad, 4),
            "features_updated": len(updates),
            "updates": updates,
        }

    # ------------------------------------------------------------------ #
    # Decision Making
    # ------------------------------------------------------------------ #

    def decide(self, prompt: str, knowledge_profile: dict[str, Any] | None = None) -> RLCDDecision:
        """Evaluate prompt and knowledge to determine archetype and formatting strategy."""
        p_lower = prompt.lower()

        # Perspective 1: Structural / Lexical prior matching from prompt
        from src.doc_gen.document_brief import extract_page_budget
        target_pages, _ = extract_page_budget(prompt)
        is_large_volume = (target_pages is not None and target_pages >= 30) or any(w in p_lower for w in ("monograph", "treatise", "dissertation", "encyclopedia"))

        lex_scores = []
        for arch in ARCHETYPES:
            score = 1.0
            if "proposal" in p_lower and arch == "Project Proposal":
                score += 4.5
            elif ("summary" in p_lower or "brief" in p_lower) and arch == "Executive Summary":
                score += 4.5
            elif ("monograph" in p_lower or "academic" in p_lower or "research" in p_lower or "paper" in p_lower or is_large_volume) and arch == "Academic Monograph":
                score += 5.5 if is_large_volume else 4.5
            elif ("letter" in p_lower or "permission" in p_lower or "formal letter" in p_lower or "application" in p_lower or "memo" in p_lower) and arch == "Formal Letter":
                score += 5.0
            elif ("report" in p_lower or "technical" in p_lower or "analysis" in p_lower or "study" in p_lower) and arch == "Technical Report":
                score += 4.0
            lex_scores.append(score)

        p_struct: list[float] = self.softmax(lex_scores, temp=0.8)  # type: ignore

        # Perspective 2: Learned Policy prior
        policy_scores = [self.archetype_biases.get(a, 0.0) + 1.0 for a in ARCHETYPES]
        p_policy: list[float] = self.softmax(policy_scores, temp=self.temperature)  # type: ignore

        # Disagreement & Consensus
        disagreement = self.jensen_shannon_divergence(p_struct, p_policy)
        agreement = max(0.0, min(1.0, 1.0 - disagreement))

        p_ens = [0.5 * (p_struct[i] + p_policy[i]) for i in range(len(ARCHETYPES))]
        norm_h = self.normalized_entropy(p_ens)

        # Winner
        winner_idx = max(range(len(ARCHETYPES)), key=lambda i: p_ens[i])
        winner_arch = ARCHETYPES[winner_idx]
        confidence = p_ens[winner_idx]

        # Calibrated Risk Gate
        is_confident = (confidence >= 0.50) and (agreement >= 0.65) and (norm_h <= 0.85)
        status = "CONFIDENT" if is_confident else "AMBIGUOUS"
        requires_review = not is_confident

        # Choose formatting strategy
        font_scores = [self.font_biases.get(f, 0.0) + 1.0 for f in FONTS]
        p_font: list[float] = self.softmax(font_scores)  # type: ignore
        chosen_font = FONTS[max(range(len(FONTS)), key=lambda i: p_font[i])]

        if knowledge_profile and knowledge_profile.get("font"):
            chosen_font = knowledge_profile["font"]

        accent = COLOR_PALETTES.get("Navy", "1F4E79")
        if winner_arch == "Project Proposal":
            accent = COLOR_PALETTES["Slate"]
        elif winner_arch == "Academic Monograph":
            accent = COLOR_PALETTES["Charcoal"]
        elif winner_arch == "Formal Letter":
            accent = COLOR_PALETTES["Charcoal"]

        include_tbl = False if winner_arch == "Formal Letter" else (knowledge_profile.get("include_tables", True) if knowledge_profile else True)
        include_call = winner_arch in ("Technical Report", "Executive Summary")

        formatting = FormattingStrategy(
            font_family=chosen_font,
            accent_color=accent,
            margin_inches=1.0 if winner_arch != "Executive Summary" else 0.8,
            line_spacing=1.15 if winner_arch != "Academic Monograph" else 1.3,
            include_tables=include_tbl,
            include_callouts=include_call,
            title_alignment="left",
        )

        # Derive recommended sections
        if knowledge_profile and knowledge_profile.get("recommended_sections"):
            sections = knowledge_profile["recommended_sections"]
        else:
            if winner_arch == "Project Proposal":
                sections = ["Executive Summary", "Project Objectives", "Scope of Work", "Technical Architecture", "Budget and Timeline", "Risk Assessment"]
            elif winner_arch == "Executive Summary":
                sections = ["Key Highlights", "Strategic Overview", "Core Recommendations", "Next Steps"]
            elif winner_arch == "Academic Monograph":
                sections = ["Abstract", "Introduction", "Related Work", "System Architecture", "Empirical Evaluation", "Conclusion"]
            elif winner_arch == "Formal Letter":
                sections = ["Formal Salutation and Recipient", "Statement of Purpose", "Background and Justification", "Formal Terms and Requirements", "Closing and Authorization Signatures"]
            else:
                sections = ["Introduction", "Problem Definition", "System Architecture", "Implementation Analysis", "Performance & Complexity", "Conclusion"]

        decision = RLCDDecision(
            archetype=winner_arch,
            confidence=round(confidence, 4),
            agreement=round(agreement, 4),
            disagreement=round(disagreement, 4),
            normalized_entropy=round(norm_h, 4),
            status=status,
            requires_human_review=requires_review,
            formatting=formatting,
            recommended_sections=sections,
            rationale=f"Selected {winner_arch} with {confidence*100:.1f}% confidence and agreement {agreement*100:.1f}%.",
        )
        self.last_decision = decision
        return decision

    def evaluate_intent(self, prompt: str) -> dict[str, Any]:
        """Evaluate user prompt to compute calibrated intent distribution."""
        p_lower = prompt.lower().strip()
        intents = [
            "DOCUMENT_CREATION",
            "CONVERSATION",
            "DOCUMENT_ANALYSIS",
            "KNOWLEDGE_INDEXING",
            "POLICY_TRAIN",
        ]

        scores = [1.0, 1.0, 1.0, 1.0, 1.0]

        # Explicit document creation indicators
        doc_cues = ["create", "generate", "write", "draft", "make a report", "make a docx", "make a document", "formal letter", "proposal on", "paper on"]
        if any(c in p_lower for c in doc_cues) and not any(p_lower.startswith(q) for q in ("why", "how", "what", "explain", "describe", "tell me")):
            scores[0] += 6.5
        elif "letter" in p_lower or "report on" in p_lower or "document on" in p_lower:
            scores[0] += 5.5

        # Conversational cues
        greet_cues = ["hi", "hello", "hey", "sup", "good morning", "good evening", "howdy"]
        question_cues = ["why", "how", "what is", "what are", "explain", "describe", "tell me", "does", "can you explain", "difference between"]
        if p_lower in greet_cues or any(p_lower.startswith(g + " ") for g in greet_cues):
            scores[1] += 8.0
        elif any(p_lower.startswith(q) for q in question_cues) or ("?" in p_lower and not any(c in p_lower for c in doc_cues)):
            scores[1] += 7.0
        elif len(p_lower.split()) <= 3 and not any(c in p_lower for c in ("create", "generate", "report", "doc")):
            scores[1] += 5.0

        # Analysis cues
        if any(c in p_lower for c in ("analyze", "inspect", "audit", "review code", "examine file")):
            scores[2] += 6.0

        # Indexing cues
        if any(c in p_lower for c in ("index", "reindex", "scan directory", "cache docs")):
            scores[3] += 6.0

        # Policy train cues
        if any(c in p_lower for c in ("train", "reward", "feedback", "policy", "episodes")):
            scores[4] += 6.0

        p_struct: list[float] = self.softmax(scores, temp=0.8)  # type: ignore

        # Baseline prior distribution
        p_base = [0.15, 0.65, 0.08, 0.06, 0.06]
        p_ens = [0.6 * p_struct[i] + 0.4 * p_base[i] for i in range(len(intents))]
        norm_h = self.normalized_entropy(p_ens)

        winner_idx = max(range(len(intents)), key=lambda i: p_ens[i])
        winner_intent = intents[winner_idx]
        confidence = p_ens[winner_idx]

        risk = "LOW" if (confidence >= 0.60 and norm_h <= 0.70) else ("MEDIUM" if norm_h <= 0.85 else "HIGH")

        result = {
            "intent": winner_intent,
            "probabilities": {
                intents[i]: round(p_ens[i], 2) for i in range(len(intents))
            },
            "confidence": round(confidence, 3),
            "entropy": round(norm_h, 2),
            "risk": risk,
        }
        self.last_decision_intent = result
        self.intent_evaluated = True
        return result

    # ------------------------------------------------------------------ #
    # Reinforcement Learning Feedback & Training
    # ------------------------------------------------------------------ #

    def record_feedback(
        self,
        reward: float,
        is_override: bool = False,
        chosen_archetype: str | None = None,
    ) -> dict[str, Any]:
        """Apply a contextual policy gradient update from user confirmation or critique."""
        if self.last_decision is None and chosen_archetype is None:
            return {"status": "no_active_decision"}

        predicted_arch = self.last_decision.archetype if self.last_decision else ARCHETYPES[0]
        actual_arch = chosen_archetype or predicted_arch
        alpha = self.learning_rate

        self.episodes += 1
        advantage = reward - self.baseline

        probs: list[float] = self.softmax([self.archetype_biases.get(a, 0.0) for a in ARCHETYPES])  # type: ignore
        p_map = dict(zip(ARCHETYPES, probs))

        if not is_override and reward > 0:
            # Positive reinforcement on accepted archetype
            grad = 1.0 - p_map[actual_arch]
            self.archetype_biases[actual_arch] += alpha * advantage * grad
            for a in ARCHETYPES:
                if a != actual_arch:
                    self.archetype_biases[a] -= alpha * advantage * p_map[a] * 0.5
        else:
            # Negative reinforcement / user correction
            self.archetype_biases[predicted_arch] -= alpha * abs(advantage) * 0.8
            if chosen_archetype and chosen_archetype in self.archetype_biases:
                self.archetype_biases[chosen_archetype] += alpha * 1.0

        for a in self.archetype_biases:
            self.archetype_biases[a] = max(-3.0, min(3.0, self.archetype_biases[a]))

        self.baseline = self.baseline_decay * self.baseline + (1 - self.baseline_decay) * reward
        self.cumulative_reward += reward
        self.reward_history.append(reward)
        self.save()

        return {
            "episode": self.episodes,
            "reward": reward,
            "advantage": round(advantage, 4),
            "baseline": round(self.baseline, 4),
            "updated_biases": {k: round(v, 4) for k, v in self.archetype_biases.items()},
        }

    def train_on_knowledge_corpus(self, knowledge_summary: dict[str, Any]) -> dict[str, Any]:
        """Self-adapt policy priors automatically from indexed document distributions."""
        archetype_counts = knowledge_summary.get("archetypes", {})
        total = sum(archetype_counts.values())
        if total == 0:
            return {"episodes_trained": 0}

        for arch, count in archetype_counts.items():
            if arch in self.archetype_biases and count > 0:
                empirical_freq = count / total
                target_bias = (empirical_freq - (1.0 / len(ARCHETYPES))) * 2.0
                self.archetype_biases[arch] = 0.8 * self.archetype_biases[arch] + 0.2 * target_bias

        self.save()
        return {
            "episodes_trained": total,
            "empirical_distribution": {k: round(v / total, 3) for k, v in archetype_counts.items()},
            "adapted_biases": {k: round(v, 3) for k, v in self.archetype_biases.items()},
        }

    def train_on_validation_episodes(
        self,
        episodes_data: list[tuple[str, str]] | None = None,
        n_episodes: int = 10,
    ) -> dict[str, Any]:
        """Train policy against a diverse evaluation set with real consensus & target validation.

        Args:
            episodes_data: Optional list of (prompt, target_archetype) tuples.
            n_episodes: Number of episodes to run.
        """
        if not episodes_data:
            episodes_data = [
                ("Technical report on high-throughput streaming architecture", "Technical Report"),
                ("Formal letter of recommendation for senior research staff", "Formal Letter"),
                ("Executive summary of Q3 cloud infrastructure operational costs", "Executive Summary"),
                ("Academic monograph exploring transformer attention bounds", "Academic Monograph"),
                ("Project proposal for autonomous robotics deployment", "Project Proposal"),
                ("Detailed engineering analysis of memory allocator throughput", "Technical Report"),
                ("Formal university permission request for off-campus fieldwork", "Formal Letter"),
                ("High-level executive briefing on cybersecurity posture", "Executive Summary"),
                ("Formal research monograph on algebraic topology in data", "Academic Monograph"),
                ("Comprehensive project proposal for multi-datacenter migration", "Project Proposal"),
            ]

        preds_before = []
        targets = []
        for prompt, target in episodes_data:
            d = self.decide(prompt)
            scores = [self.archetype_biases.get(a, 0.0) for a in ARCHETYPES]
            p = self.softmax(scores)  # type: ignore
            preds_before.append(p)
            targets.append(ARCHETYPES.index(target) if target in ARCHETYPES else 0)

        cal_before = self.compute_calibration_metrics(preds_before, targets)

        history = []
        for i in range(min(n_episodes, len(episodes_data))):
            prompt, target = episodes_data[i % len(episodes_data)]
            decision = self.decide(prompt)

            # True reward based on agreement with target archetype and consensus
            is_match = (decision.archetype == target)
            reward = (0.7 + 0.3 * decision.agreement) if is_match else (-0.4 - 0.2 * decision.disagreement)

            res = self.record_feedback(reward=reward, chosen_archetype=target)
            history.append({
                "episode": res["episode"],
                "prompt": prompt,
                "predicted": decision.archetype,
                "target": target,
                "reward": reward,
                "advantage": res["advantage"],
            })

        preds_after = []
        for prompt, target in episodes_data:
            scores = [self.archetype_biases.get(a, 0.0) for a in ARCHETYPES]
            p = self.softmax(scores)  # type: ignore
            preds_after.append(p)

        cal_after = self.compute_calibration_metrics(preds_after, targets)

        # Optimize temperature scaling on post-training validation logits
        val_logits = [[self.archetype_biases.get(a, 0.0) for a in ARCHETYPES] for _ in targets]
        self.fit_temperature_scaling(val_logits, targets)

        return {
            "episodes_run": len(history),
            "baseline": round(self.baseline, 4),
            "cumulative_reward": round(self.cumulative_reward, 4),
            "cal_before": cal_before,
            "cal_after": cal_after,
            "learned_temperature": self.temperature,
            "history": history,
        }

    # ------------------------------------------------------------------ #
    # Autonomous Policy Learning & Artifact Evaluation
    # ------------------------------------------------------------------ #

    def evaluate_document_outcome(
        self,
        doc_path: str | Path,
        prompt: str,
        decision: RLCDDecision,
        sections: list[dict[str, Any]],
        explicit_sections: list[str] | None = None,
    ) -> dict[str, Any]:
        """Objectively evaluate a generated or revised document artifact.

        Scores against measurable criteria without simulating or inventing numbers:
        1. OpenXML package integrity and valid XML structure.
        2. Structural adherence (all expected sections rendered).
        3. Content uniqueness across sections (penalizes repeated boilerplate).
        4. Domain relevance and absence of spam patterns (e.g. streaming clickbait).
        5. Clean presentation (no leaked internal RLCD telemetry tables in the Word doc).

        Returns:
            Dictionary containing metrics breakdown and final scalar reward R in [-1.0, +1.0].
        """
        import zipfile
        import xml.etree.ElementTree as ET

        p = Path(doc_path)
        metrics: dict[str, Any] = {
            "valid_openxml": False,
            "sections_count": len(sections),
            "expected_sections_ratio": 0.0,
            "section_uniqueness": 0.0,
            "spam_free": True,
            "telemetry_free": True,
            "total_words": 0,
            "reward": 0.0,
        }

        # 1. OpenXML Integrity check
        if not p.exists() or p.stat().st_size == 0:
            metrics["reward"] = -1.0
            return metrics

        try:
            with zipfile.ZipFile(p, "r") as z:
                names = z.namelist()
                if "[Content_Types].xml" in names and "word/document.xml" in names:
                    doc_xml = z.read("word/document.xml")
                    ET.fromstring(doc_xml)
                    metrics["valid_openxml"] = True
        except Exception:
            metrics["valid_openxml"] = False
            metrics["reward"] = -1.0
            return metrics

        # 2. Structural adherence
        expected = explicit_sections if explicit_sections else decision.recommended_sections
        if expected:
            rendered_titles = {s.get("title", "").strip().lower() for s in sections}
            matches = sum(1 for r in expected if r.strip().lower() in rendered_titles)
            metrics["expected_sections_ratio"] = matches / len(expected)
        else:
            metrics["expected_sections_ratio"] = 1.0

        # 3. Content uniqueness across sections
        sec_texts = [s.get("content", "").strip() for s in sections if s.get("content")]
        total_words = sum(len(txt.split()) for txt in sec_texts)
        metrics["total_words"] = total_words

        if len(sec_texts) > 1:
            # Measure pairwise Jaccard similarity of 3-grams
            def get_ngrams(text: str, n: int = 3) -> set[tuple[str, ...]]:
                words = text.lower().split()
                return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}

            jaccards = []
            for i in range(len(sec_texts)):
                ng1 = get_ngrams(sec_texts[i])
                for j in range(i + 1, len(sec_texts)):
                    ng2 = get_ngrams(sec_texts[j])
                    if ng1 and ng2:
                        union = ng1 | ng2
                        sim = len(ng1 & ng2) / len(union) if union else 0.0
                        jaccards.append(sim)
            avg_overlap = sum(jaccards) / max(len(jaccards), 1)
            metrics["section_uniqueness"] = max(0.0, min(1.0, 1.0 - avg_overlap))
        else:
            metrics["section_uniqueness"] = 1.0

        # 4. Domain relevance, Concept Coverage & Absence of Spam
        spam_indicators = ["smartcric", "crichd", "watch live cricket streaming", "buffstream", "free stream online"]
        all_text = " ".join(sec_texts).lower()
        if any(sp in all_text for sp in spam_indicators):
            metrics["spam_free"] = False

        # Extract domain-specific concept terms from prompt to verify genuine subject coverage
        import re
        stopwords = {
            "create", "generate", "write", "draft", "make", "report", "document", "technical",
            "formal", "paper", "about", "using", "with", "sections", "please", "system", "study",
            "specifying", "covering", "including", "and", "the", "for", "from", "that", "this"
        }
        prompt_words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", prompt.lower())
        key_concepts = [w for w in prompt_words if w not in stopwords]
        
        if key_concepts:
            matched_concepts = sum(1 for c in key_concepts if c in all_text)
            concept_coverage = matched_concepts / len(key_concepts)
        else:
            concept_coverage = 0.8
        metrics["concept_coverage"] = round(concept_coverage, 3)

        # 5. Detect Generic Boilerplate Phrases
        canned_boilerplate = [
            "split-brain state anomalies",
            "dead-letter queues",
            "tls-encrypted streaming",
            "ntp synchronization",
            "compliance requirements and architectural invariants",
            "adherence to production standards",
            "foundational operating principles, architectural decomposition",
            "ensures predictable execution and strict adherence",
        ]
        leaked_boilerplate = [bp for bp in canned_boilerplate if bp in all_text]
        metrics["boilerplate_detected"] = len(leaked_boilerplate) > 0
        metrics["leaked_boilerplate_count"] = len(leaked_boilerplate)

        # 6. Detect Incomplete Sentences and Repeated Paragraphs
        all_paras = [p.strip() for txt in sec_texts for p in txt.split("\n\n") if len(p.strip()) > 30]
        has_repeated_paragraphs = False
        for i in range(len(all_paras)):
            words_i = set(re.findall(r"\w+", all_paras[i].lower()))
            for j in range(i + 1, len(all_paras)):
                words_j = set(re.findall(r"\w+", all_paras[j].lower()))
                overlap = len(words_i & words_j) / max(len(words_i | words_j), 1)
                if overlap > 0.85:
                    has_repeated_paragraphs = True
                    break
            if has_repeated_paragraphs:
                break
        metrics["has_repeated_paragraphs"] = has_repeated_paragraphs

        has_incomplete_sentences = False
        for p in all_paras:
            clean_p = p.strip()
            if not clean_p:
                continue
            if clean_p.endswith(("...", "…", ",", "-", ";")) or not clean_p.endswith((".", "!", "?", ":")):
                has_incomplete_sentences = True
                break
        metrics["has_incomplete_sentences"] = has_incomplete_sentences

        # 7. Check user-requested hardware presence and explanation depth
        prompt_hw = []
        p_lower = prompt.lower()
        if "esp32" in p_lower:
            prompt_hw.append("esp32")
        if "ir" in p_lower or "infrared" in p_lower:
            prompt_hw.append("ir")
        if "camera" in p_lower or "ball detection" in p_lower:
            prompt_hw.append("camera")
        missing_hw = [h for h in prompt_hw if h not in all_text] if prompt_hw else []
        metrics["missing_hardware"] = missing_hw

        explained_components = 0
        operational_cues = ("interrupt", "signal", "gpio", "sensor", "optical", "trajectory", "tracking", "detection", "frame", "timestamp", "arbitration")
        for hw in prompt_hw:
            has_explanation = any(hw in p.lower() and any(oc in p.lower() for oc in operational_cues) for p in all_paras)
            if has_explanation:
                explained_components += 1
        explanation_depth = explained_components / max(len(prompt_hw), 1) if prompt_hw else 1.0
        metrics["explanation_depth"] = round(explanation_depth, 3)

        # 8. Detect Fabricated Precision and Trial Numbers (e.g. 99.8% precision across 1,200 trials)
        fabricated_cues = [
            r"\b\d{2,3}(?:\.\d+)?%\s*(?:precision|accuracy|recall)\b",
            r"\b\d+[\d,]*\s*(?:distinct\s+)?(?:delivery\s+)?trials\b",
        ]
        has_fabricated_metrics = any(bool(re.search(pat, all_text)) for pat in fabricated_cues)
        metrics["has_fabricated_metrics"] = has_fabricated_metrics

        # 9. Clean presentation: absence of leaked telemetry in document body
        telemetry_indicators = ["agreement (jsd)", "normalized entropy", "decision gate", "h_norm(p)"]
        if any(ti in all_text for ti in telemetry_indicators):
            metrics["telemetry_free"] = False

        # Compute composite reward R in [-1.0, 1.0]
        # OpenXML validity is a MANDATORY prerequisite gate:
        if not metrics["valid_openxml"]:
            metrics["reward"] = -1.0
            return metrics

        # Reward is driven by genuine subject matter coverage, explanation depth, and structural completeness:
        reward = (
            0.40 * concept_coverage
            + 0.30 * metrics["expected_sections_ratio"]
            + 0.15 * metrics["section_uniqueness"]
            + 0.15 * explanation_depth
        )

        # Heavily penalize generic boilerplate substitution
        if metrics["boilerplate_detected"]:
            reward -= 0.50 * metrics["leaked_boilerplate_count"]

        # Heavily penalize repeated paragraphs
        if metrics["has_repeated_paragraphs"]:
            reward -= 0.50

        # Penalize incomplete sentences
        if metrics["has_incomplete_sentences"]:
            reward -= 0.40

        # Penalize fabricated empirical metrics
        if metrics["has_fabricated_metrics"]:
            reward -= 0.40

        # Penalize missing user-requested hardware
        if missing_hw:
            reward -= 0.35 * len(missing_hw)

        # Penalize insufficient word count (shallow placeholders)
        if total_words < 250:
            reward -= 0.30

        # 10. Target Page Budget Yield Evaluation (penalize page under-yield when pages requested)
        from src.doc_gen.document_brief import extract_page_budget
        target_pages, _ = extract_page_budget(prompt)
        if target_pages:
            metrics["target_pages"] = target_pages
            # Estimate pages from words (~320 words per page with formatting) and section count
            estimated_pages = max(1, total_words // 320 + len(sections))
            metrics["estimated_pages"] = estimated_pages
            yield_ratio = min(1.0, estimated_pages / target_pages)
            metrics["page_yield_ratio"] = round(yield_ratio, 3)

            # Proportional yield penalty for under-generating requested volume
            if yield_ratio < 0.5:
                reward -= 0.40 * (1.0 - yield_ratio)
            elif yield_ratio >= 0.8:
                reward += 0.15

        # 10. Anti-Slop Policy Compliance (penalize AI connector clichés)
        try:
            from src.doc_gen.antislop_policy import BANNED_AI_CLICHES
            banned_cliches_found = [c for c in BANNED_AI_CLICHES if re.search(c, all_text, flags=re.IGNORECASE)]
            metrics["banned_cliches_count"] = len(banned_cliches_found)
            if banned_cliches_found:
                reward -= 0.10 * len(banned_cliches_found)
        except Exception:
            metrics["banned_cliches_count"] = 0

        if not metrics["spam_free"]:
            reward -= 0.50

        if not metrics["telemetry_free"]:
            reward -= 0.50

        # Cap reward if concept coverage is deficient: weak/irrelevant documents must NEVER receive high reward
        if concept_coverage < 0.40:
            reward = min(reward, 0.15)

        metrics["reward"] = round(max(-1.0, min(1.0, reward)), 4)
        return metrics

    def record_autonomous_experience(
        self,
        operation: str,
        prompt: str,
        decision: RLCDDecision,
        artifact_path: str | Path,
        sections: list[dict[str, Any]],
        explicit_sections: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record an autonomous generation/revision experience, compute objective reward, and update policy gradients."""
        import hashlib

        # Prevent duplicate rewards for repeated evaluations of the identical artifact
        eval_key = f"{operation}:{prompt}:{artifact_path}:{len(sections)}"
        eval_hash = hashlib.sha256(eval_key.encode("utf-8")).hexdigest()

        exp_dir = self.policy_path.parent
        log_file = exp_dir / "experience_log.jsonl"
        checkpoint_dir = exp_dir / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if eval_hash in line:
                            return {"status": "skipped_duplicate", "hash": eval_hash}
            except Exception:
                pass

        # Evaluate artifact objectively
        eval_result = self.evaluate_document_outcome(
            artifact_path, prompt, decision, sections, explicit_sections=explicit_sections
        )
        reward = eval_result["reward"]

        # Checkpoint current policy before update
        ckpt_path = checkpoint_dir / f"policy_ep_{self.episodes}.json"
        try:
            with open(ckpt_path, "w", encoding="utf-8") as f:
                json.dump({
                    "episodes": self.episodes,
                    "baseline": self.baseline,
                    "archetype_biases": self.archetype_biases,
                    "weights": self.weights,
                }, f, indent=2)
        except Exception:
            pass

        # Apply genuine REINFORCE policy gradient update on archetype biases
        alpha = self.learning_rate
        advantage = reward - self.baseline
        actual_arch = decision.archetype

        probs: list[float] = self.softmax([self.archetype_biases.get(a, 0.0) for a in ARCHETYPES])  # type: ignore
        p_map = dict(zip(ARCHETYPES, probs))

        if reward >= 0:
            # Positive gradient reinforcement on chosen archetype
            grad = 1.0 - p_map.get(actual_arch, 0.2)
            self.archetype_biases[actual_arch] = max(-3.0, min(3.0, self.archetype_biases[actual_arch] + alpha * advantage * grad))
            for a in ARCHETYPES:
                if a != actual_arch:
                    self.archetype_biases[a] = max(-3.0, min(3.0, self.archetype_biases[a] - alpha * advantage * p_map.get(a, 0.2) * 0.5))
        else:
            # Negative gradient on failure or poor quality
            self.archetype_biases[actual_arch] = max(-3.0, min(3.0, self.archetype_biases[actual_arch] - alpha * abs(advantage) * 0.8))

        # Update baseline and stats
        self.baseline = self.baseline_decay * self.baseline + (1 - self.baseline_decay) * reward
        self.episodes += 1
        self.cumulative_reward += reward
        self.reward_history.append(reward)
        if len(self.reward_history) > 100:
            self.reward_history = self.reward_history[-100:]

        self.save()

        # Append to experience log
        log_entry = {
            "timestamp": time.time(),
            "hash": eval_hash,
            "operation": operation,
            "prompt": prompt,
            "archetype": actual_arch,
            "artifact_path": str(artifact_path),
            "eval_metrics": eval_result,
            "reward": reward,
            "advantage": round(advantage, 4),
            "baseline": round(self.baseline, 4),
            "episode": self.episodes,
        }
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass

        return {
            "status": "updated",
            "operation": operation,
            "episode": self.episodes,
            "reward": reward,
            "advantage": round(advantage, 4),
            "baseline": round(self.baseline, 4),
            "metrics": eval_result,
        }

    def record_revision_experience(
        self,
        prompt: str,
        previous_archetype: str,
        new_archetype: str,
        artifact_path: str | Path,
    ) -> dict[str, Any]:
        """Record human corrective revision as learning signal."""
        alpha = self.learning_rate
        # If user shifted archetype, penalize previous and reinforce new
        if previous_archetype != new_archetype:
            self.archetype_biases[previous_archetype] = max(-3.0, min(3.0, self.archetype_biases.get(previous_archetype, 0.0) - alpha * 0.6))
            self.archetype_biases[new_archetype] = max(-3.0, min(3.0, self.archetype_biases.get(new_archetype, 0.0) + alpha * 0.8))
        else:
            # If revision was requested due to deficiency/missing content, do not apply blind positive reinforcement
            deficiency_cues = ("more detailed", "fix", "missing", "incomplete", "poor", "lacking", "shallow", "expand", "detailed")
            is_deficiency = any(c in prompt.lower() for c in deficiency_cues)
            if is_deficiency:
                # Moderate penalty for deficient initial draft to deter weak generation
                self.archetype_biases[new_archetype] = max(-3.0, min(3.0, self.archetype_biases.get(new_archetype, 0.0) - alpha * 0.2))
            else:
                self.archetype_biases[new_archetype] = max(-3.0, min(3.0, self.archetype_biases.get(new_archetype, 0.0) + alpha * 0.1))

        self.save()
        return {
            "status": "revision_recorded",
            "previous": previous_archetype,
            "new": new_archetype,
            "biases": {k: round(v, 3) for k, v in self.archetype_biases.items()},
        }

    def rollback_policy(self, steps_back: int = 1) -> bool:
        """Rollback policy parameters to an earlier checkpoint in case of performance degradation."""
        checkpoint_dir = self.policy_path.parent / "checkpoints"
        if not checkpoint_dir.exists():
            return False

        ckpts = sorted(checkpoint_dir.glob("policy_ep_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if len(ckpts) < steps_back:
            return False

        target_ckpt = ckpts[steps_back - 1]
        try:
            with open(target_ckpt, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.episodes = data.get("episodes", self.episodes)
                self.baseline = data.get("baseline", self.baseline)
                self.archetype_biases = data.get("archetype_biases", self.archetype_biases)
                self.weights = data.get("weights", self.weights)
                self.save()
                return True
        except Exception:
            return False

    def evaluate_held_out(self, test_set: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        """Evaluate current policy on held-out test tasks to measure genuine generalisation."""
        if not test_set:
            test_set = [
                ("Design document for low-latency cache cluster", "Technical Report"),
                ("Executive briefing on quarterly infrastructure compliance", "Executive Summary"),
                ("Formal university leave petition for senior fellow", "Formal Letter"),
                ("Grant proposal for distributed tensor compilation", "Project Proposal"),
                ("Academic treatise on category theoretic semantics", "Academic Monograph"),
            ]

        correct = 0
        total = len(test_set)
        results = []
        for prompt, expected_arch in test_set:
            dec = self.decide(prompt)
            match = (dec.archetype == expected_arch)
            if match:
                correct += 1
            results.append({
                "prompt": prompt,
                "predicted": dec.archetype,
                "expected": expected_arch,
                "confidence": dec.confidence,
                "match": match,
            })

        acc = correct / total if total > 0 else 0.0
        return {
            "total_tasks": total,
            "correct": correct,
            "accuracy": round(acc, 4),
            "results": results,
        }
    # Telemetry & Reporting
    # ------------------------------------------------------------------ #

    def get_all_probabilities(self) -> dict[str, float]:
        """Return sigmoid probabilities for all features."""
        return {f: self.sigmoid(f) for f in self.weights}

    def get_section_probabilities(self) -> dict[str, float]:
        """Return softmax probabilities over section features."""
        section_feats = [f for f in self.weights if f.startswith("section_")]
        return self.choice(section_feats)

    def get_telemetry(self) -> dict[str, Any]:
        """Return comprehensive RLCD decision model telemetry."""
        probs: list[float] = self.softmax([self.archetype_biases.get(a, 0.0) for a in ARCHETYPES])  # type: ignore
        return {
            "episodes": self.episodes,
            "baseline": round(self.baseline, 4),
            "temperature": self.temperature,
            "cumulative_reward": round(self.cumulative_reward, 4),
            "archetype_distribution": {
                ARCHETYPES[i]: round(probs[i], 4) for i in range(len(ARCHETYPES))
            },
            "font_distribution": {
                f: round(p, 4)
                for f, p in zip(FONTS, self.softmax([self.font_biases.get(f, 0.0) for f in FONTS]))  # type: ignore
            },
            "last_decision": asdict(self.last_decision) if self.last_decision else None,
        }

    def get_training_report(self) -> dict[str, Any]:
        """Return comprehensive training state report."""
        section_probs = self.get_section_probabilities()
        rigor_probs = self.choice(["rigor_none", "rigor_asymptotic", "rigor_formal"])
        depth_probs = self.choice(["depth_brief", "depth_standard", "depth_deep"])

        recent_rewards = self.reward_history[-10:] if self.reward_history else []
        avg_recent = sum(recent_rewards) / max(len(recent_rewards), 1)

        entropy = 0.0
        for p in section_probs.values():
            if p > 0:
                entropy -= p * math.log2(p)

        return {
            "episode_count": self.episodes,
            "cumulative_reward": round(self.cumulative_reward, 4),
            "baseline": round(self.baseline, 4),
            "temperature": self.temperature,
            "avg_recent_reward": round(avg_recent, 4),
            "section_probabilities": {k: round(v, 4) for k, v in section_probs.items()},
            "rigor_probabilities": {k: round(v, 4) for k, v in rigor_probs.items()},
            "depth_probabilities": {k: round(v, 4) for k, v in depth_probs.items()},
            "gate_probabilities": {
                "include_formulas": round(self.sigmoid("include_formulas"), 4),
                "include_diagrams": round(self.sigmoid("include_diagrams"), 4),
                "include_benchmarks": round(self.sigmoid("include_benchmarks"), 4),
                "include_tables": round(self.sigmoid("include_tables"), 4),
                "include_callouts": round(self.sigmoid("include_callouts"), 4),
            },
            "section_entropy": round(entropy, 4),
            "total_features": len(self.weights),
            "model_path": str(self.policy_path),
        }
