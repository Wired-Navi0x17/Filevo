"""Knowledge tree: topics arranged as a tree, each holding typed facts.

This lives in the same SQLite file as the source corpus
(``~/.filevo/corpus/corpus.db``). The corpus keeps raw chunks of sources; the
tree keeps what Filevo actually assembles documents from:

    topics   a node in the subject tree (AI/ML > Supervised learning > SVM ...)
    facts    one typed statement attached to a topic (definition, formula, ...)

Every fact carries provenance (``source_id``, optional ``chunk_id``), a
``support`` score saying how well its source backs it, and ``created_by``
(``seed`` for the curated repository data, ``llm`` or ``rule`` for facts
extracted at ingest time). Document text is assembled only from facts, so a
paragraph in a generated document can always be traced back to its source.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Iterable

# The kinds a fact can have. The renderer maps each kind to a block type
# (formula -> equation, algorithm_step -> numbered list, comparison -> table).
FACT_KINDS: tuple[str, ...] = (
    "definition",
    "intuition",
    "formula",
    "algorithm_step",
    "example",
    "comparison",
    "pitfall",
    "application",
    "history",
)

CREATED_BY = ("seed", "llm", "rule")

RRF_K = 60

KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    ord INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    vector BLOB
);
CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(parent_id);

CREATE TABLE IF NOT EXISTS topic_prereqs (
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    requires_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (topic_id, requires_id)
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    ord INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL DEFAULT '',
    latex TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '',
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    support REAL NOT NULL DEFAULT 1.0,
    created_by TEXT NOT NULL DEFAULT 'seed',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sha256 TEXT NOT NULL UNIQUE,
    vector BLOB
);
CREATE INDEX IF NOT EXISTS idx_facts_topic ON facts(topic_id);

CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
    title, summary, content='topics', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS topics_ai AFTER INSERT ON topics BEGIN
    INSERT INTO topics_fts(rowid, title, summary) VALUES (new.id, new.title, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS topics_ad AFTER DELETE ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, title, summary) VALUES ('delete', old.id, old.title, old.summary);
END;
CREATE TRIGGER IF NOT EXISTS topics_au AFTER UPDATE OF title, summary ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, title, summary) VALUES ('delete', old.id, old.title, old.summary);
    INSERT INTO topics_fts(rowid, title, summary) VALUES (new.id, new.title, new.summary);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    text, latex, content='facts', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text, latex) VALUES (new.id, new.text, new.latex);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text, latex) VALUES ('delete', old.id, old.text, old.latex);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE OF text, latex ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text, latex) VALUES ('delete', old.id, old.text, old.latex);
    INSERT INTO facts_fts(rowid, text, latex) VALUES (new.id, new.text, new.latex);
END;
"""

SCHEMA_VERSION = "2"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "topic"


def path_slug(titles: Iterable[str]) -> str:
    return "/".join(slugify(t) for t in titles)


def fact_hash(topic_slug: str, kind: str, text: str, latex: str, payload: str) -> str:
    raw = "\x1f".join((topic_slug, kind, text.strip(), latex.strip(), payload))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class TopicMatch:
    topic_id: int
    slug: str
    title: str
    level: int
    score: float
    confidence: float


@dataclass
class TopicNode:
    """A topic with its facts and children, as handed to the planner."""

    id: int
    slug: str
    title: str
    level: int
    ord: int
    summary: str
    parent_id: int | None
    prereqs: list[int] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)
    children: list["TopicNode"] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "level": self.level,
            "ord": self.ord,
            "summary": self.summary,
            "parent_id": self.parent_id,
            "prereqs": self.prereqs,
            "facts": self.facts,
            "children": [c.to_dict() for c in self.children],
        }


class KnowledgeTree:
    """CRUD and retrieval over the topic tree. Shares the corpus connection."""

    def __init__(self, conn: sqlite3.Connection, embedder: Any = None):
        self._conn = conn
        self._embedder = embedder
        self._conn.executescript(KNOWLEDGE_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('knowledge_schema', ?)",
            (SCHEMA_VERSION,),
        )
        self._conn.commit()
        self._topic_vec_cache: list[tuple[int, Any]] | None = None

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #

    def ensure_source(self, url: str, title: str, license_name: str) -> int:
        row = self._conn.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()
        if row:
            return int(row[0])
        cur = self._conn.execute(
            "INSERT INTO sources(url, title, domain, license, fetched_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (url, title, url.split("://", 1)[0], license_name),
        )
        return int(cur.lastrowid)

    def upsert_topic(
        self,
        titles: list[str],
        summary: str = "",
        ord: int = 0,
        domain: str = "",
        create_parents: bool = True,
    ) -> int:
        """Create or update the topic at ``titles`` (root first). Returns its id.

        With ``create_parents=False`` the parent must already exist; this is
        how ingest-time additions are kept inside the curated tree.
        """
        if not titles:
            raise ValueError("a topic needs at least one title")
        parent_id: int | None = None
        for depth, title in enumerate(titles):
            slug = path_slug(titles[: depth + 1])
            row = self._conn.execute("SELECT id FROM topics WHERE slug = ?", (slug,)).fetchone()
            is_leaf = depth == len(titles) - 1
            if row:
                topic_id = int(row[0])
                if is_leaf and (summary or ord):
                    self._conn.execute(
                        "UPDATE topics SET summary = CASE WHEN ? != '' THEN ? ELSE summary END, "
                        "ord = ?, title = ? WHERE id = ?",
                        (summary, summary, ord, title.strip(), topic_id),
                    )
            else:
                if not is_leaf and not create_parents:
                    raise KeyError(f"parent topic '{slug}' does not exist")
                cur = self._conn.execute(
                    "INSERT INTO topics(parent_id, slug, title, level, ord, summary, domain) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (parent_id, slug, title.strip(), depth, ord if is_leaf else 0,
                     summary if is_leaf else "", domain),
                )
                topic_id = int(cur.lastrowid)
                self._topic_vec_cache = None
            parent_id = topic_id
        return int(parent_id)  # type: ignore[arg-type]

    def add_prereq(self, topic_id: int, requires_slug: str) -> bool:
        row = self._conn.execute("SELECT id FROM topics WHERE slug = ?", (requires_slug,)).fetchone()
        if not row or int(row[0]) == topic_id:
            return False
        self._conn.execute(
            "INSERT OR IGNORE INTO topic_prereqs(topic_id, requires_id) VALUES (?, ?)",
            (topic_id, int(row[0])),
        )
        return True

    def add_fact(
        self,
        topic_id: int,
        kind: str,
        text: str = "",
        latex: str = "",
        payload: Any = None,
        source_id: int | None = None,
        chunk_id: int | None = None,
        support: float = 1.0,
        created_by: str = "seed",
        ord: int = 0,
    ) -> int | None:
        """Insert one fact. Returns its id, or None if an identical fact exists."""
        if kind not in FACT_KINDS:
            raise ValueError(f"unknown fact kind '{kind}'")
        if created_by not in CREATED_BY:
            raise ValueError(f"unknown created_by '{created_by}'")
        if not (text.strip() or latex.strip() or payload):
            return None
        slug = self._conn.execute("SELECT slug FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if not slug:
            raise KeyError(f"topic {topic_id} does not exist")
        payload_json = json.dumps(payload, sort_keys=True) if payload is not None else ""
        digest = fact_hash(slug[0], kind, text, latex, payload_json)
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO facts(topic_id, kind, ord, text, latex, payload_json, source_id, "
            "chunk_id, support, created_by, sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (topic_id, kind, ord, text.strip(), latex.strip(), payload_json, source_id, chunk_id,
             float(max(0.0, min(1.0, support))), created_by, digest),
        )
        return int(cur.lastrowid) if cur.rowcount else None

    def commit(self) -> None:
        self._conn.commit()

    def embed_missing(self, batch: int = 64) -> int:
        """Compute MiniLM vectors for topics and facts that have none."""
        if self._embedder is None or not self._embedder.load():
            return 0
        done = 0
        for table, text_sql in (
            ("topics", "title || '. ' || summary"),
            ("facts", "text || ' ' || latex"),
        ):
            rows = self._conn.execute(
                f"SELECT id, {text_sql} AS t FROM {table} WHERE vector IS NULL"
            ).fetchall()
            for start in range(0, len(rows), batch):
                part = rows[start : start + batch]
                vecs = self._embedder.encode([r[1] or "" for r in part])
                if vecs is None:
                    return done
                self._conn.executemany(
                    f"UPDATE {table} SET vector = ? WHERE id = ?",
                    [(v.astype("float32").tobytes(), r[0]) for v, r in zip(vecs, part)],
                )
                done += len(part)
        self._conn.commit()
        self._topic_vec_cache = None
        return done

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def get_topic_by_slug(self, slug: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM topics WHERE slug = ?", (slug,)).fetchone()

    def find_topic(self, title_or_slug: str) -> sqlite3.Row | None:
        """Look a topic up by full slug, last slug segment or exact title."""
        key = title_or_slug.strip()
        row = self.get_topic_by_slug(key)
        if row:
            return row
        seg = slugify(key)
        row = self._conn.execute(
            "SELECT * FROM topics WHERE slug = ? OR slug LIKE ? OR lower(title) = lower(?) "
            "ORDER BY level LIMIT 1",
            (seg, f"%/{seg}", key),
        ).fetchone()
        return row

    def children(self, topic_id: int | None) -> list[sqlite3.Row]:
        if topic_id is None:
            return self._conn.execute(
                "SELECT * FROM topics WHERE parent_id IS NULL ORDER BY ord, id"
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM topics WHERE parent_id = ? ORDER BY ord, id", (topic_id,)
        ).fetchall()

    def ancestors(self, topic_id: int) -> list[int]:
        out: list[int] = []
        row = self._conn.execute("SELECT parent_id FROM topics WHERE id = ?", (topic_id,)).fetchone()
        while row and row[0] is not None:
            out.append(int(row[0]))
            row = self._conn.execute("SELECT parent_id FROM topics WHERE id = ?", (row[0],)).fetchone()
        return out

    def facts_for(self, topic_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT f.id, f.kind, f.ord, f.text, f.latex, f.payload_json, f.support,
                      f.created_by, f.source_id, f.chunk_id, s.url, s.title AS source_title,
                      s.license
               FROM facts f LEFT JOIN sources s ON s.id = f.source_id
               WHERE f.topic_id = ? ORDER BY f.ord, f.id""",
            (topic_id,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": int(r["id"]),
                "kind": r["kind"],
                "ord": int(r["ord"]),
                "text": r["text"],
                "latex": r["latex"],
                "payload": json.loads(r["payload_json"]) if r["payload_json"] else None,
                "support": float(r["support"]),
                "created_by": r["created_by"],
                "source_id": r["source_id"],
                "chunk_id": r["chunk_id"],
                "source_url": r["url"],
                "source_title": r["source_title"],
                "license": r["license"],
            })
        return out

    def subtree(self, topic_id: int, max_depth: int = 8) -> TopicNode:
        row = self._conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if row is None:
            raise KeyError(f"topic {topic_id} does not exist")
        return self._build_node(row, max_depth)

    def _build_node(self, row: sqlite3.Row, depth_left: int) -> TopicNode:
        tid = int(row["id"])
        prereqs = [
            int(r[0])
            for r in self._conn.execute(
                "SELECT requires_id FROM topic_prereqs WHERE topic_id = ?", (tid,)
            ).fetchall()
        ]
        node = TopicNode(
            id=tid,
            slug=row["slug"],
            title=row["title"],
            level=int(row["level"]),
            ord=int(row["ord"]),
            summary=row["summary"],
            parent_id=row["parent_id"],
            prereqs=prereqs,
            facts=self.facts_for(tid),
        )
        if depth_left > 0:
            node.children = [self._build_node(c, depth_left - 1) for c in self.children(tid)]
        return node

    @staticmethod
    def _fts_query(query: str, max_terms: int = 14) -> str:
        terms = [t.lower() for t in _FTS_TOKEN_RE.findall(query) if len(t) > 2][:max_terms]
        return " OR ".join(f'"{t}"' for t in terms)

    def _lexical_topics(self, query: str, limit: int = 40) -> list[int]:
        fts = self._fts_query(query)
        if not fts:
            return []
        scores: dict[int, float] = {}
        try:
            for r in self._conn.execute(
                "SELECT rowid, bm25(topics_fts, 3.0, 1.0) AS s FROM topics_fts "
                "WHERE topics_fts MATCH ? ORDER BY s LIMIT ?",
                (fts, limit),
            ):
                scores[int(r[0])] = min(scores.get(int(r[0]), 0.0), float(r[1]) * 2.0)
            for r in self._conn.execute(
                "SELECT f.topic_id, bm25(facts_fts) AS s FROM facts_fts "
                "JOIN facts f ON f.id = facts_fts.rowid WHERE facts_fts MATCH ? "
                "ORDER BY s LIMIT ?",
                (fts, limit * 4),
            ):
                tid = int(r[0])
                scores[tid] = scores.get(tid, 0.0) + float(r[1])
        except sqlite3.OperationalError:
            return []
        # bm25() is negative; lower is better.
        return [tid for tid, _ in sorted(scores.items(), key=lambda kv: kv[1])][:limit]

    def _topic_vectors(self) -> list[tuple[int, Any]]:
        if self._topic_vec_cache is not None:
            return self._topic_vec_cache
        import numpy as np

        rows = self._conn.execute("SELECT id, vector FROM topics WHERE vector IS NOT NULL").fetchall()
        self._topic_vec_cache = [(int(r[0]), np.frombuffer(r[1], dtype="float32")) for r in rows]
        return self._topic_vec_cache

    def _dense_topics(self, query: str, limit: int = 40) -> list[tuple[int, float]]:
        if self._embedder is None or not self._embedder.load():
            return []
        import numpy as np

        vecs = self._topic_vectors()
        if not vecs:
            return []
        q = self._embedder.encode([query])
        if q is None or not len(q):
            return []
        q = q[0]
        scored = [(tid, float(np.dot(q, v))) for tid, v in vecs if v.shape == q.shape]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:limit]

    def match_topics(self, query: str, k: int = 8) -> list[TopicMatch]:
        """Hybrid BM25 + MiniLM topic search fused with Reciprocal Rank Fusion."""
        lexical = self._lexical_topics(query)
        dense = self._dense_topics(query)
        dense_scores = dict(dense)
        fused: dict[int, float] = {}
        for rank, tid in enumerate(lexical):
            fused[tid] = fused.get(tid, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, (tid, _s) in enumerate(dense):
            fused[tid] = fused.get(tid, 0.0) + 1.0 / (RRF_K + rank + 1)
        q_words = {t.lower() for t in _FTS_TOKEN_RE.findall(query) if len(t) > 2}
        out: list[TopicMatch] = []
        for tid, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]:
            row = self._conn.execute(
                "SELECT slug, title, level, summary FROM topics WHERE id = ?", (tid,)
            ).fetchone()
            if not row:
                continue
            if tid in dense_scores:
                conf = max(0.0, min(1.0, dense_scores[tid]))
            else:
                words = {t.lower() for t in _FTS_TOKEN_RE.findall(f"{row['title']} {row['summary']}")}
                conf = len(q_words & words) / max(len(q_words), 1)
            out.append(TopicMatch(tid, row["slug"], row["title"], int(row["level"]), score, conf))
        return out

    def stats(self) -> dict[str, Any]:
        topics = self._conn.execute("SELECT count(*) FROM topics").fetchone()[0]
        roots = self._conn.execute("SELECT count(*) FROM topics WHERE parent_id IS NULL").fetchone()[0]
        depth = self._conn.execute("SELECT coalesce(max(level), -1) FROM topics").fetchone()[0]
        by_kind = {
            r[0]: r[1]
            for r in self._conn.execute("SELECT kind, count(*) FROM facts GROUP BY kind")
        }
        by_origin = {
            r[0]: r[1]
            for r in self._conn.execute("SELECT created_by, count(*) FROM facts GROUP BY created_by")
        }
        return {
            "topics": int(topics),
            "roots": int(roots),
            "max_depth": int(depth) + 1,
            "facts": int(sum(by_kind.values())),
            "facts_by_kind": by_kind,
            "facts_by_origin": by_origin,
        }
