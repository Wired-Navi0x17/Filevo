"""Unit tests for the RLCD (Reinforcement Learning Calibrated Decision) engine."""

import tempfile
import json
from pathlib import Path
import numpy as np
import pytest

from src.rlcd import (
    RLCDDecision,
    RLCDPolicyStore,
    RLCDRouter,
    build_dynamic_taxonomy,
    compute_brier_score,
    compute_ece,
    compute_jensen_shannon_divergence,
    compute_normalized_shannon_entropy,
    compute_shannon_entropy,
    discover_target_categories,
    tempered_softmax,
    STATUS_CONFIDENT,
    STATUS_AMBIGUOUS,
)


def test_tempered_softmax():
    scores = [1.0, 2.0, 3.0]
    p_high_temp = tempered_softmax(scores, temperature=10.0)
    p_low_temp = tempered_softmax(scores, temperature=0.05)

    assert len(p_high_temp) == 3
    assert np.isclose(np.sum(p_high_temp), 1.0)
    assert np.isclose(np.sum(p_low_temp), 1.0)

    # Low temperature should sharpen distribution towards argmax
    assert p_low_temp[2] > 0.99

    with pytest.raises(ValueError):
        tempered_softmax(scores, temperature=0.0)


def test_shannon_entropy():
    # Deterministic distribution has 0 entropy
    p_det = [1.0, 0.0, 0.0]
    assert np.isclose(compute_shannon_entropy(p_det), 0.0)

    # Uniform distribution over 2 classes has 1 bit of entropy
    p_uni2 = [0.5, 0.5]
    assert np.isclose(compute_shannon_entropy(p_uni2), 1.0)

    # Uniform distribution over 4 classes has 2 bits of entropy
    p_uni4 = [0.25, 0.25, 0.25, 0.25]
    assert np.isclose(compute_shannon_entropy(p_uni4), 2.0)


def test_normalized_shannon_entropy():
    # Deterministic distribution has 0 normalized entropy
    p_det = [1.0, 0.0, 0.0, 0.0]
    assert np.isclose(compute_normalized_shannon_entropy(p_det), 0.0)

    # Uniform distribution over 2 classes has normalized entropy 1.0
    p_uni2 = [0.5, 0.5]
    assert np.isclose(compute_normalized_shannon_entropy(p_uni2), 1.0)

    # Uniform distribution over 8 classes has normalized entropy 1.0
    p_uni8 = [1.0 / 8.0] * 8
    assert np.isclose(compute_normalized_shannon_entropy(p_uni8), 1.0)

    # Single class has 0 normalized entropy
    assert np.isclose(compute_normalized_shannon_entropy([1.0]), 0.0)


def test_compute_ece_and_brier_score():
    # Expected Calibration Error test
    confidences = [0.9, 0.9, 0.8, 0.2]
    accuracies = [1, 1, 1, 0]
    ece = compute_ece(confidences, accuracies, num_bins=5)
    assert 0.0 <= ece <= 1.0

    # Completely wrong predictions with high confidence should have high ECE
    bad_conf = [0.95, 0.95, 0.95]
    bad_acc = [0, 0, 0]
    assert compute_ece(bad_conf, bad_acc) > 0.80

    # Brier score tests
    assert np.isclose(compute_brier_score([1.0, 0.0], 0), 0.0)
    assert np.isclose(compute_brier_score([1.0, 0.0], 1), 2.0)
    assert np.isclose(compute_brier_score([0.5, 0.5], 0), 0.5)


def test_jensen_shannon_divergence():
    # Identical distributions have 0 divergence
    p1 = np.array([0.7, 0.2, 0.1])
    p2 = np.array([0.7, 0.2, 0.1])
    jsd_same = compute_jensen_shannon_divergence(p1, p2)
    assert np.isclose(jsd_same, 0.0, atol=1e-5)

    # Completely disjoint distributions have maximum divergence (1 bit)
    q1 = np.array([1.0, 0.0])
    q2 = np.array([0.0, 1.0])
    jsd_disjoint = compute_jensen_shannon_divergence(q1, q2)
    assert np.isclose(jsd_disjoint, 1.0, atol=1e-4)

    # Symmetry: JSD(p, q) == JSD(q, p)
    a = np.array([0.8, 0.15, 0.05])
    b = np.array([0.2, 0.5, 0.3])
    assert np.isclose(
        compute_jensen_shannon_divergence(a, b),
        compute_jensen_shannon_divergence(b, a),
    )


def test_dynamic_category_discovery():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "Physics").mkdir()
        (root / "Chemistry").mkdir()
        (root / "Maths").mkdir()
        (root / ".hidden_folder").mkdir()  # should be ignored
        (root / "sample_file.txt").write_text("hello")  # should be ignored

        cats = discover_target_categories(root)
        assert cats == ["Chemistry", "Maths", "Physics"]


def test_build_dynamic_taxonomy():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        ai_dir = root / "CS2227 - AI and ML"
        ai_dir.mkdir()
        custom_dir = root / "Deep-Learning-Projects"
        custom_dir.mkdir()
        (custom_dir / "transformer_research_paper.pdf").write_text("dummy")

        tax = build_dynamic_taxonomy(root)
        assert "CS2227 - AI and ML" in tax
        # Enriched with known keywords
        assert "machine learning" in tax["CS2227 - AI and ML"]["keywords"]

        # Custom folder properly parsed
        assert "Deep-Learning-Projects" in tax
        assert "deep" in tax["Deep-Learning-Projects"]["keywords"]
        assert "transformer" in tax["Deep-Learning-Projects"]["keywords"]


def test_rlcd_policy_store_and_running_mean():
    with tempfile.TemporaryDirectory() as tmp_dir:
        policy_path = Path(tmp_dir) / "rlcd_policy.json"
        store = RLCDPolicyStore(policy_path, learning_rate=0.1)

        assert store.episodes == 0
        assert store.agreements_count == 0

        # Feedback 1: User accepts confident prediction
        reward1 = store.record_feedback(
            chosen_category="CS2227",
            predicted_category="CS2227",
            agreement=0.95,
            is_override=False,
            doc_embedding=np.array([1.0, 0.0, 0.0]),
            confidence=0.92,
        )
        assert reward1 > 0
        assert store.episodes == 1
        assert store.agreements_count == 1
        assert store.biases["CS2227"] > 0
        assert "CS2227" in store.centroids

        # Check running average centroid update:
        old_centroid = np.array(store.centroids["CS2227"])
        reward1_b = store.record_feedback(
            chosen_category="CS2227",
            predicted_category="CS2227",
            agreement=0.90,
            is_override=False,
            doc_embedding=np.array([0.9, 0.1, 0.0]),
            confidence=0.88,
        )
        new_centroid = np.array(store.centroids["CS2227"])
        # Should stay well-aligned (cosine sim > 0.9)
        assert np.dot(old_centroid, new_centroid) > 0.90
        assert store.sample_counts["CS2227"] > 1

        # Feedback 2: User overrides prediction
        reward2 = store.record_feedback(
            chosen_category="CS2000",
            predicted_category="CS2227",
            agreement=0.40,
            is_override=True,
            doc_embedding=np.array([0.0, 1.0, 0.0]),
            confidence=0.45,
        )
        assert store.episodes == 3
        assert store.overrides_count == 1
        assert store.biases["CS2000"] > 0

        # Telemetry & ECE checks
        telemetry = store.get_telemetry()
        assert telemetry["episodes"] == 3
        assert telemetry["agreements_count"] == 2
        assert telemetry["overrides_count"] == 1
        assert 0.0 <= telemetry["ece"] <= 1.0

        # Test reload from disk
        store2 = RLCDPolicyStore(policy_path)
        assert store2.episodes == 3
        assert store2.overrides_count == 1
        assert "CS2227" in store2.biases
        assert "CS2227" in store2.sample_counts


def test_rlcd_routing_and_disagreement():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = RLCDPolicyStore(Path(tmp_dir) / "policy.json")
        router = RLCDRouter(policy_store=store, temperature=0.15)

        taxonomy = {
            "Algorithms": {
                "code": "CS2000",
                "name": "Algorithms",
                "keywords": ["sorting", "quick sort", "graphs", "dijkstra", "dynamic programming"],
                "syllabus": "Algorithm design and complexity",
            },
            "Machine Learning": {
                "code": "CS2227",
                "name": "Machine Learning",
                "keywords": ["neural networks", "gradient descent", "deep learning", "supervised"],
                "syllabus": "Artificial intelligence and statistical learning",
            },
        }

        # Clear document text matching ML
        text = "Neural networks backpropagation gradient descent loss function deep learning"
        decision, _ = router.classify(text, taxonomy)

        assert decision.subject == "Machine Learning"
        assert decision.confidence > 0.70
        assert decision.agreement >= 0.75
        assert decision.status == STATUS_CONFIDENT
        assert decision.ranking[0][0] == "Machine Learning"
        assert 0.0 <= decision.normalized_entropy <= 1.0


def test_quick_extract_sample_and_library_training():
    from src.rlcd import quick_extract_sample, train_prototypes_from_library

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        maths_dir = root / "Maths"
        maths_dir.mkdir()
        (maths_dir / "calculus.txt").write_text(
            "Differential calculus limits derivatives and integrals with applications to volume.",
            encoding="utf-8",
        )

        ai_dir = root / "AI"
        ai_dir.mkdir()
        (ai_dir / "neural_nets.txt").write_text(
            "Deep neural networks supervised machine learning backpropagation loss function.",
            encoding="utf-8",
        )

        # Quick extract sample
        sample = quick_extract_sample(maths_dir / "calculus.txt")
        assert "Differential calculus" in sample

        # Train prototypes from library
        policy_store = RLCDPolicyStore(root / "policy.json")
        res = train_prototypes_from_library(root, policy_store=policy_store)

        assert res["status"] == "ok"
        assert res["categories_trained"] == 2
        assert res["total_documents"] == 2
        assert "Maths" in policy_store.centroids
        assert "AI" in policy_store.centroids


def test_query_chat_explanation():
    from src.rlcd import query_chat_explanation

    taxonomy = {
        "Computer Science": {
            "code": "CS101",
            "name": "Computer Science",
            "keywords": ["algorithms", "python", "programming", "data structures"],
            "syllabus": "Foundations of computing",
        },
        "Literature": {
            "code": "LIT101",
            "name": "Literature",
            "keywords": ["poetry", "prose", "shakespeare", "novel"],
            "syllabus": "Literary analysis",
        },
    }

    result = query_chat_explanation("Algorithms and data structures in Python programming", taxonomy)
    assert result["decision"].subject == "Computer Science"
    assert "Computer Science" in result["explanation"]
    assert "Calibrated Confidence" in result["explanation"]
    assert len(result["top3"]) > 0

