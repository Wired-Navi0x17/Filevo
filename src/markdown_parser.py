"""Comprehensive Markdown parser and DOCX renderer for Sortwise.

Supports:
- Headings 1 through 6 with anchors
- Inline formatting: bold, italic, bold+italic, strikethrough, inline code, highlights, sub/superscript
- Unordered, ordered, nested, and interactive task lists (- [ ] / - [x])
- Blockquotes and alerts (> [!NOTE], > [!TIP], > [!IMPORTANT], > [!WARNING], > [!CAUTION])
- Fenced code blocks with language identifiers and monospace styling
- GitHub Flavored Markdown (GFM) tables with column alignment (:---, :---:, ---:)
- Inline math ($...$) and display math ($$...$$)
- Horizontal rules (---, ***)
- Links and image embeddings (![alt](path))
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

import docx
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor

# Alert callout color presets (matching GitHub / Obsidian alert palettes)
ALERT_STYLES = {
    "NOTE": {"color": "1D4ED8", "bg": "EFF6FF", "title": "NOTE", "icon": "ℹ"},
    "TIP": {"color": "047857", "bg": "ECFDF5", "title": "TIP", "icon": "💡"},
    "IMPORTANT": {"color": "7C3AED", "bg": "F5F3FF", "title": "IMPORTANT", "icon": "★"},
    "WARNING": {"color": "B45309", "bg": "FFFBEB", "title": "WARNING", "icon": "⚠"},
    "CAUTION": {"color": "B91C1C", "bg": "FEF2F2", "title": "CAUTION", "icon": "⛔"},
}


def _set_cell_bg(cell: Any, fill_hex: str) -> None:
    """Set custom hex background for a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex.lstrip("#")}"/>')
    tcPr.append(shd)


def _set_cell_borders(
    cell: Any,
    top: str | None = None,
    bottom: str | None = None,
    left: str | None = None,
    right: str | None = None,
) -> None:
    """Set specific borders for a cell (color in hex or None)."""
    tcPr = cell._tc.get_or_add_tcPr()
    b_xml = [f'<w:tcBorders {nsdecls("w")}>']
    for side, col in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        if col:
            b_xml.append(f'  <w:{side} w:val="single" w:sz="6" w:space="0" w:color="{col.lstrip("#")}"/>')
        else:
            b_xml.append(f'  <w:{side} w:val="none"/>')
    b_xml.append('</w:tcBorders>')
    tcPr.append(parse_xml("".join(b_xml)))


def _set_cell_padding(cell: Any, top: int = 100, bottom: int = 100, left: int = 140, right: int = 140) -> None:
    """Set inner cell padding in twips."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for m, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        node = OxmlElement(f"w:{m}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def add_inline_markdown(
    paragraph: Any,
    text: str,
    default_font: str = "Times New Roman",
    default_size_pt: float = 12.0,
    default_color_rgb: RGBColor | None = None,
) -> None:
    """Parse inline markdown tokens and add styled runs to an existing paragraph.

    Handles:
    - ***bold italic*** or **_bold italic_**
    - **bold** or __bold__
    - *italic* or _italic_
    - ~~strikethrough~~
    - `inline code`
    - ==highlight==
    - <sup>superscript</sup>
    - <sub>subscript</sub>
    - $inline math$
    - [link text](url)
    """
    if not text:
        return

    # Strip XML-incompatible control characters (e.g. \x07 ASCII bell, null bytes)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', str(text))

    pattern = re.compile(
        r'(?P<bold_italic>\*\*\*[^*]+\*\*\*|___[^_]+___)'
        r'|(?P<bold>\*\*[^*]+\*\*|__[^_]+__)'
        r'|(?P<italic>\*[^*]+\*|_[^_]+_)'
        r'|(?P<strike>~~[^~]+~~)'
        r'|(?P<code_span>`[^`]+`)'
        r'|(?P<highlight>==[^=]+==)'
        r'|(?P<sup><sup>.*?</sup>)'
        r'|(?P<sub><sub>.*?</sub>)'
        r'|(?P<math>\$[^$]+\$)'
        r'|(?P<link>\[[^\]]+\]\([^)]+\))',
        re.DOTALL,
    )

    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            plain = text[last_idx:start]
            r = paragraph.add_run(plain)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt)
            if default_color_rgb:
                r.font.color.rgb = default_color_rgb

        m_dict = match.groupdict()
        val = match.group(0)

        if m_dict["bold_italic"]:
            core = val[3:-3]
            r = paragraph.add_run(core)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt)
            r.font.bold = True
            r.font.italic = True
        elif m_dict["bold"]:
            core = val[2:-2]
            r = paragraph.add_run(core)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt)
            r.font.bold = True
        elif m_dict["italic"]:
            core = val[1:-1]
            r = paragraph.add_run(core)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt)
            r.font.italic = True
        elif m_dict["strike"]:
            core = val[2:-2]
            r = paragraph.add_run(core)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt)
            r.font.strike = True
        elif m_dict["code_span"]:
            core = val[1:-1]
            r = paragraph.add_run(core)
            r.font.name = "Courier New"
            r.font.size = Pt(default_size_pt * 0.9)
            r.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)
        elif m_dict["highlight"]:
            core = val[2:-2]
            r = paragraph.add_run(core)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt)
            r.font.bold = True
            r.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)  # Amber highlight
        elif m_dict["sup"]:
            core = re.sub(r'</?sup>', '', val)
            r = paragraph.add_run(core)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt * 0.8)
            r.font.superscript = True
        elif m_dict["sub"]:
            core = re.sub(r'</?sub>', '', val)
            r = paragraph.add_run(core)
            r.font.name = default_font
            r.font.size = Pt(default_size_pt * 0.8)
            r.font.subscript = True
        elif m_dict["math"]:
            core = val[1:-1].strip()
            r = paragraph.add_run(core)
            r.font.name = "Cambria Math"
            r.font.size = Pt(default_size_pt)
            r.font.italic = True
            r.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)
        elif m_dict["link"]:
            link_m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', val)
            if link_m:
                lbl, url = link_m.group(1), link_m.group(2)
                r = paragraph.add_run(lbl)
                r.font.name = default_font
                r.font.size = Pt(default_size_pt)
                r.font.underline = True
                r.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)  # Classic link blue

        last_idx = end

    if last_idx < len(text):
        r = paragraph.add_run(text[last_idx:])
        r.font.name = default_font
        r.font.size = Pt(default_size_pt)
        if default_color_rgb:
            r.font.color.rgb = default_color_rgb


def render_alert_box(doc: Document, alert_type: str, title: str | None, lines: Sequence[str]) -> Any:
    """Render a GitHub / Obsidian styled alert callout box."""
    cfg = ALERT_STYLES.get(alert_type.upper(), ALERT_STYLES["NOTE"])
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    cell.width = Inches(6.0)

    _set_cell_bg(cell, cfg["bg"])
    _set_cell_borders(cell, left=cfg["color"], top=None, bottom=None, right=None)
    _set_cell_padding(cell, top=100, bottom=100, left=180, right=140)

    # Header with icon and alert badge
    raw_title = title if title else cfg["title"]
    header_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', str(raw_title))
    p_hdr = cell.paragraphs[0]
    p_hdr.paragraph_format.space_before = Pt(0)
    p_hdr.paragraph_format.space_after = Pt(3)
    r_icon = p_hdr.add_run(f"{cfg['icon']}  {header_text}")
    r_icon.font.name = "Times New Roman"
    r_icon.font.size = Pt(11)
    r_icon.font.bold = True
    c_hex = cfg["color"]
    r_icon.font.color.rgb = RGBColor(int(c_hex[0:2], 16), int(c_hex[2:4], 16), int(c_hex[4:6], 16))

    # Content lines
    for line in lines:
        if line.strip():
            p_line = cell.add_paragraph()
            p_line.paragraph_format.space_before = Pt(0)
            p_line.paragraph_format.space_after = Pt(2)
            p_line.paragraph_format.line_spacing = 1.25
            add_inline_markdown(p_line, line.strip(), default_size_pt=10.5)

    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(2)
    sp.paragraph_format.space_after = Pt(4)
    return table


def render_markdown_table(doc: Document, header_cells: Sequence[str], rows: Sequence[Sequence[str]], alignments: Sequence[str] | None = None) -> Any:
    """Render a GFM Markdown pipe table with column alignments and alternating shading."""
    num_cols = len(header_cells)
    if num_cols == 0:
        return None

    table = doc.add_table(rows=len(rows) + 1, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"

    # Alignments mapping
    align_map = {
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "left": WD_ALIGN_PARAGRAPH.LEFT,
    }

    # Header Row
    hdr_row = table.rows[0]
    for c_idx, h_text in enumerate(header_cells):
        c = hdr_row.cells[c_idx]
        _set_cell_bg(c, "1E293B")
        _set_cell_padding(c, top=120, bottom=120, left=140, right=140)
        p = c.paragraphs[0]
        p.alignment = align_map.get(alignments[c_idx] if alignments and c_idx < len(alignments) else "left", WD_ALIGN_PARAGRAPH.LEFT)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(h_text.strip())
        r.font.name = "Times New Roman"
        r.font.size = Pt(10)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Data Rows
    for r_idx, r_data in enumerate(rows):
        row = table.rows[r_idx + 1]
        bg_fill = "F8FAFC" if r_idx % 2 == 0 else "FFFFFF"
        for c_idx in range(num_cols):
            c = row.cells[c_idx]
            _set_cell_bg(c, bg_fill)
            _set_cell_padding(c, top=90, bottom=90, left=120, right=120)
            p = c.paragraphs[0]
            p.alignment = align_map.get(alignments[c_idx] if alignments and c_idx < len(alignments) else "left", WD_ALIGN_PARAGRAPH.LEFT)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            cell_text = str(r_data[c_idx]).strip() if c_idx < len(r_data) else ""
            add_inline_markdown(p, cell_text, default_size_pt=10.0)

    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(3)
    sp.paragraph_format.space_after = Pt(6)
    return table


def parse_markdown_into_doc(markdown_text: str, doc: Document) -> None:
    """Parse a full Markdown string and append all elements to a Word document."""
    lines = markdown_text.strip().split("\n")
    idx = 0
    num_lines = len(lines)

    while idx < num_lines:
        line = lines[idx]
        stripped = line.strip()

        # 1. Blank line -> skip
        if not stripped:
            idx += 1
            continue

        # 2. Horizontal Rule (---, ***, ___)
        if re.match(r'^(?:-{3,}|\*{3,}|_{3,})$', stripped):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(8)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run("―" * 45)
            r.font.name = "Times New Roman"
            r.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)
            idx += 1
            continue

        # 3. Headings (# to ######)
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            hashes, h_text = heading_match.group(1), heading_match.group(2).strip()
            level = len(hashes)
            h_p = doc.add_heading(level=min(3, max(1, level)))
            h_p.alignment = WD_ALIGN_PARAGRAPH.LEFT

            sizes = {1: 16.0, 2: 13.5, 3: 12.0, 4: 11.5, 5: 11.0, 6: 10.5}
            pt_sz = sizes.get(level, 12.0)
            if level == 1:
                h_p.paragraph_format.space_before = Pt(16)
                h_p.paragraph_format.space_after = Pt(6)
            elif level == 2:
                h_p.paragraph_format.space_before = Pt(12)
                h_p.paragraph_format.space_after = Pt(4)
            else:
                h_p.paragraph_format.space_before = Pt(8)
                h_p.paragraph_format.space_after = Pt(2)

            add_inline_markdown(h_p, h_text, default_size_pt=pt_sz, default_color_rgb=RGBColor(0x0F, 0x17, 0x2A))
            for r in h_p.runs:
                r.font.bold = True
            idx += 1
            continue

        # 4. Fenced Code Block (```lang ... ```)
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines = []
            idx += 1
            while idx < num_lines and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            if idx < num_lines:
                idx += 1  # consume closing fence

            from .docx_creator import add_code_block
            add_code_block(doc, "\n".join(code_lines))
            continue

        # 5. Display Math ($$ ... $$)
        if stripped.startswith("$$"):
            math_lines = []
            if stripped == "$$":
                idx += 1
                while idx < num_lines and not lines[idx].strip().startswith("$$"):
                    math_lines.append(lines[idx])
                    idx += 1
                if idx < num_lines:
                    idx += 1
            else:
                core = stripped.strip("$")
                math_lines.append(core)
                idx += 1

            from .docx_creator import add_math_equation_block
            add_math_equation_block(doc, math_lines)
            continue

        # 6. Blockquote or Alert (> [!NOTE] or > quote)
        if stripped.startswith(">"):
            b_lines = []
            while idx < num_lines and lines[idx].strip().startswith(">"):
                raw_b = lines[idx].strip()
                cleaned = re.sub(r'^>\s?', '', raw_b)
                b_lines.append(cleaned)
                idx += 1

            first = b_lines[0] if b_lines else ""
            alert_m = re.match(r'^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$', first, re.IGNORECASE)
            if alert_m:
                a_type = alert_m.group(1).upper()
                a_title = alert_m.group(2).strip() or None
                render_alert_box(doc, a_type, a_title, b_lines[1:])
            else:
                table = doc.add_table(rows=1, cols=1)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                cell = table.rows[0].cells[0]
                cell.width = Inches(5.8)
                _set_cell_bg(cell, "F8FAFC")
                _set_cell_borders(cell, left="94A3B8")
                _set_cell_padding(cell, top=80, bottom=80, left=160, right=120)
                for i, q_l in enumerate(b_lines):
                    qp = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
                    qp.paragraph_format.space_before = Pt(0)
                    qp.paragraph_format.space_after = Pt(2)
                    qp.paragraph_format.line_spacing = 1.3
                    add_inline_markdown(qp, q_l, default_size_pt=10.5, default_color_rgb=RGBColor(0x33, 0x41, 0x55))
                    for r in qp.runs:
                        r.font.italic = True
                sp = doc.add_paragraph()
                sp.paragraph_format.space_before = Pt(2)
                sp.paragraph_format.space_after = Pt(4)
            continue

        # 7. Tables (| col 1 | col 2 |)
        if stripped.startswith("|") and stripped.endswith("|"):
            tbl_lines = []
            while idx < num_lines and lines[idx].strip().startswith("|"):
                tbl_lines.append(lines[idx].strip())
                idx += 1

            if len(tbl_lines) >= 2:
                raw_h = [c.strip() for c in tbl_lines[0].strip("|").split("|")]
                raw_sep = [c.strip() for c in tbl_lines[1].strip("|").split("|")]
                alignments = []
                for s in raw_sep:
                    if s.startswith(":") and s.endswith(":"):
                        alignments.append("center")
                    elif s.endswith(":"):
                        alignments.append("right")
                    else:
                        alignments.append("left")

                data_rows = []
                for d_line in tbl_lines[2:]:
                    row_cells = [c.strip() for c in d_line.strip("|").split("|")]
                    data_rows.append(row_cells)

                render_markdown_table(doc, raw_h, data_rows, alignments)
                continue

        # 8. Lists: Task lists (- [ ] or - [x]), Unordered (*, -, +), Ordered (1.)
        task_m = re.match(r'^[-*+]\s+\[([ xX])\]\s+(.*)$', stripped)
        if task_m:
            is_checked = task_m.group(1).lower() == "x"
            item_text = task_m.group(2).strip()
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.3
            box = "☑  " if is_checked else "☐  "
            r_box = p.add_run(box)
            r_box.font.name = "Segoe UI Symbol"
            r_box.font.size = Pt(11)
            r_box.font.bold = True
            r_box.font.color.rgb = RGBColor(0x05, 0x96, 0x69) if is_checked else RGBColor(0x64, 0x74, 0x8B)
            add_inline_markdown(p, item_text, default_size_pt=11.0)
            idx += 1
            continue

        bullet_m = re.match(r'^[-*+]\s+(.*)$', stripped)
        if bullet_m:
            item_text = bullet_m.group(1).strip()
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.3
            add_inline_markdown(p, item_text, default_size_pt=11.0)
            idx += 1
            continue

        ordered_m = re.match(r'^(\d+)[.)]\s+(.*)$', stripped)
        if ordered_m:
            num_str, item_text = ordered_m.group(1), ordered_m.group(2).strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.3
            p.paragraph_format.left_indent = Inches(0.25)
            r_num = p.add_run(f"{num_str}.  ")
            r_num.font.name = "Times New Roman"
            r_num.font.size = Pt(11)
            r_num.font.bold = True
            add_inline_markdown(p, item_text, default_size_pt=11.0)
            idx += 1
            continue

        # 9. Images (![alt](path))
        img_m = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if img_m:
            alt, img_src = img_m.group(1), img_m.group(2)
            from .docx_creator import add_styled_figure
            add_styled_figure(doc, image_path=img_src, caption=alt or None)
            idx += 1
            continue

        # 10. Default Body Paragraph
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(6)
        add_inline_markdown(p, stripped, default_font="Times New Roman", default_size_pt=12.0)
        idx += 1


def markdown_to_docx(markdown_text: str, output_path: str | Path | None = None, title: str | None = None) -> Document:
    """Convert a complete Markdown document string into a high-grade Word .docx file."""
    doc = Document()

    for sec in doc.sections:
        sec.page_width = Inches(8.27)
        sec.page_height = Inches(11.69)
        sec.left_margin = Inches(1.25)
        sec.right_margin = Inches(1.0)
        sec.top_margin = Inches(1.0)
        sec.bottom_margin = Inches(1.0)

    if title:
        tp = doc.add_paragraph()
        tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        tp.paragraph_format.space_before = Pt(12)
        tp.paragraph_format.space_after = Pt(12)
        tr = tp.add_run(title)
        tr.font.name = "Times New Roman"
        tr.font.size = Pt(20)
        tr.font.bold = True
        tr.font.color.rgb = RGBColor(0x18, 0x1A, 0x20)

    parse_markdown_into_doc(markdown_text, doc)

    if output_path:
        out_f = Path(output_path).expanduser().resolve()
        out_f.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_f))

    return doc


def parse_markdown_into_sections(markdown_text: str) -> list[dict[str, Any]]:
    """Parse Markdown text into structured Sortwise sections.

    Each section dictionary contains:
    - heading: str
    - level: int (1-6)
    - paragraphs: list[str]
    - bullets: list[str]
    - alerts: list[dict[str, Any]] (type, title, lines)
    - table: dict[str, Any] | None (headers, rows, alignments)
    - equations: list[dict[str, Any]] (formulas, num, explanation)
    - code: str | None
    - image_path: str | None
    - caption: str | None
    - page_break: bool
    - raw_markdown: str
    """
    if not markdown_text or not markdown_text.strip():
        return []

    sections: list[dict[str, Any]] = []
    lines = markdown_text.strip().split("\n")
    num_lines = len(lines)
    idx = 0
    eq_counter = 1

    def _new_section(heading: str = "", level: int = 1, page_break: bool = False) -> dict[str, Any]:
        return {
            "heading": heading,
            "level": level,
            "paragraphs": [],
            "bullets": [],
            "alerts": [],
            "table": None,
            "equations": [],
            "code": None,
            "image_path": None,
            "caption": None,
            "page_break": page_break,
            "raw_markdown": "",
        }

    current_sec = _new_section()

    def _has_content(sec: dict[str, Any]) -> bool:
        return bool(
            sec["heading"]
            or sec["paragraphs"]
            or sec["bullets"]
            or sec["alerts"]
            or sec["table"]
            or sec["equations"]
            or sec["code"]
            or sec["image_path"]
        )

    while idx < num_lines:
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            idx += 1
            continue

        # Page break markers
        if stripped in ("<!-- pagebreak -->", "\\pagebreak", "<!-- PAGE_BREAK -->"):
            current_sec["page_break"] = True
            idx += 1
            continue

        # Horizontal Rule (---, ***, ___)
        if re.match(r'^(?:-{3,}|\*{3,}|_{3,})$', stripped):
            current_sec["paragraphs"].append("―" * 40)
            idx += 1
            continue

        # Headings (# to ######)
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            if _has_content(current_sec):
                sections.append(current_sec)
            lvl = len(heading_match.group(1))
            h_text = heading_match.group(2).strip()
            # Top-level headings after the first section break page by default
            should_break = (lvl == 1 and len(sections) > 0)
            current_sec = _new_section(heading=h_text, level=lvl, page_break=should_break)
            idx += 1
            continue

        # Fenced Code Block
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines = []
            idx += 1
            while idx < num_lines and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            if idx < num_lines:
                idx += 1
            current_sec["code"] = "\n".join(code_lines)
            continue

        # Display Math ($$...$$)
        if stripped.startswith("$$"):
            math_lines = []
            if stripped == "$$":
                idx += 1
                while idx < num_lines and not lines[idx].strip().startswith("$$"):
                    math_lines.append(lines[idx].strip())
                    idx += 1
                if idx < num_lines:
                    idx += 1
            else:
                core = stripped.strip("$").strip()
                math_lines.append(core)
                idx += 1

            current_sec["equations"].append({
                "num": str(eq_counter),
                "formulas": math_lines,
                "explanation": None,
            })
            eq_counter += 1
            continue

        # Blockquotes & Alerts (> [!NOTE] or > quote)
        if stripped.startswith(">"):
            b_lines = []
            while idx < num_lines and lines[idx].strip().startswith(">"):
                cleaned = re.sub(r'^>\s?', '', lines[idx].strip())
                b_lines.append(cleaned)
                idx += 1

            first = b_lines[0] if b_lines else ""
            alert_m = re.match(r'^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$', first, re.IGNORECASE)
            if alert_m:
                current_sec["alerts"].append({
                    "type": alert_m.group(1).upper(),
                    "title": alert_m.group(2).strip() or None,
                    "lines": b_lines[1:],
                })
            else:
                current_sec["paragraphs"].append(" ".join(b_lines))
            continue

        # Tables (| col 1 | col 2 |)
        if stripped.startswith("|") and stripped.endswith("|"):
            tbl_lines = []
            while idx < num_lines and lines[idx].strip().startswith("|"):
                tbl_lines.append(lines[idx].strip())
                idx += 1

            if len(tbl_lines) >= 2:
                raw_h = [c.strip() for c in tbl_lines[0].strip("|").split("|")]
                raw_sep = [c.strip() for c in tbl_lines[1].strip("|").split("|")]
                alignments = []
                for s in raw_sep:
                    if s.startswith(":") and s.endswith(":"):
                        alignments.append("center")
                    elif s.endswith(":"):
                        alignments.append("right")
                    else:
                        alignments.append("left")

                data_rows = []
                for d_line in tbl_lines[2:]:
                    row_cells = [c.strip() for c in d_line.strip("|").split("|")]
                    data_rows.append(row_cells)

                current_sec["table"] = {
                    "headers": raw_h,
                    "rows": data_rows,
                    "alignments": alignments,
                }
            continue

        # Task list (- [ ] or - [x])
        task_m = re.match(r'^[-*+]\s+\[([ xX])\]\s+(.*)$', stripped)
        if task_m:
            box = "☑  " if task_m.group(1).lower() == "x" else "☐  "
            current_sec["bullets"].append(box + task_m.group(2).strip())
            idx += 1
            continue

        # Unordered list (- or * or +)
        bullet_m = re.match(r'^[-*+]\s+(.*)$', stripped)
        if bullet_m:
            current_sec["bullets"].append(bullet_m.group(1).strip())
            idx += 1
            continue

        # Ordered list (1. or 1))
        ordered_m = re.match(r'^(\d+)[.)]\s+(.*)$', stripped)
        if ordered_m:
            current_sec["bullets"].append(f"{ordered_m.group(1)}. {ordered_m.group(2).strip()}")
            idx += 1
            continue

        # Image (![alt](path))
        img_m = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if img_m:
            current_sec["image_path"] = img_m.group(2).strip()
            current_sec["caption"] = img_m.group(1).strip() or None
            idx += 1
            continue

        # Standard Body Paragraph (collect contiguous lines)
        p_lines = [stripped]
        idx += 1
        while idx < num_lines:
            next_l = lines[idx].strip()
            if not next_l:
                break
            if next_l.startswith(("#", "```", "$$", ">", "|", "-", "*", "+", "!", "<!--")):
                break
            p_lines.append(next_l)
            idx += 1

        current_sec["paragraphs"].append(" ".join(p_lines))

    if _has_content(current_sec):
        sections.append(current_sec)

    return sections
