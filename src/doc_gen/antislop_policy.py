"""Anti-AI Slop Document Policy for Filevo.

Enforces deterministic editorial structure, authentic voice, and typography
derived from the Anti-Slop Docs specification so that generated documents
never read or look AI-generated.

Core Disciplines:
1. BLUF / Pyramid Structure: Thesis, recommendation, and implications go first.
2. Ban Windup Openers: No 'In today's fast-paced world...', 'This document aims to...'.
3. Ban Conclusion Summaries: The close delivers forward actions, not repackaged text.
4. Ban AI Clichés: 'Furthermore', 'Moreover', 'Additionally', 'It is important to note',
   'Delve', 'Leverage', 'Robust', 'Seamless', 'Elevate', 'Tapestry', 'Testament'.
5. Ban Bold-Bombing: Deliberate, sparse bold only; never half the page or every lead-in.
6. Prose by Default: Bullet lists only when strictly parallel or sequential steps (3-7 items).
7. Concrete Data: Grounded figures, protocols, hardware, and specific evidence.
8. Signature Element: Exactly one owned, sustained signature structural/visual device.
9. Real Editorial Typography: Thoughtful display/body pairings, generous leading, horizontal rules.
10. DOC.md Generation: Generates per-document source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BANNED_AI_CLICHES = [
    r"\bfurthermore\b",
    r"\bmoreover\b",
    r"\badditionally\b",
    r"\bit is important to note(?:\s+that)?\b",
    r"\bin today['’]?s\s+(?:fast-paced|rapidly\s+evolving|dynamic|modern)\s+world\b",
    r"\bdelve(?:\s+into)?\b",
    r"\bleverage\b",
    r"\bseamless(?:ly)?\b",
    r"\belevate\b",
    r"\brobust(?:ly)?\b",
    r"\btapestry\b",
    r"\btestament\b",
    r"\bgame-changer\b",
    r"\bparadigm\s+shift\b",
    r"\bholistic(?:ally)?\b",
    r"\bbeacon\b",
    r"\bunpack(?:ing)?\b",
]

BANNED_INTRO_PATTERNS = [
    r"^in\s+today['’]?s\s+world",
    r"^this\s+document\s+(?:aims|seeks|intends)\s+to",
    r"^this\s+report\s+(?:aims|seeks|intends)\s+to",
    r"^the\s+purpose\s+of\s+this\s+document\s+is\s+to",
    r"^in\s+this\s+(?:report|document|paper|study),?\s+we\s+(?:will\s+)?(?:explore|delve|examine)",
]

BANNED_CONCLUSION_PATTERNS = [
    r"^in\s+conclusion,?\s+(?:this\s+report|this\s+document|we\s+have)",
    r"^to\s+summarize,?\s+(?:the\s+above|what\s+we\s+have\s+seen)",
    r"^in\s+summary,?\s+",
    r"^all\s+in\s+all,?\s+",
]


@dataclass
class AntiSlopDials:
    """Quantitative sliders for document tone and layout."""

    formality: int = 6  # 1 (conversational) <-> 10 (institutional)
    density: int = 5    # 1 (airy one-pager) <-> 10 (dense technical report)
    ornament: int = 2   # 1 (sober editorial) <-> 10 (magazine device heavy)


@dataclass
class AntiSlopPolicy:
    """Document editorial and layout governance policy."""

    enabled: bool = True
    dials: AntiSlopDials = field(default_factory=AntiSlopDials)
    font_display: str = "Times New Roman"
    font_body: str = "Times New Roman"
    font_mono: str = "Cascadia Code"
    ban_cliches: bool = True
    prose_default: bool = True
    bluf_required: bool = True
    signature_element_required: bool = True

    def sanitize_prose(self, text: str, is_intro: bool = False, is_conclusion: bool = False) -> str:
        """Prunes AI connector cliches, windups, and summary phrases from text."""
        if not self.enabled or not text:
            return text

        lines = text.split("\n")
        cleaned_lines = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                cleaned_lines.append("")
                continue

            # Prune connector clichés
            if self.ban_cliches:
                # Replace 'Furthermore, X' -> 'X'
                line_str = re.sub(r"\b(?:Furthermore|Moreover|Additionally)[,\s]*", "", line_str, flags=re.IGNORECASE)
                # Replace 'It is important to note that X' -> 'X'
                line_str = re.sub(r"\b(?:It\s+is\s+important\s+to\s+note\s+that|It\s+should\s+be\s+noted\s+that)\s*", "", line_str, flags=re.IGNORECASE)
                # Strip 'In today's fast-paced world...'
                line_str = re.sub(r"\bin\s+today['’]?s\s+(?:fast-paced|rapidly\s+evolving|dynamic|modern)\s+world[,\s]*", "", line_str, flags=re.IGNORECASE)
                if line_str and line_str[0].islower():
                    line_str = line_str[0].upper() + line_str[1:]

                # Replace clichés with concrete equivalents
                line_str = re.sub(r"\bseamlessly\b", "directly", line_str, flags=re.IGNORECASE)
                line_str = re.sub(r"\bseamless\b", "integrated", line_str, flags=re.IGNORECASE)
                line_str = re.sub(r"\bleverage\b", "use", line_str, flags=re.IGNORECASE)
                line_str = re.sub(r"\bleveraging\b", "using", line_str, flags=re.IGNORECASE)
                line_str = re.sub(r"\bdelve into\b", "examine", line_str, flags=re.IGNORECASE)
                line_str = re.sub(r"\brobust\b", "reliable", line_str, flags=re.IGNORECASE)
                line_str = re.sub(r"\belevate\b", "improve", line_str, flags=re.IGNORECASE)

            # Strip intro windup phrases
            if is_intro:
                for pat in BANNED_INTRO_PATTERNS:
                    if re.match(pat, line_str, flags=re.IGNORECASE):
                        line_str = re.sub(pat + r"[,\s]*", "", line_str, flags=re.IGNORECASE).strip()
                        if line_str and line_str[0].islower():
                            line_str = line_str[0].upper() + line_str[1:]

            # Strip conclusion recap openers
            if is_conclusion:
                for pat in BANNED_CONCLUSION_PATTERNS:
                    if re.match(pat, line_str, flags=re.IGNORECASE):
                        line_str = re.sub(pat, "", line_str, flags=re.IGNORECASE).strip()
                        if line_str and line_str[0].islower():
                            line_str = line_str[0].upper() + line_str[1:]

            # Strip bold-bombing (e.g. **Word** everywhere -> Word)
            bold_count = len(re.findall(r"\*\*[^*]+\*\*", line_str))
            word_count = len(line_str.split())
            if word_count > 0 and (bold_count / word_count > 0.15 or bold_count > 4):
                # Excessive bolding detected; unbold except first key phrase
                matches = list(re.finditer(r"\*\*([^*]+)\*\*", line_str))
                if len(matches) > 1:
                    new_line = line_str[:matches[0].end()]
                    remainder = line_str[matches[0].end():]
                    remainder = re.sub(r"\*\*([^*]+)\*\*", r"\1", remainder)
                    line_str = new_line + remainder

            cleaned_lines.append(line_str)

        return "\n".join(cleaned_lines)

    def generate_doc_md(
        self,
        title: str,
        topic: str,
        genre: str,
        output_dir: Path,
        signature_element: str,
        sections: list[dict[str, Any]],
    ) -> Path:
        """Generates the mandatory per-document DOC.md source of truth file."""
        clean_slug = re.sub(r"[^\w\-]", "_", title)[:40]
        doc_md_path = output_dir / f"{clean_slug}_DOC.md"

        sec_lines = []
        for s in sections:
            s_name = s.get("title", s.get("heading", "Section"))
            sec_lines.append(f"- **{s_name}**: Focuses on authoritative domain depth.")

        content = f"""# Doc: {title} — Anti-Slop Specification

## 0. Dials
FORMALITY: {self.dials.formality} | DENSITY: {self.dials.density} | ORNAMENT: {self.dials.ornament}

## 1. Format and Engine
Deliverable: .docx and .pdf
Authoring Engine: WordCraft MCP Primary Composition Engine
Fallback Engine: Filevo Native OpenXML Zero C-Dependency Renderer

## 2. Structure (BLUF)
Thesis / Core Finding: Establishes rigorous architectural and operational principles for {topic}.
Executive findings and core parameters are stated in the opening paragraph without windups.

### Sections
{chr(10).join(sec_lines)}

## 3. Signature Element (Mandatory, Exactly One)
**{signature_element}** — An intentional, sustained device anchoring the document's professional identity.

## 4. Voice Directives
- FORMALITY {self.dials.formality}; prose by default; bullet lists reserved for parallel criteria.
- Complete ban on AI connector clichés ('Furthermore', 'Moreover', 'Seamless', 'Leverage', 'Robust').
- Zero bold-bombing; bold used only for key terms upon first definition.
- Concrete numbers, hardware specifications, and verifiable protocols.

## 5. Typography and Layout
Display Font: {self.font_display} (Headings, bold weight, keepNext: true)
Body Font: {self.font_body} (11pt, 1.2 line spacing, 60-75ch measure)
Mono Font: {self.font_mono} (Telemetry, registers, and code items)
Tables: Clean horizontal rules (border-t / border-b), zero box grids.
Margins: Generous 1.0 inch (72pt) margins with discreet header and page-numbered footer.

## 6. Anti-Patterns (BANNED)
- NO intro restating the prompt.
- NO 'In conclusion' repetitive summaries.
- NO chained one-line bullets acting as chopped paragraphs.
- NO emoji or clipart.
- NO default unstyled Calibri 11 single-column layout.
"""
        doc_md_path.parent.mkdir(parents=True, exist_ok=True)
        doc_md_path.write_text(content, encoding="utf-8")
        return doc_md_path


# Global singleton policy instance
_GLOBAL_POLICY: AntiSlopPolicy | None = None


def get_antislop_policy() -> AntiSlopPolicy:
    """Returns the globally configured AntiSlopPolicy."""
    global _GLOBAL_POLICY
    if _GLOBAL_POLICY is None:
        _GLOBAL_POLICY = AntiSlopPolicy()
    return _GLOBAL_POLICY
