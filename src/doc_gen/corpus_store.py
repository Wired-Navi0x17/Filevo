"""Local corpus store for Filevo: persistent, retrievable source knowledge.

The knowledge base (``knowledge_base.py``) records how documents *look* — fonts,
heading hierarchies, archetypes. It has never stored what documents *say*. This
module stores the actual source text that generated documents cite.

Design notes
------------
Storage
    SQLite with FTS5 (both in the Python standard library, so no new
    dependency). Chunks live in a normal table; FTS5 indexes them as external
    content with triggers keeping the index in sync.

Retrieval
    Hybrid. BM25 via FTS5 finds exact terminology; MiniLM embeddings find
    paraphrase. Results are fused with Reciprocal Rank Fusion, which needs no
    score normalisation between the two sources.

    The dense path is optional on purpose. If ``transformers`` or ``numpy``
    cannot load, the store degrades to lexical-only and reports that it did,
    rather than raising.
    
Provenance
    Every chunk carries ``source_id``; every source carries ``url``, ``title``,
    ``license`` and ``fetched_at``. Citations are therefore assembled from ids
    the document actually used, never from text the model produced. Retrofitting
    those columns later would force re-ingesting the whole corpus, so they are
    present from the first version.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

# Chunk sizing. ~200 words is small enough for precise retrieval and large
# enough to hold a coherent argument, and three of them fit comfortably in the
# 8k context window alongside the document plan.
TARGET_CHUNK_WORDS = 200
MIN_CHUNK_WORDS = 40
CHUNK_OVERLAP_WORDS = 40

RRF_K = 60

# Source sections that never contain usable evidence. Wikipedia's rendered
# plaintext includes these verbatim, and without this filter a query like
# "history of classification" matches the "External links" section first.
BOILERPLATE_HEADINGS = {
    "external links", "references", "see also", "further reading", "notes",
    "bibliography", "citations", "sources", "footnotes", "gallery", "literature",
    "works cited", "further information", "media", "navigation",
}

LICENSE_BY_DOMAIN = {
    "wikipedia.org": "CC BY-SA 4.0 (attribution + share-alike)",
    "wikimedia.org": "CC BY-SA 4.0 (attribution + share-alike)",
    "arxiv.org": "arXiv (per-paper licence — verify before reuse)",
    "gutenberg.org": "Public domain",
    "nasa.gov": "Public domain (US Government work)",
    "noaa.gov": "Public domain (US Government work)",
    "who.int": "CC BY-NC-SA (non-commercial)",
    "openstax.org": "CC BY 4.0",
}

DISAMBIGUATION_SIGNATURES = (
    "may refer to",
    "can refer to",
    "most often refers to",
    "commonly refers to",
    "is a disambiguation",
)

_HEADING_RE = re.compile(r"^\s*(={2,6})\s*(.+?)\s*={2,6}\s*$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]+")
_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "they", "have", "has",
    "are", "was", "were", "which", "their", "there", "these", "those", "into",
    "such", "also", "been", "more", "most", "other", "some", "than", "then",
    "when", "what", "where", "while", "about", "because", "would", "could",
    "should", "your", "you", "its", "it's", "not", "but", "can", "may",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT 'unknown',
    fetched_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL DEFAULT 0,
    heading_path TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    n_words INTEGER NOT NULL DEFAULT 0,
    vector BLOB
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, heading_path, content='chunks', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, heading_path)
    VALUES (new.id, new.text, new.heading_path);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, heading_path)
    VALUES ('delete', old.id, old.text, old.heading_path);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, heading_path)
    VALUES ('delete', old.id, old.text, old.heading_path);
    INSERT INTO chunks_fts(rowid, text, heading_path)
    VALUES (new.id, new.text, new.heading_path);
END;
"""


@dataclass
class IngestResult:
    """Outcome of one ingestion attempt."""

    url: str
    status: str  # "ingested" | "skipped" | "failed"
    chunks: int = 0
    words: int = 0
    message: str = ""


class _Embedder:
    """Optional MiniLM sentence embedder.

    Loaded through ``transformers`` directly rather than
    ``sentence-transformers`` so no extra dependency is required. Failure is
    non-fatal: the store falls back to lexical retrieval.
    """

    MODEL_GLOB = "models--sentence-transformers--all-MiniLM-L6-v2/snapshots/*"

    def __init__(self, home: Path | None = None):
        self._model = None
        self._tokenizer = None
        self._tried = False
        self._error: str | None = None
        self._home = home or Path.home()

    @property
    def available(self) -> bool:
        return self._model is not None

    @property
    def error(self) -> str | None:
        return self._error

    def _locate(self) -> str | None:
        base = self._home / ".cache" / "huggingface" / "hub"
        matches = sorted(base.glob(self.MODEL_GLOB))
        for path in matches:
            if (path / "config.json").exists() and (path / "model.safetensors").exists():
                return str(path)
        return None

    def load(self) -> bool:
        if self._tried:
            return self._model is not None
        self._tried = True
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            path = self._locate()
            if not path:
                self._error = "MiniLM weights not present in the Hugging Face cache"
                return False
            self._tokenizer = AutoTokenizer.from_pretrained(path)
            self._model = AutoModel.from_pretrained(path)
            self._model.eval()
            self._torch = torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model.to(device)
            self._device = device
            return True
        except Exception as exc:  # pragma: no cover - environment dependent
            self._error = f"{type(exc).__name__}: {exc}"
            self._model = None
            return False

    def encode(self, texts: Iterable[str], batch_size: int = 16) -> Any:
        """Return a normalised float32 matrix of embeddings."""
        import numpy as np

        if not self.load():
            return None
        texts = list(texts)
        if not texts:
            return np.zeros((0, 384), dtype="float32")

        vectors = []
        with self._torch.no_grad():
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                encoded = self._tokenizer(
                    batch, padding=True, truncation=True, max_length=256, return_tensors="pt"
                ).to(self._device)
                out = self._model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).float()
                pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-6)
                pooled = self._torch.nn.functional.normalize(pooled, dim=1)
                vectors.append(pooled.cpu().numpy())
        return np.vstack(vectors).astype("float32")


def _content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOP_WORDS}


def chunk_text(
    text: str,
    target_words: int = TARGET_CHUNK_WORDS,
    min_words: int = MIN_CHUNK_WORDS,
) -> list[tuple[str, str]]:
    """Split source text into (heading_path, chunk) pairs.

    Headings are taken from MediaWiki ``== Heading ==`` markers when present,
    which lets each chunk carry the section it came from. That heading is then
    stored alongside the text and searched by FTS5, so retrieval can match a
    document's section to the source section it belongs to.
    """
    current_heading = ""
    heading_stack: list[tuple[int, str]] = []
    skip_level: int | None = None
    paragraphs: list[tuple[str, str]] = []

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            # Keep the full path ("Roots > Types of roots") so the tree builder
            # knows how sections nest; == is level 2, === level 3, and so on.
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current_heading = " > ".join(t for _, t in heading_stack)
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and title.lower().strip(" .") in BOILERPLATE_HEADINGS:
                skip_level = level
            continue
        if skip_level is not None:
            continue
        paragraphs.append((current_heading, line))

    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    buffer_heading = ""
    buffer_words = 0

    def flush() -> None:
        nonlocal buffer, buffer_words
        if not buffer:
            return
        joined = " ".join(buffer).strip()
        if len(joined.split()) >= min_words:
            chunks.append((buffer_heading, joined))
        buffer = []
        buffer_words = 0

    for heading, paragraph in paragraphs:
        words = paragraph.split()
        if buffer and heading != buffer_heading:
            flush()
        buffer_heading = heading or buffer_heading

        # Split an over-long paragraph so no chunk wildly exceeds the target.
        while len(words) > target_words * 2:
            head, words = words[:target_words], words[target_words:]
            flush()
            buffer_heading = heading or buffer_heading
            buffer = [" ".join(head)]
            buffer_words = target_words
            flush()

        buffer.append(" ".join(words))
        buffer_words += len(words)
        if buffer_words >= target_words:
            overlap_count = min(CHUNK_OVERLAP_WORDS, max(0, target_words // 4))
            overlap = " ".join(" ".join(buffer).split()[-overlap_count:]) if overlap_count else ""
            flush()
            if overlap:
                buffer = [overlap]
                buffer_words = len(overlap.split())

    flush()
    return chunks


def normalize_whitespace(text: str) -> str:
    """Collapse the punctuation debris left behind by request parsing."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(?:,\s*)+", ", ", text)
    text = re.sub(r"\s+([.;:])", r"\1", text)
    text = re.sub(r"[,;:\s]+$", "", text)
    return text.strip()


def license_for_url(url: str) -> str:
    domain = urllib.parse.urlparse(url).netloc.removeprefix("www.").lower()
    for key, lic in LICENSE_BY_DOMAIN.items():
        if domain == key or domain.endswith("." + key):
            return lic
    return "unknown"


class CorpusStore:
    """Persistent local source corpus with hybrid retrieval."""

    def __init__(self, storage_dir: str | Path | None = None, embedder: _Embedder | None = None):
        self.storage_dir = (
            Path(storage_dir) if storage_dir else Path.home() / ".filevo" / "corpus"
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_dir / "corpus.db"
        self.manifest_path = self.storage_dir / "sources.json"
        self.embedder = embedder if embedder is not None else _Embedder()
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._vector_cache: list[tuple[int, Any]] | None = None
        from src.doc_gen.knowledge_tree import KnowledgeTree
        self.tree = KnowledgeTree(self._conn, self.embedder)

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

    def ingest_document(
        self,
        url: str,
        text: str,
        title: str | None = None,
        license_name: str | None = None,
        replace: bool = False,
    ) -> IngestResult:
        """Store one source. Unchanged sources are skipped by content hash."""
        text = text.strip()
        if len(text.split()) < 40:
            return IngestResult(url=url, status="failed", message="source text too short")

        lead_words = " ".join(text.split()[:60]).lower()
        if any(sig in lead_words for sig in DISAMBIGUATION_SIGNATURES):
            return IngestResult(url=url, status="skipped", message="disambiguation page — not citable")

        content_hash = self.hash_text(text)
        domain = urllib.parse.urlparse(url).netloc.removeprefix("www.")
        title = normalize_whitespace(title or domain or url)
        license_name = license_name or license_for_url(url)

        existing = self._conn.execute(
            "SELECT id, content_sha256 FROM sources WHERE url = ?", (url,)
        ).fetchone()

        if existing and existing["content_sha256"] == content_hash and not replace:
            return IngestResult(url=url, status="skipped", message="unchanged (sha-256 match)")

        if existing:
            self._conn.execute("DELETE FROM chunks WHERE source_id = ?", (existing["id"],))
            self._conn.execute("DELETE FROM sources WHERE id = ?", (existing["id"],))

        chunks = chunk_text(text)
        if not chunks:
            return IngestResult(url=url, status="failed", message="no usable chunks")

        fetched_at = datetime.now().isoformat(timespec="seconds")
        words = len(text.split())

        cursor = self._conn.execute(
            """INSERT INTO sources (url, title, domain, license, fetched_at, content_sha256, word_count)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (url, title, domain, license_name, fetched_at, content_hash, words),
        )
        source_id = int(cursor.lastrowid)

        vectors = None
        if self.embedder.available or self.embedder.load():
            vectors = self.embedder.encode([c[1] for c in chunks])

        for seq, (heading_path, chunk) in enumerate(chunks):
            blob = None
            if vectors is not None and seq < len(vectors):
                blob = vectors[seq].tobytes()
            self._conn.execute(
                """INSERT INTO chunks (source_id, seq, heading_path, text, n_words, vector)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source_id, seq, heading_path, chunk, len(chunk.split()), blob),
            )

        self._conn.commit()
        self._vector_cache = None
        self._write_manifest()

        return IngestResult(
            url=url, status="ingested", chunks=len(chunks), words=words, message=title
        )

    def _write_manifest(self) -> None:
        """Maintain a human-readable mirror of provenance for auditing."""
        import json

        rows = self._conn.execute(
            "SELECT url, title, domain, license, fetched_at, word_count FROM sources ORDER BY fetched_at"
        ).fetchall()
        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "sources": [dict(r) for r in rows],
        }
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #

    @staticmethod
    def _fts_query(query: str, max_terms: int = 14) -> str:
        terms = [
            w for w in _WORD_RE.findall(query.lower())
            if len(w) > 2 and w not in _STOP_WORDS
        ]
        # Preserve order, drop duplicates.
        seen: list[str] = []
        for term in terms:
            if term not in seen:
                seen.append(term)
        seen = seen[:max_terms]
        return " OR ".join(f'"{t}"' for t in seen)

    def _lexical_rank(self, query: str, limit: int = 40) -> list[int]:
        match_expr = self._fts_query(query)
        if not match_expr:
            return []
        try:
            rows = self._conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
                "ORDER BY bm25(chunks_fts) LIMIT ?",
                (match_expr, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [int(r["rowid"]) for r in rows]

    def _all_vectors(self) -> list[tuple[int, Any]]:
        if self._vector_cache is not None:
            return self._vector_cache
        import numpy as np

        rows = self._conn.execute(
            "SELECT id, vector FROM chunks WHERE vector IS NOT NULL"
        ).fetchall()
        cache: list[tuple[int, Any]] = [
            (int(r["id"]), np.frombuffer(r["vector"], dtype="float32")) for r in rows
        ]
        self._vector_cache = cache
        return cache

    def _dense_rank(self, query: str, limit: int = 40) -> list[tuple[int, float]]:
        """Return (chunk_id, cosine similarity) sorted best-first."""
        import numpy as np

        if not self.embedder.available and not self.embedder.load():
            return []
        vectors = self._all_vectors()
        if not vectors:
            return []
        query_vec = self.embedder.encode([query])
        if query_vec is None or len(query_vec) == 0:
            return []
        q = query_vec[0]
        scored = [
            (chunk_id, float(np.dot(q, vec))) for chunk_id, vec in vectors if vec.shape == q.shape
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def retrieve(
        self,
        query: str,
        k: int = 3,
        min_similarity: float = 0.30,
    ) -> list[dict[str, Any]]:
        """Hybrid retrieval fused with Reciprocal Rank Fusion.

        Each hit reports a ``confidence`` value: cosine similarity when the dense
        path is available, otherwise the fraction of query terms present in the
        chunk. Callers can gate on it instead of using a poor match blindly.
        """
        lexical = self._lexical_rank(query)
        dense = self._dense_rank(query)
        dense_scores = {cid: score for cid, score in dense}

        fused: dict[int, float] = {}
        for rank, chunk_id in enumerate(lexical):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, (chunk_id, _score) in enumerate(dense):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

        if not fused:
            return []

        ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:k]
        query_terms = _content_words(query)

        hits: list[dict[str, Any]] = []
        for chunk_id, rrf_score in ordered:
            row = self._conn.execute(
                """SELECT c.id, c.text, c.heading_path, s.url, s.title, s.domain,
                          s.license, s.fetched_at
                   FROM chunks c JOIN sources s ON s.id = c.source_id
                   WHERE c.id = ?""",
                (chunk_id,),
            ).fetchone()
            if not row:
                continue
            if chunk_id in dense_scores:
                confidence = max(0.0, min(1.0, dense_scores[chunk_id]))
            else:
                overlap = query_terms & _content_words(row["text"])
                confidence = len(overlap) / max(len(query_terms), 1)
            hits.append({
                "chunk_id": int(row["id"]),
                "text": row["text"],
                "heading_path": row["heading_path"],
                "url": row["url"],
                "title": row["title"],
                "domain": row["domain"],
                "license": row["license"],
                "fetched_at": row["fetched_at"],
                "rrf": round(rrf_score, 5),
                "confidence": round(confidence, 3),
                "above_threshold": confidence >= min_similarity,
            })
        return hits

    def grounding_coverage(self, text: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """Measure how well generated sentences are supported by the given chunks.

        Returns the mean per-sentence support, plus any sentences below the
        threshold. This doubles as an objective reward signal for the RLCD
        policy and as the review list for hallucination checks.
        """
        import numpy as np

        sentences = [s.strip() for s in _SENTENCE_RE.split(text) if len(s.strip().split()) >= 4]
        if not sentences or not chunks:
            return {"coverage": 0.0, "sentences": 0, "weak": [], "method": "none"}

        chunk_texts = [c["text"] for c in chunks]
        if self.embedder.available or self.embedder.load():
            sent_vecs = self.embedder.encode(sentences)
            chunk_vecs = self.embedder.encode(chunk_texts)
            if sent_vecs is not None and chunk_vecs is not None and len(chunk_vecs):
                sims = sent_vecs @ chunk_vecs.T
                best = sims.max(axis=1)
                method = "embedding"
            else:
                best, method = self._lexical_support(sentences, chunk_texts)
        else:
            best, method = self._lexical_support(sentences, chunk_texts)

        weak = [
            {"sentence": s, "support": round(float(score), 3)}
            for s, score in zip(sentences, best)
            if score < 0.25
        ]
        return {
            "coverage": round(float(np.mean(best)), 3),
            "sentences": len(sentences),
            "weak": weak[:8],
            "method": method,
        }

    def _lexical_support(self, sentences: list[str], chunks: list[str]):
        chunk_words = [_content_words(c) for c in chunks]
        scores = []
        for sentence in sentences:
            words = _content_words(sentence)
            if not words:
                scores.append(0.0)
                continue
            best = 0.0
            for cw in chunk_words:
                if not cw:
                    continue
                best = max(best, len(words & cw) / len(words))
            scores.append(best)
        return scores, "lexical"

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #

    def profile(self) -> dict[str, Any]:
        """Summarise the corpus for the RLCD decision engine."""
        row = self._conn.execute(
            """SELECT COUNT(*) AS sources, MAX(fetched_at) AS latest,
                      SUM(word_count) AS words
               FROM sources"""
        ).fetchone()
        chunk_row = self._conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        domains = {
            r["domain"]: r["n"]
            for r in self._conn.execute(
                "SELECT domain, COUNT(*) AS n FROM sources GROUP BY domain ORDER BY n DESC"
            ).fetchall()
        }
        licenses = {
            r["license"]: r["n"]
            for r in self._conn.execute(
                "SELECT license, COUNT(*) AS n FROM sources GROUP BY license"
            ).fetchall()
        }
        archetype_hint = None
        if domains:
            academic_domains = {"arxiv.org", "nature.com", "sciencedirect.com", "acm.org", "ieee.org"}
            if any(d in academic_domains for d in domains):
                archetype_hint = "Academic Monograph"
            elif len(domains) == 1 and "wikipedia.org" in domains:
                archetype_hint = "Academic Monograph"
        return {
            "sources": int(row["sources"] or 0),
            "chunks": int(chunk_row["n"] or 0),
            "words": int(row["words"] or 0),
            "latest_fetched": row["latest"],
            "domains": domains,
            "licenses": licenses,
            "archetype_hint": archetype_hint,
            "dense_available": bool(self.embedder.available),
            "knowledge": self.tree.stats(),
        }

    def stats(self) -> dict[str, Any]:
        profile = self.profile()
        profile["db_path"] = str(self.db_path)
        profile["db_size_bytes"] = self.db_path.stat().st_size if self.db_path.exists() else 0
        profile["dense_error"] = self.embedder.error
        profile["oldest_fetched"] = (
            self._conn.execute("SELECT MIN(fetched_at) AS t FROM sources").fetchone()["t"]
        )
        return profile

    def known_urls(self) -> set[str]:
        return {
            r["url"] for r in self._conn.execute("SELECT url FROM sources").fetchall()
        }

    def clear(self) -> None:
        self._conn.execute("DELETE FROM chunks")
        self._conn.execute("DELETE FROM sources")
        self._conn.commit()
        self._vector_cache = None
        self._write_manifest()

    def close(self) -> None:
        self._conn.close()


def build_context_block(hits: list[dict[str, Any]]) -> str:
    """Format retrieved chunks as numbered, citable evidence for the prompt.

    Numbers are assigned here, by code, so the model can only reference sources
    that actually exist. Any bracketed number it invents is stripped afterwards.
    """
    lines = []
    for index, hit in enumerate(hits, start=1):
        lines.append(
            f"[{index}] {hit['title']} ({hit['domain']}, retrieved {hit['fetched_at'][:10]}"
            f" · {hit['license']})"
        )
        if hit.get("heading_path"):
            lines.append(f"Section: {hit['heading_path']}")
        lines.append(hit["text"])
        lines.append("")
    return "\n".join(lines).strip()


def sanitize_citation_markers(text: str, valid: int) -> tuple[str, list[int]]:
    """Drop bracketed citation numbers the model invented; return those used."""
    used: list[int] = []

    def replace(match: re.Match) -> str:
        number = int(match.group(1))
        if 1 <= number <= valid:
            if number not in used:
                used.append(number)
            return match.group(0)
        return ""

    cleaned = re.sub(r"\[(\d{1,3})\]", replace, text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip(), sorted(used)
