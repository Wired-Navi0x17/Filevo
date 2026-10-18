"""Calibrated subject router for the RLCD pipeline.

The classifier embeds a document with a Sentence-Transformer
(``all-MiniLM-L6-v2``), compares it by cosine similarity against a semantic
*centroid* per subject from :mod:`src.taxonomy`, turns those similarities into
a probability distribution with a low-temperature softmax, and reports both the
winning subject and two uncertainty signals:

* **confidence** -- the top probability of the calibrated distribution.
* **entropy**    -- Shannon entropy (base 2) of that distribution.

A decision is marked ``CONFIDENT`` only when the confidence clears
:data:`CONFIDENCE_THRESHOLD` *and* the entropy stays below
:data:`ENTROPY_THRESHOLD`; otherwise it is ``AMBIGUOUS`` and should be routed
for human review.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from .extractors import ExtractedDoc
from .taxonomy import SUBJECT_TAXONOMY, subject_labels

__all__ = [
    "CalibratedClassifier",
    "CalibratedDecision",
    "brier_score",
    "classify_document",
    "classify_extracted",
    "cosine_similarity",
    "shannon_entropy",
    "tempered_softmax",
]

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_TEMPERATURE = 0.15
CONFIDENCE_THRESHOLD = 0.70
ENTROPY_THRESHOLD = 1.5

STATUS_CONFIDENT = "CONFIDENT"
STATUS_AMBIGUOUS = "AMBIGUOUS"


# --------------------------------------------------------------------------- #
# Numeric primitives (pure, easy to unit-test)
# --------------------------------------------------------------------------- #
def tempered_softmax(similarities: list[float] | np.ndarray, temperature: float) -> np.ndarray:
    """Temperature-scaled softmax over similarity scores.

    A small temperature sharpens the distribution; ``T -> 0`` approaches an
    argmax. The maximum is subtracted before exponentiating for numerical
    stability.
    """
    if temperature <= 0:
        raise ValueError("temperature must be strictly positive")

    z = np.asarray(similarities, dtype=np.float64) / float(temperature)
    z = z - np.max(z)
    exp = np.exp(z)
    total = exp.sum()
    if total == 0:  # pragma: no cover - cannot happen with exp of finite values
        return np.full_like(exp, 1.0 / exp.size)
    return exp / total


def shannon_entropy(probabilities: list[float] | np.ndarray) -> float:
    """Shannon entropy in bits: ``H(x) = -sum_k p_k * log2(p_k)``."""
    p = np.asarray(probabilities, dtype=np.float64)
    p = p[p > 0.0]
    if p.size == 0:
        return 0.0
    return float(-np.sum(p * np.log2(p)))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors."""
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def brier_score(probabilities: list[float], ground_truth_idx: int) -> float:
    """Multiclass Brier score: ``sum_k (p_k - y_k)^2`` with one-hot ``y``.

    Lower is better. ``0.0`` is a perfect, fully confident correct prediction;
    ``1.0`` is a fully confident *wrong* prediction. This measures the quality
    of the calibration, not just the argmax correctness.
    """
    p = np.asarray(probabilities, dtype=np.float64).ravel()
    if p.size == 0:
        raise ValueError("probabilities must be non-empty")
    if not 0 <= ground_truth_idx < p.size:
        raise ValueError(
            f"ground_truth_idx {ground_truth_idx} out of range for {p.size} classes"
        )

    target = np.zeros_like(p)
    target[ground_truth_idx] = 1.0
    return float(np.sum((p - target) ** 2))


# --------------------------------------------------------------------------- #
# Decision record
# --------------------------------------------------------------------------- #
@dataclass
class CalibratedDecision:
    """Result of routing one document to a subject."""

    subject: str
    confidence: float
    entropy: float
    status: str
    ranking: list[tuple[str, float]]


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #
def _ensure_ca_bundle() -> None:
    """Point Python/requests at a CA bundle when the environment lacks one.

    NixOS installations frequently ship an OpenSSL that cannot locate the
    system trust store from inside a virtualenv, which makes the model
    download fail with ``CERTIFICATE_VERIFY_FAILED``. Setting ``SSL_CERT_FILE``
    from certifi is a no-op on healthy systems.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi

        bundle = certifi.where()
    except Exception:  # pragma: no cover - certifi is a std dependency here
        return
    os.environ.setdefault("SSL_CERT_FILE", bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)


def _subject_facets(subject: dict) -> list[str]:
    """Build the text facets whose embeddings form a subject centroid."""
    code = subject.get("code", "")
    name = subject.get("name", "")
    keywords = list(subject.get("keywords", []))
    syllabus = subject.get("syllabus", "")

    facets = [
        f"{code} {name}".strip(),
        f"{name}. Core topics: " + ", ".join(keywords),
        syllabus,
    ]
    # Additional chunks keep long keyword lists from being diluted in one facet.
    for start in range(0, len(keywords), 12):
        facets.append(f"{name}: " + ", ".join(keywords[start : start + 12]))
    return [f for f in facets if f.strip()]


class CalibratedClassifier:
    """Embedding-based, entropy-calibrated subject classifier."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        temperature: float = DEFAULT_TEMPERATURE,
        taxonomy: dict[str, dict] | None = None,
    ) -> None:
        if temperature <= 0:
            raise ValueError("temperature must be strictly positive")
        self.model_name = model_name
        self.temperature = float(temperature)
        self._taxonomy = taxonomy if taxonomy is not None else SUBJECT_TAXONOMY
        self._labels: list[str] = (
            subject_labels() if taxonomy is None else list(self._taxonomy.keys())
        )

        self._model = None
        self._centroids: np.ndarray | None = None

    # -- lazy resources ---------------------------------------------------- #
    def _ensure_model(self):
        if self._model is None:
            _ensure_ca_bundle()
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _ensure_centroids(self) -> np.ndarray:
        if self._centroids is None:
            model = self._ensure_model()
            centroids: list[np.ndarray] = []
            for label in self._labels:
                subject = self._taxonomy[label]
                facets = _subject_facets(subject)
                vectors = model.encode(
                    facets,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                centroid = np.mean(vectors, axis=0)
                norm = np.linalg.norm(centroid)
                if norm > 0:
                    centroid = centroid / norm
                centroids.append(centroid)
            self._centroids = np.vstack(centroids)
        return self._centroids

    # -- inference --------------------------------------------------------- #
    def similarities(self, text: str) -> np.ndarray:
        """Cosine similarity of ``text`` against every subject centroid."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("cannot classify empty text")
        model = self._ensure_model()
        centroids = self._ensure_centroids()
        doc_vec = model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )[0]
        return centroids @ doc_vec

    def probabilities(self, text: str) -> np.ndarray:
        """Calibrated probability distribution over the subjects."""
        return tempered_softmax(self.similarities(text), self.temperature)

    def decide(self, probs: np.ndarray) -> CalibratedDecision:
        """Turn a probability vector into a :class:`CalibratedDecision`."""
        probs = np.asarray(probs, dtype=np.float64)
        ranking = sorted(
            ((label, float(p)) for label, p in zip(self._labels, probs)),
            key=lambda item: item[1],
            reverse=True,
        )
        subject, confidence = ranking[0]
        entropy = shannon_entropy(probs)
        status = (
            STATUS_CONFIDENT
            if confidence >= CONFIDENCE_THRESHOLD and entropy < ENTROPY_THRESHOLD
            else STATUS_AMBIGUOUS
        )
        return CalibratedDecision(
            subject=subject,
            confidence=confidence,
            entropy=entropy,
            status=status,
            ranking=ranking,
        )

    def classify(self, text: str) -> CalibratedDecision:
        """Classify raw document text."""
        return self.decide(self.probabilities(text))

    def classify_document(self, doc: ExtractedDoc) -> CalibratedDecision:
        """Classify an :class:`~src.extractors.ExtractedDoc`."""
        parts = [doc.title, *doc.headings, doc.clean_text]
        text = "\n".join(part for part in parts if part and part.strip())
        return self.classify(text)


# --------------------------------------------------------------------------- #
# Module-level convenience API (shares one lazily-built classifier)
# --------------------------------------------------------------------------- #
_default_classifier: CalibratedClassifier | None = None


def _get_default_classifier() -> CalibratedClassifier:
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = CalibratedClassifier()
    return _default_classifier


def classify_document(text: str) -> CalibratedDecision:
    """Classify raw document text with a shared default classifier."""
    return _get_default_classifier().classify(text)


def classify_extracted(doc: ExtractedDoc) -> CalibratedDecision:
    """Classify an :class:`~src.extractors.ExtractedDoc` with the default model."""
    return _get_default_classifier().classify_document(doc)
