"""Unit tests for the RLCD (Reinforcement Learning from Classifier Disagreement) engine."""

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
    compute_jensen_shannon_divergence,
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


def test_rlcd_policy_store():
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
        )
        assert reward1 > 0
        assert store.episodes == 1
        assert store.agreements_count == 1
        assert store.biases["CS2227"] > 0
        assert "CS2227" in store.centroids

        # Feedback 2: User overrides prediction
        reward2 = store.record_feedback(
            chosen_category="CS2000",
            predicted_category="CS2227",
            agreement=0.40,
            is_override=True,
            doc_embedding=np.array([0.0, 1.0, 0.0]),
        )
        assert store.episodes == 2
        assert store.overrides_count == 1
        assert store.biases["CS2000"] > 0

        # Test reload from disk
        store2 = RLCDPolicyStore(policy_path)
        assert store2.episodes == 2
        assert store2.overrides_count == 1
        assert "CS2227" in store2.biases


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
