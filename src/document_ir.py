"""
Document Intermediate Representation (DocumentIR) Module
Defines the canonical, structured, and format-independent representation of documents.
Serves as the single source of truth for both Microsoft Word (.docx) and IEEE LaTeX (.tex) renderers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CitationIR:
    """Scholarly citation with verifiable provenance."""

    key: str  # e.g., '1', 'dawson1973', 'arxiv:2301.12345'
    title: str
    authors: list[str]
    year: int | str
    source_url: str = ""
    doi: str = ""
    source_type: str = "peer_reviewed"  # 'peer_reviewed', 'arxiv', 'book', 'encyclopedia', 'web'
    abstract: str = ""

    def format_ieee_bibitem(self) -> str:
        """Format as standard IEEE bibliography item."""
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        if not authors_str:
            authors_str = "Anonymous"

        parts = [f"{authors_str}, \"{self.title},\""]
        if self.doi:
            parts.append(f"DOI: {self.doi},")
        if self.year:
            parts.append(f"{self.year}.")
        if self.source_url:
            parts.append(f"[Online]. Available: {self.source_url}")
        return " ".join(parts)


@dataclass
class ClaimIR:
    """Factual claim grounded in retrieved evidence."""

    statement: str
    evidence_text: str = ""
    citation_keys: list[str] = field(default_factory=list)


@dataclass
class FigureIR:
    """Structured figure with verified image path and source attribution."""

    image_path: str
    caption: str
    source_url: str = ""
    attribution: str = ""
    license: str = ""
    figure_num: int = 1


@dataclass
class TableIR:
    """Structured booktabs-compatible data table."""

    caption: str
    headers: list[str]
    rows: list[list[str]]
    table_num: int = 1


@dataclass
class EquationIR:
    """Authentic mathematical formulation with latex notation."""

    formula: str = ""
    explanation: str = ""
    num: int = 1
    formulas: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.formulas and not self.formula:
            self.formula = self.formulas[0]
        elif self.formula and not self.formulas:
            self.formulas = [self.formula]


@dataclass
class SectionIR:
    """Logical section of the document."""

    heading: str
    level: int = 1
    paragraphs: list[str] = field(default_factory=list)
    claims: list[ClaimIR] = field(default_factory=list)
    figures: list[FigureIR] = field(default_factory=list)
    tables: list[TableIR] = field(default_factory=list)
    equations: list[EquationIR] = field(default_factory=list)
    subsections: list[SectionIR] = field(default_factory=list)
    page_break: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to legacy section dictionary format for backward compatibility."""
        sec_dict: dict[str, Any] = {
            "heading": self.heading,
            "level": self.level,
            "paragraphs": list(self.paragraphs),
            "page_break": self.page_break,
        }
        if self.equations:
            sec_dict["equations"] = [
                {
                    "num": eq.num,
                    "explanation": eq.explanation,
                    "formulas": [eq.formula],
                }
                for eq in self.equations
            ]
        if self.tables:
            t = self.tables[0]
            sec_dict["table"] = {
                "caption": t.caption,
                "headers": list(t.headers),
                "rows": [list(r) for r in t.rows],
            }
        if self.figures:
            sec_dict["images"] = [
                {
                    "path": f.image_path,
                    "caption": f.caption,
                    "source_url": f.source_url,
                    "license": f.license,
                }
                for f in self.figures
                if Path(f.image_path).is_file()
            ]
        return sec_dict


@dataclass
class DocumentIR:
    """Structured Intermediate Representation of an entire document."""

    title: str
    subtitle: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    doc_type: str = "literature_review"  # 'literature_review', 'technical_report', 'original_research', 'monograph'
    sections: list[SectionIR] = field(default_factory=list)
    bibliography: list[CitationIR] = field(default_factory=list)
    author_metadata: dict[str, str] = field(
        default_factory=lambda: {
            "author": "[Author Name]",
            "affiliation": "[Author Institution / Department]",
            "location": "[City, Country]",
            "email": "[author@domain.edu]",
        }
    )
    page_count: int = 10
    is_research: bool = True
    format: str = "both"  # 'docx', 'ieee_latex', 'both'

    def validate(self) -> list[str]:
        """Validate structural integrity and citation traceability."""
        issues: list[str] = []
        if not self.title.strip():
            issues.append("Document title is empty.")
        if not self.sections:
            issues.append("Document has no sections.")

        all_keys = {c.key for c in self.bibliography}
        for sec in self.sections:
            for claim in sec.claims:
                for k in claim.citation_keys:
                    if k not in all_keys:
                        issues.append(f"Section '{sec.heading}' cites unknown key '{k}'.")
            for fig in sec.figures:
                if not Path(fig.image_path).is_file():
                    issues.append(f"Figure file does not exist: {fig.image_path}")

        return issues

    def to_legacy_dict(self) -> dict[str, Any]:
        """Export as dictionary directly consumed by docx_creator and ieee_latex_creator."""
        out_sections = [s.to_dict() for s in self.sections]

        # Add bibliography section if not already present
        if not any("reference" in s.heading.lower() or "bibliography" in s.heading.lower() for s in self.sections):
            ref_bullets = [
                f"[{idx}] {cit.format_ieee_bibitem()}"
                for idx, cit in enumerate(self.bibliography, 1)
            ]
            if ref_bullets:
                out_sections.append({
                    "heading": "References & Scholarly Bibliography",
                    "level": 1,
                    "page_break": True,
                    "paragraphs": ["The following verified sources and literature ground this document:"],
                    "bullets": ref_bullets,
                })

        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "abstract": self.abstract,
            "keywords": list(self.keywords),
            "sections": out_sections,
            "page_count": self.page_count,
            "is_research": self.is_research,
            "format": "ieee" if self.is_research else "standard",
            "author": self.author_metadata.get("author", "Sortwise"),
            "affiliation": self.author_metadata.get("affiliation", ""),
            "location": self.author_metadata.get("location", ""),
            "email": self.author_metadata.get("email", ""),
            "cover_page": None if self.is_research else {"title": self.title},
            "table_of_contents": None if self.is_research else out_sections,
            "declaration": None,
            "certificate": None,
            "lists_of_figures_and_symbols": False,
        }
