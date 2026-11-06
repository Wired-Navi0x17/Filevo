"""RLCD tree planner: the Python side of the Rust ``filevo_rlcd`` policy.

What this module does, in order:

1. Find candidate topics for a request in the knowledge tree (hybrid search).
2. Compute named features for every candidate topic, child topic and fact
   (relevance to the request, support, kind, cost in words ...), plus the
   genre and theme options read from ``data/genres`` and ``data/themes``.
3. Hand everything to the Rust policy, which walks the tree and returns which
   topics and facts to take, the genre, the theme and the front-matter gates.
4. Repair and score the structure (prerequisite order, no empty headings, no
   duplicate facts), and run the calibrated risk gate on the genre decision.
5. After the document is built, turn its measured quality into a reward and
   apply one REINFORCE update to the policy.

Nothing here names a subject, a genre or a theme. Those come from data files
and the database; the weights that combine them are learned.
"""

from __future__ import annotations

import json
import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.doc_gen.document_brief import extract_page_budget

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"
DEFAULT_POLICY_PATH = Path.home() / ".filevo" / "policy" / "rlcd_tree.json"

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-']+")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "what", "how", "why",
    "does", "explain", "describe", "write", "create", "make", "generate", "docx", "document",
    "report", "guide", "page", "pages", "please", "using", "on", "of", "a", "an", "to", "in",
    "is", "are", "be", "me", "my", "it", "its", "their", "give", "tell", "detail", "detailed",
}


class PolicyUnavailable(RuntimeError):
    pass


def _rust():
    try:
        import filevo_rlcd  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on build
        raise PolicyUnavailable(
            "The RLCD tree policy (Rust module 'filevo_rlcd') is not built. "
            "Run: scripts/build_rlcd.sh"
        ) from exc
    return filevo_rlcd


def content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP and len(w) > 2}


def _overlap(query_words: set[str], text: str) -> float:
    if not query_words:
        return 0.0
    return len(query_words & content_words(text)) / len(query_words)


# ---------------------------------------------------------------------- #
# Data files
# ---------------------------------------------------------------------- #

def load_genres() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "genres").glob("*.json"))]


def load_themes() -> list[dict[str, Any]]:
    out = []
    for p in sorted((DATA / "themes").glob("*.toml")):
        with open(p, "rb") as fh:
            out.append(tomllib.load(fh))
    return out


def load_kind_descriptions() -> dict[str, str]:
    return json.loads((DATA / "policy" / "kinds.json").read_text(encoding="utf-8"))


def load_prior() -> str:
    raw = json.loads((DATA / "policy" / "prior.json").read_text(encoding="utf-8"))
    return json.dumps({k: v for k, v in raw.items() if not k.startswith("_")})


# ---------------------------------------------------------------------- #
# Plan objects
# ---------------------------------------------------------------------- #

@dataclass
class PlanNode:
    topic_id: int
    title: str
    slug: str
    depth: int
    detail: int
    facts: list[dict[str, Any]]
    children: list["PlanNode"] = field(default_factory=list)
    prereqs: list[int] = field(default_factory=list)
    ord: int = 0

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class GenreGate:
    """Calibrated risk gate on the genre decision (two views, as in RLCD)."""

    chosen: str
    confidence: float
    agreement: float
    entropy: float
    status: str
    request_view: dict[str, float]
    policy_view: dict[str, float]


@dataclass
class TreePlan:
    request: str
    genre: dict[str, Any]
    theme: dict[str, Any]
    gates: dict[str, bool]
    nodes: list[PlanNode]
    words_planned: float
    budget_words: float
    target_pages: int | None
    trajectory_json: str
    decisions: int
    genre_gate: GenreGate
    structure: dict[str, Any]
    candidates: list[dict[str, Any]]

    @property
    def n_topics(self) -> int:
        return sum(1 for n in self.nodes for _ in n.walk())

    @property
    def n_facts(self) -> int:
        return sum(len(x.facts) for n in self.nodes for x in n.walk())

    def all_facts(self) -> list[dict[str, Any]]:
        return [f for n in self.nodes for x in n.walk() for f in x.facts]


# ---------------------------------------------------------------------- #
# Cost model
# ---------------------------------------------------------------------- #

def fact_cost(fact: dict[str, Any]) -> float:
    """Estimated words a fact occupies on the page (headings, captions included)."""
    words = len((fact.get("text") or "").split())
    payload = fact.get("payload") or {}
    kind = fact["kind"]
    if kind == "formula":
        return words + 28.0
    if kind == "algorithm_step":
        return words + 8.0 + sum(len(s.split()) + 3 for s in payload.get("steps", []))
    if kind == "comparison":
        rows = payload.get("rows", [])
        cells = sum(len(" ".join(r).split()) for r in rows) + len(" ".join(payload.get("header", [])).split())
        return words + 18.0 + cells * 1.4 + 6.0 * len(rows)
    return float(words) + 4.0


HEADING_COST = 18.0


# ---------------------------------------------------------------------- #
# The planner
# ---------------------------------------------------------------------- #

class TreePlanner:
    def __init__(self, corpus, policy_path: Path | None = None):
        self.corpus = corpus
        self.tree = corpus.tree
        self.embedder = corpus.embedder
        self.policy_path = Path(policy_path) if policy_path else DEFAULT_POLICY_PATH
        rust = _rust()
        self.policy = rust.TreePolicy.load(str(self.policy_path))
        self.policy.apply_prior(load_prior())
        self.genres = load_genres()
        self.themes = load_themes()
        self.kinds = load_kind_descriptions()
        self._desc_vecs: dict[str, Any] | None = None

    # -- embeddings ------------------------------------------------------ #

    def _encode(self, texts: list[str]):
        if self.embedder is None or not self.embedder.load():
            return None
        return self.embedder.encode(texts)

    def _descriptions(self) -> dict[str, Any]:
        if self._desc_vecs is not None:
            return self._desc_vecs
        keys, texts = [], []
        for g in self.genres:
            keys.append(f"genre:{g['id']}")
            texts.append(g["description"])
        for t in self.themes:
            keys.append(f"theme:{t['id']}")
            texts.append(t["description"])
        for k, d in self.kinds.items():
            keys.append(f"kind:{k}")
            texts.append(d)
        vecs = self._encode(texts)
        self._desc_vecs = dict(zip(keys, vecs)) if vecs is not None else {}
        return self._desc_vecs

    @staticmethod
    def _cos(a, b) -> float:
        if a is None or b is None:
            return 0.0
        import numpy as np

        return float(np.dot(a, b))

    def _vec_of(self, table: str, row_id: int):
        import numpy as np

        r = self.corpus._conn.execute(f"SELECT vector FROM {table} WHERE id = ?", (row_id,)).fetchone()
        if not r or r[0] is None:
            return None
        return np.frombuffer(r[0], dtype="float32")

    # -- features -------------------------------------------------------- #

    def _relevance(self, qvec, qwords: set[str], vec, text: str) -> float:
        if qvec is not None and vec is not None:
            return max(0.0, self._cos(qvec, vec))
        return _overlap(qwords, text)

    def _topic_in(self, node, ctx: dict[str, Any], depth: int) -> dict[str, Any]:
        qvec, qwords = ctx["qvec"], ctx["qwords"]
        tvec = self._vec_of("topics", node.id)
        text = f"{node.title}. {node.summary}"
        rel = self._relevance(qvec, qwords, tvec, text)
        match = ctx["match_scores"].get(node.id)
        feats = {
            "bias": 1.0,
            "relevance": rel,
            "is_match": 1.0 if match is not None else 0.0,
            "match_score": match or 0.0,
            "title_overlap": _overlap(qwords, node.title),
            "log_children": math.log1p(len(node.children)),
            "log_facts": math.log1p(len(node.facts)),
            "prereq_of_match": 1.0 if node.id in ctx["prereq_ids"] else 0.0,
        }
        facts_in = []
        n = max(1, len(node.facts))
        for i, f in enumerate(node.facts):
            fvec = self._vec_of("facts", f["id"])
            ftext = " ".join(filter(None, [f.get("text"), f.get("latex")]))
            fx = {
                "bias": 1.0,
                "relevance": self._relevance(qvec, qwords, fvec, ftext),
                "support": float(f.get("support", 1.0)),
                "ord": i / n,
                "length": len(ftext.split()) / 100.0,
                "kind_cue": ctx["kind_cue"].get(f["kind"], 0.0),
            }
            for g in self.genres:
                fx[f"genre_pref@{g['id']}"] = float(g.get("kind_preference", {}).get(f["kind"], 0.5))
            facts_in.append({"id": f["id"], "kind": f["kind"], "cost": fact_cost(f), "features": fx})
        return {
            "id": node.id,
            "cost": HEADING_COST,
            "features": feats,
            "facts": facts_in,
            "children": [self._topic_in(c, ctx, depth + 1) for c in node.children],
        }

    def _candidates(self, request: str, k: int) -> list[Any]:
        matches = self.tree.match_topics(request, k=k)
        ids = {m.topic_id for m in matches}
        keep = []
        for m in matches:
            if any(a in ids for a in self.tree.ancestors(m.topic_id)):
                continue  # already inside an ancestor's subtree
            keep.append(m)
        return keep, matches

    # -- planning -------------------------------------------------------- #

    def plan(self, request: str, greedy: bool = True, seed: int = 0, k: int = 6,
             max_depth: int = 4) -> TreePlan:
        target_pages, clean = extract_page_budget(request)
        roots, matches = self._candidates(clean, k)
        if not roots:
            raise LookupError(
                "The local database has no knowledge that matches this request. "
                "Load a seed with /seed or turn webfetch on and /ingest sources first."
            )
        qwords = content_words(clean)
        qvec_arr = self._encode([clean])
        qvec = qvec_arr[0] if qvec_arr is not None else None
        desc = self._descriptions()

        kind_sims = {k_: self._cos(qvec, desc.get(f"kind:{k_}")) for k_ in self.kinds}
        mean_sim = sum(kind_sims.values()) / max(1, len(kind_sims))
        kind_cue = {k_: max(0.0, v - mean_sim) * 5.0 for k_, v in kind_sims.items()}

        top = max((m.score for m in matches), default=1.0) or 1.0
        match_scores = {m.topic_id: m.score / top for m in matches}
        prereq_ids: set[int] = set()
        subtrees = []
        for m in roots:
            st = self.tree.subtree(m.topic_id, max_depth=max_depth)
            subtrees.append(st)
            for node in st.walk():
                if node.id in match_scores:
                    prereq_ids.update(node.prereqs)
        ctx = {"qvec": qvec, "qwords": qwords, "match_scores": match_scores,
               "prereq_ids": prereq_ids, "kind_cue": kind_cue}

        wpp_by_theme = {t["id"]: float(t["words_per_page"]) for t in self.themes}
        mean_wpp = sum(wpp_by_theme.values()) / max(1, len(wpp_by_theme))
        budget = float(target_pages) * mean_wpp if target_pages else 0.0

        genre_opts, request_view = [], {}
        for g in self.genres:
            sim = self._cos(qvec, desc.get(f"genre:{g['id']}")) if qvec is not None else _overlap(qwords, g["description"])
            pages_fit = 0.0
            if budget:
                pages_fit = max(0.0, 1.0 - abs(math.log(budget / float(g["default_words"]))) / 3.0)
            genre_opts.append({"id": g["id"], "features": {"sim_description": sim, "pages_fit": pages_fit},
                               "budget_words": float(g["default_words"])})
            request_view[g["id"]] = sim
        theme_opts = []
        for t in self.themes:
            sim = self._cos(qvec, desc.get(f"theme:{t['id']}")) if qvec is not None else _overlap(qwords, t["description"])
            theme_opts.append({"id": t["id"], "features": {"sim_description": sim}})

        global_feats = {
            "has_pages": 1.0 if target_pages else 0.0,
            "log_pages": math.log1p(target_pages or 0),
            "log_request_words": math.log1p(len(clean.split())),
            "n_candidates": float(len(roots)),
        }
        req = {
            "global": global_feats,
            "genres": genre_opts,
            "themes": theme_opts,
            "candidates": [self._topic_in(st, ctx, 0) for st in subtrees],
            "budget_words": budget,
            "hard_cap_ratio": 1.15,
            "max_depth": max_depth,
            "detail_levels": 3,
            "gates": ["toc", "cover", "references"],
            "seed": int(seed),
            "greedy": bool(greedy),
        }
        result = json.loads(self.policy.plan(json.dumps(req)))

        by_id = {node.id: node for st in subtrees for node in st.walk()}
        facts_by_id = {f["id"]: f for node in by_id.values() for f in node.facts}

        def build(pt: dict[str, Any]) -> PlanNode:
            node = by_id[pt["id"]]
            return PlanNode(
                topic_id=node.id, title=node.title, slug=node.slug, depth=pt["depth"],
                detail=pt["detail"], facts=[facts_by_id[i] for i in pt["facts"]],
                children=[build(c) for c in pt["children"]], prereqs=node.prereqs, ord=node.ord,
            )

        nodes = [build(t) for t in result["topics"]]
        structure = repair_structure(nodes)
        genre = next(g for g in self.genres if g["id"] == result["genre"])
        theme = next(t for t in self.themes if t["id"] == result["theme"])
        gate = genre_risk_gate(request_view, dict(result["genre_probs"]), result["genre"])
        return TreePlan(
            request=request, genre=genre, theme=theme, gates=result["gates"], nodes=nodes,
            words_planned=float(result["words_planned"]), budget_words=float(result["budget_words"]),
            target_pages=target_pages, trajectory_json=json.dumps(result["trajectory"]),
            decisions=int(result["decisions"]), genre_gate=gate, structure=structure,
            candidates=[{"topic_id": m.topic_id, "title": m.title, "score": round(m.score, 5),
                         "confidence": round(m.confidence, 3)} for m in matches],
        )

    # -- learning -------------------------------------------------------- #

    def learn(self, plan: TreePlan, reward: float) -> dict[str, Any]:
        stats = json.loads(self.policy.update(plan.trajectory_json, float(reward)))
        self.policy.save(str(self.policy_path))
        return stats

    def telemetry(self) -> dict[str, Any]:
        data = json.loads(self.policy.to_json())
        hist = data.get("reward_history", [])
        return {
            "episodes": data.get("episodes", 0),
            "baseline": round(data.get("baseline", 0.0), 4),
            "families": sorted(data.get("families", {}).keys()),
            "mean_reward_last_20": round(sum(hist[-20:]) / max(1, len(hist[-20:])), 4) if hist else None,
            "policy_path": str(self.policy_path),
        }


# ---------------------------------------------------------------------- #
# Structure: repair and measure
# ---------------------------------------------------------------------- #

def repair_structure(nodes: list[PlanNode]) -> dict[str, Any]:
    """Make the planned tree structurally sound and report what had to change.

    Rules (structural only, they never add content):
    * siblings keep their curated order, except that a prerequisite that is in
      the same sibling group is moved in front of the topic that needs it;
    * a fact already used elsewhere in the document is not repeated;
    * a heading with nothing under it is removed.
    """
    violations = 0
    seen_facts: set[int] = set()
    total = 0

    def fix(group: list[PlanNode]) -> list[PlanNode]:
        nonlocal violations, total
        group.sort(key=lambda n: n.ord)
        ids = [n.topic_id for n in group]
        ordered: list[PlanNode] = []
        placed: set[int] = set()
        pending = list(group)
        guard = 0
        while pending and guard < 10_000:
            guard += 1
            for n in list(pending):
                need = [p for p in n.prereqs if p in ids and p not in placed]
                if not need:
                    ordered.append(n)
                    placed.add(n.topic_id)
                    pending.remove(n)
                    break
            else:  # cycle: keep curated order
                ordered.extend(pending)
                break
        if [n.topic_id for n in ordered] != [n.topic_id for n in sorted(group, key=lambda n: n.ord)]:
            violations += 1
        out = []
        for n in ordered:
            total += 1
            unique = [f for f in n.facts if f["id"] not in seen_facts]
            if len(unique) != len(n.facts):
                violations += 1
            n.facts = unique
            seen_facts.update(f["id"] for f in unique)
            n.children = fix(n.children)
            if n.facts or n.children:
                out.append(n)
            else:
                violations += 1
        return out

    nodes[:] = fix(nodes)
    return {
        "topics": total,
        "violations_repaired": violations,
        "structural_accuracy": round(1.0 - violations / max(1, total), 4),
    }


def _jsd(p: list[float], q: list[float]) -> float:
    def kl(a, b):
        return sum(x * math.log2(max(x, 1e-12) / max(y, 1e-12)) for x, y in zip(a, b) if x > 0)

    m = [(x + y) / 2 for x, y in zip(p, q)]
    return max(0.0, min(1.0, 0.5 * kl(p, m) + 0.5 * kl(q, m)))


def genre_risk_gate(request_view: dict[str, float], policy_view: dict[str, float], chosen: str,
                    sharpness: float = 14.0) -> GenreGate:
    """Two views of the genre, as in RLCD: how the request reads (similarity
    to each genre's description) and what the learned policy chose."""
    keys = list(policy_view.keys())
    z = [request_view.get(k, 0.0) * sharpness for k in keys]
    mx = max(z) if z else 0.0
    e = [math.exp(v - mx) for v in z]
    s = sum(e) or 1.0
    p_req = [v / s for v in e]
    p_pol = [policy_view[k] for k in keys]
    ens = [(a + b) / 2 for a, b in zip(p_req, p_pol)]
    h = -sum(v * math.log2(v) for v in ens if v > 0) / max(1e-9, math.log2(max(2, len(ens))))
    agreement = 1.0 - _jsd(p_req, p_pol)
    conf = ens[keys.index(chosen)] if chosen in keys else 0.0
    confident = conf >= 0.5 and agreement >= 0.65 and h <= 0.85
    return GenreGate(
        chosen=chosen, confidence=round(conf, 4), agreement=round(agreement, 4), entropy=round(h, 4),
        status="CONFIDENT" if confident else "AMBIGUOUS",
        request_view={k: round(v, 4) for k, v in zip(keys, p_req)},
        policy_view={k: round(v, 4) for k, v in zip(keys, p_pol)},
    )


# ---------------------------------------------------------------------- #
# Reward
# ---------------------------------------------------------------------- #

def plan_reward(plan: TreePlan, valid_package: bool = True) -> dict[str, Any]:
    """Score a finished document from measurable properties only.

    R = 0.30 coverage + 0.20 structure + 0.20 budget fit + 0.15 uniqueness
        + 0.15 support - penalties, clipped to [-1, 1]; an invalid package is -1.
    """
    if not valid_package:
        return {"reward": -1.0, "valid_package": False}
    facts = plan.all_facts()
    text = " ".join(
        [n.title for root in plan.nodes for n in root.walk()]
        + [(f.get("text") or "") for f in facts]
    )
    qwords = content_words(extract_page_budget(plan.request)[1])
    coverage = _overlap(qwords, text) if qwords else 1.0
    structure = plan.structure.get("structural_accuracy", 1.0)
    budget = plan.budget_words or 1.0
    budget_fit = max(0.0, 1.0 - abs(plan.words_planned - budget) / budget)
    texts = [((f.get("text") or "") + (f.get("latex") or "")).strip() for f in facts]
    uniqueness = len(set(texts)) / max(1, len(texts))
    support = sum(float(f.get("support", 1.0)) for f in facts) / max(1, len(facts))
    pref = plan.genre.get("kind_preference", {})
    genre_fit = sum(float(pref.get(f["kind"], 0.5)) for f in facts) / max(1, len(facts))
    penalties = 0.0
    if not facts:
        penalties += 1.0
    if plan.n_topics < 2:
        penalties += 0.2
    reward = (0.30 * coverage + 0.20 * structure + 0.20 * budget_fit + 0.15 * uniqueness
              + 0.15 * support) * (0.6 + 0.4 * genre_fit) - penalties
    reward = max(-1.0, min(1.0, reward))
    return {
        "reward": round(reward, 4),
        "coverage": round(coverage, 4),
        "structural_accuracy": round(structure, 4),
        "budget_fit": round(budget_fit, 4),
        "uniqueness": round(uniqueness, 4),
        "support": round(support, 4),
        "genre_fit": round(genre_fit, 4),
        "valid_package": True,
    }
