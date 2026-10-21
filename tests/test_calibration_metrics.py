"""Dedicated tests for calibration metrics, ECE calculation, and normalized entropy."""

import numpy as np
import pytest

from src.rlcd import (
    compute_brier_score,
    compute_ece,
    compute_normalized_shannon_entropy,
    compute_shannon_entropy,
)
from src.calibrator import (
    CalibratedClassifier,
    CalibratedDecision,
    brier_score,
    shannon_entropy,
    tempered_softmax,
)


def test_ece_edge_cases():
    # Empty inputs
    assert compute_ece([], []) == 0.0

    # Perfectly calibrated predictions:
    # 10 samples with confidence 1.0 all correct (1) -> bin error = 0
    confs = [1.0] * 10
    accs = [1] * 10
    assert np.isclose(compute_ece(confs, accs), 0.0)

    # 10 samples with confidence 0.5 where 5 are correct -> acc = 0.5, conf = 0.5 -> error = 0
    confs_half = [0.5] * 10
    accs_half = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    assert np.isclose(compute_ece(confs_half, accs_half, num_bins=10), 0.0)


def test_normalized_entropy_properties():
    # For any K > 1, normalized entropy must be in [0.0, 1.0]
    for k in [2, 3, 5, 8, 16, 32]:
        uniform = [1.0 / k] * k
        norm_h = compute_normalized_shannon_entropy(uniform)
        assert np.isclose(norm_h, 1.0, atol=1e-5)

    # Skewed distribution should have 0 < norm_h < 1
    skewed = [0.90, 0.05, 0.03, 0.02]
    norm_skewed = compute_normalized_shannon_entropy(skewed)
    assert 0.0 < norm_skewed < 0.5


def test_calibrated_decision_dataclass_fields():
    dec = CalibratedDecision(
        subject="CS2227",
        confidence=0.92,
        entropy=0.45,
        status="CONFIDENT",
        ranking=[("CS2227", 0.92), ("CS2000", 0.08)],
        agreement=0.95,
        disagreement=0.05,
        normalized_entropy=0.15,
    )
    assert dec.confident
    assert dec.normalized_entropy == 0.15
    assert dec.agreement == 0.95
