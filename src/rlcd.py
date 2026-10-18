"""RLCD: Reinforcement Learning from Classifier Disagreement.

This module implements a calibrated document routing engine based on
Reinforcement Learning from Classifier Disagreement (RLCD).

Architecture
------------
1. **Dynamic Category Discovery**:
   Discovers destination categories dynamically by inspecting subfolders
   inside the user-configured ``target_root``. If no subfolders exist yet,
   falls back to the standard academic/work taxonomy.

2. **Dual-Perspective Classifiers**:
   - **Lexical Classifier (P_lex)**: Fast surface-token, course code, n-gram,
     and keyword matching with calibrated tempered softmax.
   - **Semantic Bi-Encoder (P_sem)**: Dense 384-dimensional embedding matching
     (using ``all-MiniLM-L6-v2``) against dynamic category prototype centroids.

3. **Classifier Disagreement Quantification**:
   - Jensen-Shannon Divergence D_JS(P_lex || P_sem) in [0, 1] bits.
   - Agreement Metric: Agreement = 1.0 - D_JS.
   - Ensemble Consensus: P_ens = 0.5 * (P_lex + P_sem).
   - Shannon Entropy: H(P_ens) = -sum(P_ens * log2(P_ens)).

4. **Risk-Limiting Gate**:
   A decision is stamped ``CONFIDENT`` only when:
     - Consensus Confidence >= tau (e.g. 0.70)
     - Classifier Agreement >= 0.75 (Disagreement D_JS <= 0.25 bits)
     - Shannon Entropy <= H_max (e.g. 1.50 bits)
   Otherwise, it is marked ``AMBIGUOUS`` and queued for interactive review.

5. **Reinforcement Learning Policy Store (RLCDPolicyStore)**:
   Persists category biases, learned term weights, running centroids, and
   episode telemetry to disk (`~/.config/sortwise/rlcd_policy.json`).
   Applies policy-gradient updates when users confirm or override routing decisions.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .taxonomy import SUBJECT_TAXONOMY, get_subject_taxonomy

__all__ = [
    "RLCDDecision",
    "RLCDPolicyStore",
    "RLCDRouter",
    "build_dynamic_taxonomy",
    "compute_jensen_shannon_divergence",
    "compute_shannon_entropy",
    "discover_target_categories",
    "get_default_policy_store",
    "get_default_router",
    "quick_extract_sample",
    "tempered_softmax",
    "train_prototypes_from_library",
]

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_TEMPERATURE = 0.15
DEFAULT_CONFIDENCE_THRESHOLD = 0.70
DEFAULT_ENTROPY_THRESHOLD = 1.50
MAX_DISAGREEMENT_FOR_CONFIDENT = 0.25  # JSD <= 0.25 bits means Agreement >= 75%

STATUS_CONFIDENT = "CONFIDENT"
STATUS_AMBIGUOUS = "AMBIGUOUS"

_WORD_RE = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------- #
# Math & Information Theory Primitives
# --------------------------------------------------------------------------- #
def normalise_text(text: str) -> str:
    """Normalize text into lowercase alphanumeric space-separated words."""
    if not text:
        return ""
    words = _WORD_RE.findall(text.lower())
    return " ".join(words)


def tempered_softmax(scores: Sequence[float] | np.ndarray, temperature: float = DEFAULT_TEMPERATURE) -> np.ndarray:
    """Compute temperature-scaled softmax probability distribution."""
    if temperature <= 0:
        raise ValueError("temperature must be strictly positive")
    z = np.asarray(scores, dtype=np.float64) / float(temperature)
    if z.size == 0:
        return np.array([], dtype=np.float64)
    z = z - np.max(z)
    exp = np.exp(z)
    total = np.sum(exp)
    if total <= 0:
        return np.full_like(exp, 1.0 / exp.size)
    return exp / total


def compute_shannon_entropy(probabilities: Sequence[float] | np.ndarray) -> float:
    """Shannon entropy in bits: H(P) = -sum p * log2(p)."""
    p = np.asarray(probabilities, dtype=np.float64)
    p = p[p > 0.0]
    if p.size == 0:
        return 0.0
    return float(-np.sum(p * np.log2(p)))


def compute_kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Kullback-Leibler divergence D_KL(P || Q) in bits using log2."""
    eps = 1e-12
    p = np.clip(p, eps, 1.0)
    q = np.clip(q, eps, 1.0)
    p = p / np.sum(p)
    q = q / np.sum(q)
    return float(np.sum(p * np.log2(p / q)))


def compute_jensen_shannon_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Symmetric Jensen-Shannon Divergence D_JS(P || Q) in bits in [0, 1]."""
    p = np.asarray(p, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    if p.size == 0 or q.size == 0 or p.size != q.size:
        return 0.0
    eps = 1e-12
    p = np.clip(p, eps, 1.0)
    q = np.clip(q, eps, 1.0)
    p = p / np.sum(p)
    q = q / np.sum(q)
    m = 0.5 * (p + q)
    jsd = 0.5 * compute_kl_divergence(p, m) + 0.5 * compute_kl_divergence(q, m)
    return float(np.clip(jsd, 0.0, 1.0))


# --------------------------------------------------------------------------- #
# Decision Data Record
# --------------------------------------------------------------------------- #
@dataclass
class RLCDDecision:
    """Result of dual-classifier routing with disagreement & reinforcement telemetry."""

    subject: str
    confidence: float
    entropy: float
    status: str
    agreement: float
    disagreement: float
    p_lex: dict[str, float]
    p_sem: dict[str, float]
    p_ens: dict[str, float]
    ranking: list[tuple[str, float]]

    @property
    def confident(self) -> bool:
        return self.status == STATUS_CONFIDENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "confidence": self.confidence,
            "entropy": self.entropy,
            "status": self.status,
            "agreement": self.agreement,
            "disagreement": self.disagreement,
            "p_lex": self.p_lex,
            "p_sem": self.p_sem,
            "p_ens": self.p_ens,
            "ranking": self.ranking,
        }


# --------------------------------------------------------------------------- #
# Dynamic Category Discovery
# --------------------------------------------------------------------------- #
def discover_target_categories(target_root: str | Path) -> list[str]:
    """Find all existing category subfolders in target_root.

    Returns folder names in alphabetical order. If no subfolders exist,
    returns empty list.
    """
    path = Path(target_root).expanduser().resolve()
    if not path.is_dir():
        return []
    return sorted(
        [
            p.name
            for p in path.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        ],
        key=lambda s: s.lower(),
    )


def build_dynamic_taxonomy(
    target_root: str | Path,
    fallback_taxonomy: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Build a dynamic taxonomy from the subdirectories present in target_root.

    If target_root contains subfolders, each subfolder becomes an active category.
    If a subfolder corresponds to a known academic course, its rich keywords are merged.
    Otherwise, keywords are derived from the directory name and existing files.
    If target_root has no subdirectories, fallback_taxonomy (Semester 3 default) is used.
    """
    known = fallback_taxonomy if fallback_taxonomy is not None else get_subject_taxonomy()
    discovered_names = discover_target_categories(target_root)
    if not discovered_names:
        return copy.deepcopy(known)

    taxonomy: dict[str, dict] = {}
    root_path = Path(target_root).expanduser().resolve()

    for folder_name in discovered_names:
        matched_key = None
        folder_lower = folder_name.lower()
        for k, info in known.items():
            if (
                folder_lower == k.lower()
                or folder_lower == info.get("name", "").lower()
                or folder_lower == info.get("code", "").lower()
            ):
                matched_key = k
                break

        if matched_key:
            entry = copy.deepcopy(known[matched_key])
            taxonomy[folder_name] = entry
        else:
            clean_name = folder_name.replace("-", " ").replace("_", " ")
            parts = [w for w in clean_name.split() if w.strip()]
            code = parts[0] if parts and any(c.isdigit() for c in parts[0]) else ""
            keywords = [clean_name.lower()] + [p.lower() for p in parts if len(p) > 2]

            # Inspect existing files inside the folder to discover topics
            folder_dir = root_path / folder_name
            if folder_dir.is_dir():
                try:
                    for child in folder_dir.iterdir():
                        if child.is_file() and not child.name.startswith("."):
                            stem_words = [
                                w
                                for w in normalise_text(child.stem).split()
                                if len(w) > 3
                            ]
                            keywords.extend(stem_words[:4])
                except OSError:
                    pass

            taxonomy[folder_name] = {
                "code": code,
                "name": clean_name,
                "keywords": sorted(list(dict.fromkeys(keywords))),
                "syllabus": f"Documents, coursework, materials and references concerning {clean_name}.",
            }

    return taxonomy


# --------------------------------------------------------------------------- #
# Reinforcement Learning Policy Store
# --------------------------------------------------------------------------- #
class RLCDPolicyStore:
    """Persistent storage for RLCD policy weights, biases, and centroids.

    Thread-safe and persists to `~/.config/sortwise/rlcd_policy.json`.
    """

    def __init__(self, path: str | Path | None = None, learning_rate: float = 0.05) -> None:
        if path is None:
            config_dir = (
                Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser()
                / "sortwise"
            )
            config_dir.mkdir(parents=True, exist_ok=True)
            self.path = config_dir / "rlcd_policy.json"
        else:
            self.path = Path(path).expanduser().resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self.learning_rate = learning_rate
        self._lock = threading.Lock()
        self.biases: dict[str, float] = {}
        self.term_weights: dict[str, dict[str, float]] = {}
        self.centroids: dict[str, list[float]] = {}
        self.episodes: int = 0
        self.agreements_count: int = 0
        self.overrides_count: int = 0
        self.cumulative_reward: float = 0.0

        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                return
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.biases = data.get("biases", {})
                self.term_weights = data.get("term_weights", {})
                self.centroids = data.get("centroids", {})
                self.episodes = int(data.get("episodes", 0))
                self.agreements_count = int(data.get("agreements_count", 0))
                self.overrides_count = int(data.get("overrides_count", 0))
                self.cumulative_reward = float(data.get("cumulative_reward", 0.0))
            except Exception:
                pass

    def save(self) -> None:
        with self._lock:
            data = {
                "biases": self.biases,
                "term_weights": self.term_weights,
                "centroids": self.centroids,
                "episodes": self.episodes,
                "agreements_count": self.agreements_count,
                "overrides_count": self.overrides_count,
                "cumulative_reward": self.cumulative_reward,
            }
            tmp_path = self.path.with_suffix(".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                tmp_path.replace(self.path)
            except Exception:
                if tmp_path.exists():
                    tmp_path.unlink()

    def get_bias(self, category: str) -> float:
        return self.biases.get(category, 0.0)

    def record_feedback(
        self,
        *,
        chosen_category: str,
        predicted_category: str,
        agreement: float,
        is_override: bool,
        doc_embedding: np.ndarray | None = None,
    ) -> float:
        """Apply a policy-gradient reinforcement update from user interaction.

        Returns the computed reward.
        """
        with self._lock:
            self.episodes += 1
            if not is_override:
                # User accepted the system prediction
                reward = float(np.clip(1.0 * agreement, 0.2, 1.0))
                self.agreements_count += 1
                current_bias = self.biases.get(chosen_category, 0.0)
                # Policy gradient update on category bias
                self.biases[chosen_category] = float(
                    current_bias + self.learning_rate * reward
                )
            else:
                # User corrected the system prediction
                reward = -0.5 * (1.0 - agreement)
                self.overrides_count += 1
                # Increase chosen category bias, decrease rejected category bias
                pred_bias = self.biases.get(predicted_category, 0.0)
                chosen_bias = self.biases.get(chosen_category, 0.0)
                self.biases[predicted_category] = float(
                    pred_bias - self.learning_rate * (1.0 - agreement + 0.1)
                )
                self.biases[chosen_category] = float(
                    chosen_bias + self.learning_rate * 1.0
                )

            self.cumulative_reward += reward

            # Update semantic centroid if vector is provided
            if doc_embedding is not None and doc_embedding.size > 0:
                vec = np.asarray(doc_embedding, dtype=np.float64).ravel()
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                    if chosen_category in self.centroids:
                        old_centroid = np.asarray(self.centroids[chosen_category], dtype=np.float64)
                        updated = (1.0 - self.learning_rate) * old_centroid + self.learning_rate * vec
                        updated_norm = np.linalg.norm(updated)
                        if updated_norm > 0:
                            updated = updated / updated_norm
                        self.centroids[chosen_category] = [round(float(x), 6) for x in updated]
                    else:
                        self.centroids[chosen_category] = [round(float(x), 6) for x in vec]

        self.save()
        return reward


# --------------------------------------------------------------------------- #
# RLCD Dual-Perspective Router Engine
# --------------------------------------------------------------------------- #
class RLCDRouter:
    """Reinforcement Learning from Classifier Disagreement Router."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        temperature: float = DEFAULT_TEMPERATURE,
        policy_store: RLCDPolicyStore | None = None,
    ) -> None:
        self.model_name = model_name
        self.temperature = float(temperature)
        self.policy_store = policy_store or get_default_policy_store()

        self._model = None
        self._model_lock = threading.Lock()
        self._cached_centroids: dict[int, dict[str, np.ndarray]] = {}

    def _get_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    # Ensure SSL certificates on Linux/NixOS
                    if not os.environ.get("SSL_CERT_FILE"):
                        try:
                            import certifi
                            bundle = certifi.where()
                            os.environ.setdefault("SSL_CERT_FILE", bundle)
                            os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
                        except Exception:
                            pass
                    try:
                        from sentence_transformers import SentenceTransformer
                        self._model = SentenceTransformer(self.model_name)
                    except Exception:
                        self._model = None
        return self._model

    # -- Classifier 1: Lexical (P_lex) ------------------------------------- #
    def score_lexical(
        self, text: str, taxonomy: dict[str, dict]
    ) -> dict[str, float]:
        """Compute surface lexical and n-gram overlap scores."""
        clean = normalise_text(text)
        padded = f" {clean} " if clean else " "
        tokens = set(clean.split())

        scores: dict[str, float] = {}
        for label, entry in taxonomy.items():
            score = 0.0
            # Incorporate learned policy bias
            score += self.policy_store.get_bias(label)

            code = normalise_text(str(entry.get("code", "")))
            if code and f" {code} " in padded:
                score += 3.5

            name_norm = normalise_text(str(entry.get("name", "")))
            for word in name_norm.split():
                if len(word) > 2 and word in tokens:
                    score += 1.8

            for kw in entry.get("keywords", []):
                kw_norm = normalise_text(str(kw))
                if kw_norm:
                    if " " in kw_norm:
                        if f" {kw_norm} " in padded:
                            score += 2.0
                    elif kw_norm in tokens:
                        score += 1.0

            scores[label] = max(0.0, score)

        return scores

    # -- Classifier 2: Dense Semantic Bi-Encoder (P_sem) ------------------- #
    def _get_centroids(self, taxonomy: dict[str, dict]) -> dict[str, np.ndarray]:
        tax_id = id(taxonomy)
        if tax_id in self._cached_centroids:
            return self._cached_centroids[tax_id]

        centroids: dict[str, np.ndarray] = {}
        model = self._get_model()

        for label, entry in taxonomy.items():
            # Check if policy store has a reinforced centroid
            if label in self.policy_store.centroids:
                vec = np.asarray(self.policy_store.centroids[label], dtype=np.float64)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    centroids[label] = vec / norm
                    continue

            facets = [
                f"{entry.get('code', '')} {entry.get('name', '')}".strip(),
                entry.get("name", ""),
                entry.get("syllabus", ""),
                ", ".join(entry.get("keywords", [])[:15]),
            ]
            facets = [f for f in facets if f.strip()]

            if model is not None and facets:
                try:
                    embeds = model.encode(
                        facets,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                    )
                    mean_vec = np.mean(embeds, axis=0)
                    norm = np.linalg.norm(mean_vec)
                    centroids[label] = mean_vec / norm if norm > 0 else np.zeros(384)
                except Exception:
                    centroids[label] = np.zeros(384)
            else:
                centroids[label] = np.zeros(384)

        self._cached_centroids[tax_id] = centroids
        return centroids

    def score_semantic(
        self, text: str, taxonomy: dict[str, dict]
    ) -> tuple[dict[str, float], np.ndarray | None]:
        """Compute dense semantic cosine similarity against category centroids."""
        model = self._get_model()
        centroids = self._get_centroids(taxonomy)
        scores: dict[str, float] = {}

        if model is None or not text.strip():
            # Graceful lexical fallback for semantics
            lex = self.score_lexical(text, taxonomy)
            return lex, None

        try:
            doc_vec = model.encode(
                [text[:2000]],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )[0]
        except Exception:
            return self.score_lexical(text, taxonomy), None

        for label, centroid in centroids.items():
            if np.linalg.norm(centroid) > 0:
                sim = float(np.dot(centroid, doc_vec))
                # Scale cosine similarity [-1, 1] to positive logit [0, 2]
                scores[label] = max(0.0, (sim + 1.0))
            else:
                scores[label] = 0.0

        return scores, doc_vec

    # -- Disagreement & Consensus Integration ------------------------------ #
    def classify(
        self,
        text: str,
        taxonomy: dict[str, dict],
        *,
        threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        entropy_threshold: float = DEFAULT_ENTROPY_THRESHOLD,
        temperature: float | None = None,
    ) -> tuple[RLCDDecision, np.ndarray | None]:
        """Run dual-perspective classifiers and compute RLCD consensus decision."""
        temp = temperature if temperature is not None else self.temperature
        labels = list(taxonomy.keys())
        if not labels:
            empty = RLCDDecision(
                subject="",
                confidence=0.0,
                entropy=0.0,
                status=STATUS_AMBIGUOUS,
                agreement=0.0,
                disagreement=1.0,
                p_lex={},
                p_sem={},
                p_ens={},
                ranking=[],
            )
            return empty, None

        # 1. Compute scores from both classifiers
        lex_scores = self.score_lexical(text, taxonomy)
        sem_scores, doc_embedding = self.score_semantic(text, taxonomy)

        lex_raw = [lex_scores.get(lbl, 0.0) for lbl in labels]
        sem_raw = [sem_scores.get(lbl, 0.0) for lbl in labels]

        # 2. Tempered Softmax Distributions
        p_lex = tempered_softmax(lex_raw, temp)
        p_sem = tempered_softmax(sem_raw, temp)

        # 3. Disagreement Quantification (Jensen-Shannon Divergence)
        disagreement = compute_jensen_shannon_divergence(p_lex, p_sem)
        agreement = float(np.clip(1.0 - disagreement, 0.0, 1.0))

        # 4. Ensemble Posterior Consensus
        p_ens = 0.5 * (p_lex + p_sem)
        entropy = compute_shannon_entropy(p_ens)

        # 5. Ranking & Winning Category
        ranking_indices = sorted(range(len(labels)), key=lambda i: p_ens[i], reverse=True)
        ranking = [(labels[i], float(p_ens[i])) for i in ranking_indices]

        winner_idx = ranking_indices[0]
        winner_label = labels[winner_idx]
        confidence = float(p_ens[winner_idx])

        # 6. Risk-Limiting Calibrated Gate
        # Confident only when confidence is high AND classifiers strongly agree
        # AND distribution entropy is low
        is_confident = (
            confidence >= threshold
            and disagreement <= MAX_DISAGREEMENT_FOR_CONFIDENT
            and entropy <= entropy_threshold
        )
        status = STATUS_CONFIDENT if is_confident else STATUS_AMBIGUOUS

        p_lex_map = {labels[i]: float(p_lex[i]) for i in range(len(labels))}
        p_sem_map = {labels[i]: float(p_sem[i]) for i in range(len(labels))}
        p_ens_map = {labels[i]: float(p_ens[i]) for i in range(len(labels))}

        decision = RLCDDecision(
            subject=winner_label,
            confidence=confidence,
            entropy=entropy,
            status=status,
            agreement=agreement,
            disagreement=disagreement,
            p_lex=p_lex_map,
            p_sem=p_sem_map,
            p_ens=p_ens_map,
            ranking=ranking,
        )
        return decision, doc_embedding


# --------------------------------------------------------------------------- #
# Module Singletons
# --------------------------------------------------------------------------- #
_default_policy_store: RLCDPolicyStore | None = None
_default_router: RLCDRouter | None = None


def get_default_policy_store() -> RLCDPolicyStore:
    global _default_policy_store
    if _default_policy_store is None:
        _default_policy_store = RLCDPolicyStore()
    return _default_policy_store


def get_default_router() -> RLCDRouter:
    global _default_router
    if _default_router is None:
        _default_router = RLCDRouter(policy_store=get_default_policy_store())
    return _default_router


# --------------------------------------------------------------------------- #
# Library Document Training & Quick Sampling
# --------------------------------------------------------------------------- #
def quick_extract_sample(path: str | Path, max_chars: int = 2000) -> str:
    """Quickly extract leading text from a document to allow content-aware classification."""
    p = Path(path)
    if not p.is_file():
        return ""
    ext = p.suffix.lstrip(".").casefold()
    try:
        if ext in ("txt", "md"):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(max_chars)
        elif ext == "pdf":
            import pymupdf
            doc = pymupdf.open(str(p))
            parts: list[str] = []
            for page in doc[:3]:
                t = page.get_text("text").strip()
                if t:
                    parts.append(t)
                if sum(len(x) for x in parts) >= max_chars:
                    break
            doc.close()
            return "\n".join(parts)[:max_chars]
        elif ext in ("docx", "pptx"):
            from .extractors import extract_document
            edoc = extract_document(str(p))
            return (edoc.title + "\n" + edoc.clean_text)[:max_chars]
    except Exception:
        pass
    return ""


def train_prototypes_from_library(
    target_root: str | Path,
    model_name: str = DEFAULT_MODEL_NAME,
    policy_store: RLCDPolicyStore | None = None,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Train and fine-tune category prototype centroids on the user's actual documents.

    Walks each category folder inside target_root, extracts real text from all
    PDF/DOCX/PPTX/TXT/MD files, computes dense embeddings, averages them into
    ground-truth category centroids, and persists them into the RLCD policy store.
    """
    store = policy_store or get_default_policy_store()
    root = Path(target_root).expanduser().resolve()
    if not root.is_dir():
        return {"status": "error", "message": f"Target root does not exist: {target_root}"}

    from .extractors import extract_document
    router = get_default_router()
    model = router._get_model()

    categories = discover_target_categories(root)
    if not categories:
        return {"status": "error", "message": f"No category subfolders found inside {target_root}"}

    trained_stats: dict[str, int] = {}
    total_docs = 0
    total_words = 0

    for cat_idx, cat in enumerate(categories):
        cat_dir = root / cat
        if not cat_dir.is_dir():
            continue

        cat_texts: list[str] = []
        for file_path in cat_dir.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                ext = file_path.suffix.lstrip(".").casefold()
                if ext in ("pdf", "docx", "pptx"):
                    try:
                        edoc = extract_document(str(file_path))
                        if edoc.clean_text:
                            text_body = f"{edoc.title}\n{' '.join(edoc.headings)}\n{edoc.clean_text[:4000]}"
                            cat_texts.append(text_body)
                            total_words += edoc.word_count
                    except Exception:
                        sample = quick_extract_sample(file_path, 2000)
                        if sample:
                            cat_texts.append(f"{file_path.stem}\n{sample}")
                elif ext in ("txt", "md"):
                    sample = quick_extract_sample(file_path, 2000)
                    if sample:
                        cat_texts.append(f"{file_path.stem}\n{sample}")
                        total_words += len(sample.split())

        if cat_texts:
            total_docs += len(cat_texts)
            trained_stats[cat] = len(cat_texts)
            if model is not None:
                try:
                    embeds = model.encode(cat_texts, convert_to_numpy=True, normalize_embeddings=True)
                    centroid = np.mean(embeds, axis=0)
                    norm = np.linalg.norm(centroid)
                    if norm > 0:
                        centroid = centroid / norm
                        store.centroids[cat] = [round(float(x), 6) for x in centroid]
                except Exception:
                    pass

        if progress_callback:
            try:
                progress_callback(cat, cat_idx + 1, len(categories))
            except Exception:
                pass

    store.save()
    router._cached_centroids.clear()
    return {
        "status": "ok",
        "categories_trained": len(trained_stats),
        "total_documents": total_docs,
        "total_words": total_words,
        "category_counts": trained_stats,
    }
