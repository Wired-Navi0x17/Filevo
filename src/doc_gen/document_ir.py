"""Document Intermediate Representation (IR) for Filevo.

Defines a language-independent, typed, structural AST representing a publication-grade
document before it is lowered into WordCraft MCP commands or native OpenXML packages.

Includes:
- Document metadata: title, subtitle, authors, date, genre, anti-slop dials, signature element
- Page layout: margins, headers, footers, page numbers
- Structural hierarchy: sections (h1, h2, h3), appendices, references
- Content blocks:
  - ParagraphBlock (with inline formatting)
  - ListBlock (ordered / bulleted)
  - TableBlock (tabular data with headers and cell alignment)
  - CalloutBlock (signature elements, key-figures panels)
  - ImageBlock / DiagramBlock (visual figures with captions)
  - PageBreakBlock
  - FootnoteBlock
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from src.doc_gen.antislop_policy import AntiSlopPolicy, get_antislop_policy
from src.doc_gen.document_brief import DocumentBrief, PlannedSection


@dataclass
class InlineRun:
    """A segment of text with specific inline formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    underline: bool = False
    link: str | None = None


@dataclass
class ParagraphBlock:
    """A block of text containing one or more formatted runs."""

    runs: list[InlineRun] = field(default_factory=list)
    style: str = "Normal"  # "Normal", "Title", "Subtitle", "Quote", "Callout"
    alignment: Literal["left", "center", "right", "justify"] = "left"
    space_before_pt: float = 0.0
    space_after_pt: float = 6.0
    is_bluf: bool = False

    @classmethod
    def from_text(cls, text: str, style: str = "Normal", bold: bool = False, italic: bool = False) -> ParagraphBlock:
        return cls(runs=[InlineRun(text=text, bold=bold, italic=italic)], style=style)


@dataclass
class ListBlock:
    """An ordered or unordered list of items."""

    items: list[str] = field(default_factory=list)
    ordered: bool = False
    space_after_pt: float = 6.0


@dataclass
class TableBlock:
    """A structured data table with headers and data rows."""

    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    caption: str | None = None
    column_widths: list[float] | None = None
    horizontal_rules_only: bool = True  # Anti-slop table styling


def parse_markdown_table(text: str) -> TableBlock | None:
    """Parse and validate a markdown table string into a TableBlock.

    Requires:
    - At least one header row and at least one data row (matrix >= 2 rows).
    - Header must contain >= 2 non-empty columns.
    - Data rows must align in column count with the header.
    Returns None if malformed, invalid, or insufficient rows, falling back to prose.
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return None

    # All lines must appear tabular with '|'
    if not all(l.startswith("|") and l.endswith("|") for l in lines):
        return None

    matrix: list[list[str]] = []
    for line in lines:
        inner = line.strip("|").strip()
        # Skip markdown separator row |---|---|
        if inner and all(c in "-:| \t" for c in inner):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        matrix.append(cols)

    if len(matrix) < 2:
        return None

    header = matrix[0]
    if len(header) < 2 or not any(header):
        return None

    n_cols = len(header)
    rows: list[list[str]] = []
    for r in matrix[1:]:
        if len(r) != n_cols:
            return None
        rows.append(r)

    if not rows:
        return None

    return TableBlock(headers=header, rows=rows)


@dataclass
class CalloutBlock:
    """An executive signature element or key figures panel."""

    title: str
    content: str
    kind: str = "signature"  # "signature", "key_figures", "warning", "note"


@dataclass
class ImageBlock:
    """A raster or vector figure with assertive caption."""

    path: str
    caption: str = ""
    source: str = ""
    width_inches: float = 6.0


@dataclass
class EquationBlock:
    """A display equation written in LaTeX, with an optional name and number."""

    latex: str
    name: str = ""
    number: int | None = None


@dataclass
class PageBreakBlock:
    """Explicit page break."""
    pass


@dataclass
class FootnoteBlock:
    """A document footnote."""

    id: int
    text: str


@dataclass
class SectionIR:
    """A top-level or nested section within the document."""

    id: str
    title: str
    level: int = 1  # 1 = Heading 1, 2 = Heading 2, 3 = Heading 3
    purpose: str = ""
    blocks: list[Any] = field(default_factory=list)
    page_break_before: bool = False
    subsections: list["SectionIR"] = field(default_factory=list)

    def walk(self):
        yield self
        for s in self.subsections:
            yield from s.walk()


@dataclass
class ReferenceItem:
    """A cited literature or discovered web reference."""

    title: str
    url: str
    snippet: str = ""


@dataclass
class AppendixIR:
    """An appendix at the end of the document."""

    title: str
    content: str


@dataclass
class DocumentIR:
    """Complete, self-contained typed Intermediate Representation of a document."""

    title: str
    subtitle: str
    topic: str
    genre: str
    author: str = "Filevo Autonomous Document Intelligence"
    date_str: str = field(default_factory=lambda: datetime.datetime.now().strftime("%B %d, %Y"))
    sections: list[SectionIR] = field(default_factory=list)
    signature_element: str = "Executive Architectural Invariants Panel"
    include_toc: bool = True
    include_page_numbers: bool = True
    header_text: str = ""
    footer_text: str = "Filevo Autonomous Document Intelligence"
    references: list[ReferenceItem] = field(default_factory=list)
    appendices: list[AppendixIR] = field(default_factory=list)
    margin_inches: float = 1.0
    # Set by the knowledge-tree pipeline: a theme dict (data/themes/*.toml),
    # whether to print a cover page, and the references heading text.
    theme: dict[str, Any] | None = None
    cover_page: bool = False
    references_title: str = "References"

    @classmethod
    def from_brief_and_content(
        cls,
        brief: DocumentBrief,
        sections_data: list[dict[str, Any]],
        antislop: AntiSlopPolicy | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> DocumentIR:
        """Constructs a fully typed DocumentIR from DocumentBrief and generated section contents."""
        policy = antislop or get_antislop_policy()
        title = brief.title
        topic = brief.topic
        genre = brief.genre

        # The signature element is one sustained structural device. Its content is
        # derived from the document's own evidence rather than a hardcoded domain
        # blurb: the previous version injected marine-taxonomy boilerplate into any
        # topic whose name contained "plant" or "nature".
        sig_elem = "Scope and Evidence Base"
        if genre == "Formal Letter":
            sig_elem = "Administrative Authorization Block"

        doc = cls(
            title=title,
            subtitle=f"{genre} — {brief.audience}",
            topic=topic,
            genre=genre,
            header_text=f"{title[:45]} | {genre}",
            footer_text=f"{brief.author if hasattr(brief, 'author') else 'Filevo'} • {genre}",
            signature_element=sig_elem,
            include_toc=(len(sections_data) >= 4 and genre != "Formal Letter" and len(sections_data) < 25) or (len(sections_data) >= 25 and any(w in getattr(brief, "original_request", "").lower() for w in ("toc", "table of contents"))),
        )

        # Build SectionIR hierarchy
        for idx, sec in enumerate(sections_data):
            sec_title = sec.get("title", f"Section {idx + 1}")
            sec_raw_content = sec.get("content", "")

            # Apply Anti-Slop sanitization
            is_intro = idx == 0
            is_conclusion = idx == len(sections_data) - 1
            cleaned_content = policy.sanitize_prose(
                sec_raw_content,
                is_intro=is_intro,
                is_conclusion=is_conclusion,
            )

            page_break = bool(
                sec.get("page_break", False)
                or sec.get("page_break_before", False)
                or (sec_title.lower().startswith("chapter "))
            )
            sec_ir = SectionIR(
                id=f"sec_{idx + 1}",
                title=sec_title,
                level=1,
                page_break_before=page_break,
            )

            # Insert the signature element right after the executive section.
            if idx == 0 and genre != "Formal Letter" and policy.signature_element_required:
                sig_lines = [f"Scope: {topic}"]
                prov = provenance or {}
                if prov.get("sources"):
                    sig_lines.append(
                        f"Evidence base: {prov['sources']} local source(s) "
                        f"retrieved {prov.get('retrieved', 'n/a')}"
                    )
                    if prov.get("coverage") is not None:
                        sig_lines.append(
                            f"Grounding coverage: {prov['coverage']:.0%} of sentences traced to sources"
                        )
                else:
                    sig_lines.append(
                        "Evidence base: generated from the document plan; no local sources ingested."
                    )
                sig_lines.append(f"Structure: {len(sections_data)} sections, {genre}")

                sig_body = "\n".join(sig_lines)
                sec_ir.blocks.append(
                    CalloutBlock(
                        title=sig_elem,
                        content=sig_body,
                        kind="signature",
                    )
                )

            # Parse paragraphs and procedural lists
            paragraphs = cleaned_content.split("\n\n")
            for p_idx, p in enumerate(paragraphs):
                p_str = p.strip()
                if not p_str:
                    continue

                # Check if paragraph is formatted as numbered operational steps
                step_matches = re.findall(r"^\d+\.\s+(.*)$", p_str, flags=re.MULTILINE)
                if len(step_matches) >= 2:
                    sec_ir.blocks.append(ListBlock(items=step_matches, ordered=True))
                    continue

                # Check if bullet list
                bullet_matches = re.findall(r"^[•\-*]\s+(.*)$", p_str, flags=re.MULTILINE)
                if len(bullet_matches) >= 2:
                    sec_ir.blocks.append(ListBlock(items=bullet_matches, ordered=False))
                    continue

                # Check if markdown table (| col1 | col2 |)
                tbl_block = parse_markdown_table(p_str)
                if tbl_block is not None:
                    sec_ir.blocks.append(tbl_block)
                    continue

                # Ordinary prose paragraph (Anti-slop default)
                # First paragraph of intro is marked as BLUF
                is_bluf = (is_intro and p_idx == 0)
                sec_ir.blocks.append(
                    ParagraphBlock.from_text(p_str, style="Normal")
                )

            # Check explicit sec['table']
            if sec.get("table") and isinstance(sec["table"], list) and len(sec["table"]) >= 2:
                sec_ir.blocks.append(TableBlock(headers=sec["table"][0], rows=sec["table"][1:]))

            # Check if section has an attached image
            sec_img = sec.get("image")
            if sec_img is not None:
                img_path = getattr(sec_img, "path", None) or (sec_img.get("path") if isinstance(sec_img, dict) else str(sec_img))
                img_caption = getattr(sec_img, "caption", "") or (sec_img.get("caption", "") if isinstance(sec_img, dict) else "")
                img_src = getattr(sec_img, "source_url", "") or (sec_img.get("source_url", "") if isinstance(sec_img, dict) else "")
                if img_path:
                    sec_ir.blocks.append(ImageBlock(path=str(img_path), caption=img_caption, source=img_src))

            # Check if brief planned a table for this section
            for ps in brief.sections:
                if ps.heading.lower() == sec_title.lower() and ps.visual_element:
                    table_block = cls._create_domain_table(ps.visual_element, topic)
                    if table_block:
                        sec_ir.blocks.append(table_block)
                    break

            doc.sections.append(sec_ir)

        # Append references if available
        if brief.sources_and_evidence:
            for ev in brief.sources_and_evidence:
                doc.references.append(
                    ReferenceItem(
                        title=ev.get("title", "Discovered Source"),
                        url=ev.get("url", ""),
                        snippet=ev.get("snippet", ""),
                    )
                )

        return doc

    @staticmethod
    def _create_domain_table(visual_type: str, topic: str) -> TableBlock | None:
        """Constructs an anti-slop tabular block only when genuine tabular data is available."""
        # Never emit placeholder tables filled with invented or domain-mismatched rows.
        # Tables are rendered only when explicit tabular data is provided in section content.
        return None
