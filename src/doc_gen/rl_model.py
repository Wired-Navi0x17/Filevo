"""Trainable RL Probabilistic Model for Document Generation.

Consolidated with RLCDDecisionEngine to provide a single, unified
calibrated reinforcement learning policy architecture.
"""

from __future__ import annotations

from typing import Any
from src.doc_gen.rlcd_engine import RLCDDecisionEngine


class RLProbabilisticModel(RLCDDecisionEngine):
    """Unified REINFORCE policy gradient model for document generation decisions.

    Features:
    - Unified policy storage shared with RLCDDecisionEngine
    - Jev primitives: Choice (softmax), Score (ordinal level), Noul (sigmoid gate)
    - Empirical calibration (Expected Calibration Error, Brier score, temperature scaling)
    - Proper policy gradient: θ ← θ + α · (R - b) · ∇_θ log π_θ(a|s)
    - Moving average baseline for variance reduction
    - Entropy regularization
    - Trajectory caching for reward attribution
    """

    def __init__(self, model_path: str | None = None, learning_rate: float = 0.05):
        super().__init__(policy_path=model_path, learning_rate=learning_rate)

    def format_live_display(self, update_metrics: dict[str, Any]) -> str:
        """Format a live training update for terminal display."""
        lines = []
        ep = update_metrics.get("episode", self.episodes)
        r = update_metrics.get("reward", 0.0)
        adv = update_metrics.get("advantage", 0.0)
        b = update_metrics.get("baseline", self.baseline)

        lines.append(f"  ╭─── Episode {ep} ───────────────────────────────────────╮")
        lines.append(f"  │ Reward: {r:+.2f}  Advantage: {adv:+.4f}  Baseline: {b:.4f}")

        section_probs = self.get_section_probabilities()
        lines.append("  │")
        lines.append("  │ Section Probabilities:")
        for feat, prob in sorted(section_probs.items(), key=lambda x: -x[1]):
            bar_len = int(prob * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            name = feat.replace("section_", "").capitalize()
            lines.append(f"  │   {name:<15} {bar} {prob:.3f}")

        lines.append("  │")
        lines.append("  │ Gates:")
        for gate in ["include_formulas", "include_diagrams", "include_benchmarks", "include_tables"]:
            p = self.sigmoid(gate)
            indicator = "●" if p > 0.5 else "○"
            name = gate.replace("include_", "").capitalize()
            lines.append(f"  │   {indicator} {name:<15} {p:.3f}")

        lines.append("  ╰──────────────────────────────────────────────────────╯")
        return "\n".join(lines)
