"""Turn a planned knowledge tree into a DocumentIR, using database text only.

Every block in the result comes from a fact in the knowledge tree. The only
words this module adds are labels taken from the chosen genre file
(``kind_labels``, ``overview_title``, ``references_title``) and the numbers of
equations and tables. Headings are topic titles from the database.

Topic depth maps to heading level:

* one root topic:   the root's facts open the document under the genre's
                    ``overview_title``; its children are Heading 1, their
                    children Heading 2, then Heading 3.
* several roots:    each root is Heading 1, its children Heading 2, then 3.

Anything deeper than Heading 3 is folded into its Heading 3 parent so the
outline never skips or exceeds three levels.
"""

from __future__ import annotations

import datetime
from typing import Any

from src.doc_gen.document_ir import (
    CalloutBlock,
    DocumentIR,
    EquationBlock,
    InlineRun,
    ListBlock,
    ParagraphBlock,
    ReferenceItem,
    SectionIR,
    TableBlock,
)
from src.doc_gen.rlcd_tree import PlanNode, TreePlan

MAX_LEVEL = 3


class _Counter:
    def __init__(self) -> None:
        self.equation = 0
        self.table = 0


def _paragraph(text: str, label: str | None = None) -> ParagraphBlock:
    runs = []
    if label:
        runs.append(InlineRun(text=f"{label}. ", bold=True))
    runs.append(InlineRun(text=text))
    return ParagraphBlock(runs=runs)


def fact_blocks(fact: dict[str, Any], genre: dict[str, Any], counter: _Counter) -> list[Any]:
    """Blocks for one fact. The block type follows the fact's kind."""
    kind = fact["kind"]
    text = (fact.get("text") or "").strip()
    payload = fact.get("payload") or {}
    labels = genre.get("kind_labels", {})

    if kind == "formula":
        counter.equation += 1
        blocks: list[Any] = [EquationBlock(latex=fact["latex"], name=payload.get("name", ""),
                                           number=counter.equation)]
        if text:
            blocks.append(_paragraph(text))
        return blocks
    if kind == "algorithm_step":
        blocks = []
        if text:
            blocks.append(ParagraphBlock(runs=[InlineRun(text=text, bold=True)], style="Lead"))
        blocks.append(ListBlock(items=list(payload.get("steps", [])), ordered=True))
        return blocks
    if kind == "comparison":
        counter.table += 1
        caption = f"Table {counter.table}. {text}" if text else f"Table {counter.table}."
        return [TableBlock(headers=list(payload.get("header", [])),
                           rows=[list(r) for r in payload.get("rows", [])], caption=caption)]
    if kind in genre.get("callout_kinds", []):
        return [CalloutBlock(title=labels.get(kind, kind.replace("_", " ").capitalize()),
                             content=text, kind=kind)]
    if kind in labels:
        return [_paragraph(text, labels[kind])]
    return [_paragraph(text)]


def _section(node: PlanNode, level: int, genre: dict[str, Any], counter: _Counter) -> SectionIR:
    sec = SectionIR(id=node.slug, title=node.title, level=level)
    for f in node.facts:
        sec.blocks.extend(fact_blocks(f, genre, counter))
    for child in node.children:
        if level < MAX_LEVEL:
            sec.subsections.append(_section(child, level + 1, genre, counter))
        else:
            # Fold deeper topics into this section, keeping their order.
            folded = _section(child, level, genre, counter)
            for s in folded.walk():
                sec.blocks.extend(s.blocks)
    return sec


def _references(plan: TreePlan) -> list[ReferenceItem]:
    refs: dict[str, ReferenceItem] = {}
    for f in plan.all_facts():
        url = f.get("source_url")
        if not url or url in refs:
            continue
        license_text = f.get("license") or ""
        refs[url] = ReferenceItem(title=f.get("source_title") or url, url=url, snippet=license_text)
    return list(refs.values())


def build_document_ir(plan: TreePlan) -> DocumentIR:
    genre, theme = plan.genre, plan.theme
    counter = _Counter()
    sections: list[SectionIR] = []

    if len(plan.nodes) == 1:
        root = plan.nodes[0]
        title = root.title
        if root.facts:
            lead = SectionIR(id=f"{root.slug}#overview", title=genre.get("overview_title", root.title), level=1)
            for f in root.facts:
                lead.blocks.extend(fact_blocks(f, genre, counter))
            sections.append(lead)
        sections.extend(_section(c, 1, genre, counter) for c in root.children)
    else:
        titles = [n.title for n in plan.nodes]
        title = titles[0] if len(titles) == 1 else ", ".join(titles[:-1]) + " and " + titles[-1]
        sections.extend(_section(n, 1, genre, counter) for n in plan.nodes)

    references = _references(plan) if plan.gates.get("references", True) else []
    return DocumentIR(
        title=title,
        subtitle=genre.get("label", ""),
        topic=title,
        genre=genre.get("label", ""),
        author="",
        date_str=datetime.date.today().strftime("%B %Y"),
        sections=sections,
        signature_element="",
        include_toc=bool(plan.gates.get("toc", False)),
        include_page_numbers=True,
        header_text=title,
        footer_text="",
        references=references,
        margin_inches=float(theme.get("layout", {}).get("margin_side", 72)) / 72.0,
        theme=theme,
        cover_page=bool(plan.gates.get("cover", False)),
        references_title=genre.get("references_title", "References"),
    )


def ir_outline(doc: DocumentIR) -> list[tuple[int, str]]:
    """(level, title) for every heading, in reading order."""
    out: list[tuple[int, str]] = []
    for s in doc.sections:
        for x in s.walk():
            out.append((x.level, x.title))
    return out


def ir_text(doc: DocumentIR) -> list[str]:
    """Every piece of body text in the IR, for provenance checks."""
    texts: list[str] = []
    for s in doc.sections:
        for x in s.walk():
            for b in x.blocks:
                if isinstance(b, ParagraphBlock):
                    texts.append("".join(r.text for r in b.runs))
                elif isinstance(b, ListBlock):
                    texts.extend(b.items)
                elif isinstance(b, CalloutBlock):
                    texts.append(b.content)
                elif isinstance(b, EquationBlock):
                    texts.append(b.latex)
                elif isinstance(b, TableBlock):
                    texts.extend(" ".join(r) for r in [b.headers] + b.rows)
    return texts
