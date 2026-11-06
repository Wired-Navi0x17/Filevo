"""Load curated knowledge files (``data/knowledge/<domain>/*.md``) into the tree.

File format (plain Markdown, standard library parser):

    ---
    domain: aiml
    root: Artificial intelligence and machine learning
    source: seed://aiml
    license: CC BY 4.0 (Filevo curated seed)
    ---

    # Reinforcement learning                <- level-1 topic under the root
    summary: One sentence that says what this topic is.
    prereq: Foundations > Probability        <- path below the root, may repeat

    ## Markov decision processes             <- child topic
    ```definition
    A Markov decision process is ...
    ```
    ```formula
    name: Bellman expectation equation
    latex: V^\\pi(s) = \\sum_a \\pi(a \\mid s) \\, ...
    text: The value of a state is ...
    ```
    ```steps
    title: Value iteration
    1. Initialise V(s) = 0 for every state.
    2. ...
    ```
    ```compare
    caption: On-policy versus off-policy TD control
    Method, Target, Policy learned
    SARSA, r + γQ(s', a'), behaviour policy
    ```

Fence kinds: definition, intuition, formula, steps, example, compare, pitfall,
application, history. Plain paragraphs directly under a heading (other than
``summary:``/``prereq:`` lines) become ``intuition`` facts.

Loading is idempotent: facts are keyed by a SHA-256 of their content, so
re-running ``report seed`` only adds what is new.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FENCE_KIND = {
    "definition": "definition",
    "intuition": "intuition",
    "formula": "formula",
    "steps": "algorithm_step",
    "example": "example",
    "compare": "comparison",
    "pitfall": "pitfall",
    "application": "application",
    "history": "history",
}

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_OPEN = re.compile(r"^```\s*([a-z]+)\s*$")
_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*)$")


def data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "knowledge"


@dataclass
class SeedFact:
    kind: str
    text: str = ""
    latex: str = ""
    payload: dict[str, Any] | None = None


@dataclass
class SeedTopic:
    path: list[str]
    summary: str = ""
    prereqs: list[list[str]] = field(default_factory=list)
    facts: list[SeedFact] = field(default_factory=list)


@dataclass
class SeedFile:
    meta: dict[str, str]
    topics: list[SeedTopic]


def _parse_fields(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """Split ``key: value`` lines from free lines. A field may continue on
    following indented lines."""
    fields: dict[str, str] = {}
    rest: list[str] = []
    key: str | None = None
    for line in lines:
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m and m.group(1) in ("name", "latex", "text", "title", "caption", "where"):
            key = m.group(1)
            fields[key] = m.group(2).strip()
        elif key and line.startswith((" ", "\t")) and line.strip():
            fields[key] += " " + line.strip()
        else:
            key = None
            rest.append(line)
    return fields, rest


def _fence_to_fact(kind_word: str, body: list[str], where: str) -> SeedFact:
    kind = FENCE_KIND.get(kind_word)
    if kind is None:
        raise ValueError(f"{where}: unknown fence kind '{kind_word}'")
    if kind == "formula":
        fields, rest = _parse_fields(body)
        if not fields.get("latex"):
            raise ValueError(f"{where}: formula block needs a 'latex:' line")
        text = fields.get("text", " ".join(l.strip() for l in rest if l.strip()))
        payload = {k: v for k, v in fields.items() if k in ("name", "where")}
        return SeedFact(kind, text=text, latex=fields["latex"], payload=payload or None)
    if kind == "algorithm_step":
        fields, rest = _parse_fields(body)
        steps = []
        for line in rest:
            m = _STEP.match(line)
            if m:
                steps.append(m.group(1).strip())
            elif line.strip() and steps:
                steps[-1] += " " + line.strip()
        if not steps:
            raise ValueError(f"{where}: steps block has no numbered lines")
        return SeedFact(kind, text=fields.get("title", ""), payload={"steps": steps})
    if kind == "comparison":
        fields, rest = _parse_fields(body)
        rows = [[c.strip() for c in l.split(",")] for l in rest if l.strip()]
        if len(rows) < 2:
            raise ValueError(f"{where}: compare block needs a header and at least one row")
        width = len(rows[0])
        if any(len(r) != width for r in rows):
            raise ValueError(f"{where}: compare rows must all have {width} cells")
        return SeedFact(
            kind,
            text=fields.get("caption", ""),
            payload={"header": rows[0], "rows": rows[1:]},
        )
    text = " ".join(l.strip() for l in body if l.strip())
    return SeedFact(kind, text=text)


def parse_seed_file(path: Path) -> SeedFile:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta: dict[str, str] = {}
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            if ":" in lines[i]:
                k, v = lines[i].split(":", 1)
                meta[k.strip()] = v.strip()
            i += 1
        i += 1
    if "root" not in meta:
        raise ValueError(f"{path.name}: front matter needs 'root:'")

    topics: list[SeedTopic] = []
    stack: list[str] = []
    current: SeedTopic | None = None
    para: list[str] = []

    def flush_para() -> None:
        if current is not None and para:
            text = " ".join(p.strip() for p in para).strip()
            if text:
                current.facts.append(SeedFact("intuition", text=text))
        para.clear()

    while i < len(lines):
        line = lines[i]
        where = f"{path.name}:{i + 1}"
        h = _HEADING.match(line)
        f = _FENCE_OPEN.match(line.strip())
        if h:
            flush_para()
            level = len(h.group(1))
            if level > len(stack) + 1:
                raise ValueError(f"{where}: heading jumps from level {len(stack)} to {level}")
            stack = stack[: level - 1] + [h.group(2).strip()]
            current = SeedTopic(path=list(stack))
            topics.append(current)
        elif f:
            flush_para()
            if current is None:
                raise ValueError(f"{where}: fence before any heading")
            body: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                body.append(lines[i])
                i += 1
            if i >= len(lines):
                raise ValueError(f"{where}: unclosed fence")
            current.facts.append(_fence_to_fact(f.group(1), body, where))
        elif current is not None and line.startswith("summary:"):
            current.summary = line.split(":", 1)[1].strip()
        elif current is not None and line.startswith("prereq:"):
            current.prereqs.append([p.strip() for p in line.split(":", 1)[1].split(">")])
        elif not line.strip():
            flush_para()
        elif current is not None:
            para.append(line)
        i += 1
    flush_para()
    return SeedFile(meta=meta, topics=topics)


def load_seed(tree, domain: str = "aiml", root: Path | None = None) -> dict[str, int]:
    """Load every ``*.md`` file of ``domain`` into ``tree`` (a KnowledgeTree)."""
    from src.doc_gen.knowledge_tree import path_slug

    folder = (root or data_root()) / domain
    files = sorted(folder.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"no seed files in {folder}")

    added_topics = added_facts = 0
    pending_prereqs: list[tuple[int, list[str]]] = []
    before = tree.stats()["topics"]

    for order, path in enumerate(files):
        seed = parse_seed_file(path)
        root_title = seed.meta["root"]
        source_id = tree.ensure_source(
            f"{seed.meta.get('source', 'seed://' + domain)}/{path.stem}",
            f"{root_title}: {path.stem.split('_', 1)[-1].replace('_', ' ')}",
            seed.meta.get("license", "Filevo curated seed"),
        )
        tree.upsert_topic([root_title], summary=seed.meta.get("root_summary", ""), domain=domain)
        for t_ord, topic in enumerate(seed.topics):
            full = [root_title] + topic.path
            ord_value = order * 1000 + t_ord if len(topic.path) == 1 else t_ord
            topic_id = tree.upsert_topic(full, summary=topic.summary, ord=ord_value, domain=domain)
            for prereq in topic.prereqs:
                pending_prereqs.append((topic_id, [root_title] + prereq))
            for f_ord, fact in enumerate(topic.facts):
                if tree.add_fact(
                    topic_id, fact.kind, text=fact.text, latex=fact.latex, payload=fact.payload,
                    source_id=source_id, support=1.0, created_by="seed", ord=f_ord,
                ):
                    added_facts += 1
    unresolved = []
    for topic_id, prereq_path in pending_prereqs:
        if not tree.add_prereq(topic_id, path_slug(prereq_path)):
            unresolved.append(" > ".join(prereq_path))
    tree.commit()
    added_topics = tree.stats()["topics"] - before
    if unresolved:
        raise ValueError("unresolved prerequisites: " + "; ".join(sorted(set(unresolved))))
    embedded = tree.embed_missing()
    return {
        "files": len(files),
        "topics_added": added_topics,
        "facts_added": added_facts,
        "vectors": embedded,
    }
