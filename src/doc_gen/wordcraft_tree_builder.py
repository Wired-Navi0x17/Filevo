"""Lower a themed DocumentIR (knowledge-tree pipeline) into WordCraft commands.

All typography comes from the theme dict (``data/themes/*.toml``): fonts,
sizes, colours, margins, leading, heading numbering and TOC depth. Styles are
defined once (Normal, Title, Subtitle, Heading 1-3, Caption, and the custom
Lead, Callout and Equation Note styles) and then applied by name, so the saved
.docx carries real styles rather than hand formatting.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from src.doc_gen.document_ir import (
    CalloutBlock,
    DocumentIR,
    EquationBlock,
    ImageBlock,
    ListBlock,
    PageBreakBlock,
    ParagraphBlock,
    SectionIR,
    TableBlock,
)

TABLE_STYLE = "Filevo Rules"


def _c(command: str, **params: Any) -> dict[str, Any]:
    return {"command": command, "params": params} if params else {"command": command}


def _spacing(rule_value: float) -> dict[str, Any]:
    return {"rule": "multiple", "value": float(rule_value)}


def _csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().rstrip("\n")


def style_commands(theme: dict[str, Any]) -> list[dict[str, Any]]:
    f, s, col, lay = theme["fonts"], theme["size"], theme["color"], theme["layout"]
    body_ls = _spacing(lay["line_spacing"])
    return [
        _c("tools.autocorrect", enabled=False),
        _c("layout.margins", top=lay["margin_top"], bottom=lay["margin_bottom"],
           left=lay["margin_side"], right=lay["margin_side"]),
        _c("design.themeFonts", heading=f["display"], body=f["body"]),
        _c("styles.modify", style="Normal",
           chr={"font": f["body"], "size": s["body"], "color": col["text"]},
           para={"lineSpacing": body_ls, "spaceBefore": 0, "spaceAfter": lay["space_after"]}),
        _c("styles.modify", style="Title",
           chr={"font": f["display"], "size": s["title"], "color": col["accent"], "bold": False},
           para={"spaceAfter": 6, "lineSpacing": _spacing(1.05)}),
        _c("styles.modify", style="Subtitle",
           chr={"font": f["display"], "size": s["subtitle"], "color": col["muted"], "italic": True},
           para={"spaceAfter": 18}),
        _c("styles.modify", style="Heading 1",
           chr={"font": f["display"], "size": s["h1"], "bold": True, "color": col["accent"]},
           para={"spaceBefore": 22, "spaceAfter": 6, "keepNext": True}),
        _c("styles.modify", style="Heading 2",
           chr={"font": f["display"], "size": s["h2"], "bold": True, "color": col["accent_soft"]},
           para={"spaceBefore": 14, "spaceAfter": 4, "keepNext": True}),
        _c("styles.modify", style="Heading 3",
           chr={"font": f["display"], "size": s["h3"], "bold": True, "italic": False, "color": col["accent_soft"]},
           para={"spaceBefore": 10, "spaceAfter": 3, "keepNext": True}),
        _c("styles.modify", style="Caption",
           chr={"font": f["body"], "size": s["caption"], "italic": True, "color": col["muted"]},
           para={"spaceBefore": 4, "spaceAfter": 8, "keepNext": True}),
        _c("styles.create", name="Lead", basedOn="Normal"),
        _c("styles.modify", style="Lead", chr={"bold": True}, para={"keepNext": True, "spaceAfter": 2}),
        _c("styles.create", name="Callout", basedOn="Normal"),
        _c("styles.modify", style="Callout",
           chr={"color": col["accent"]},
           para={"shading": col["callout_fill"], "indentLeft": 8, "indentRight": 8,
                 "spaceBefore": 4, "spaceAfter": 10}),
        _c("styles.create", name="Equation Note", basedOn="Normal"),
        _c("styles.modify", style="Equation Note",
           chr={"size": s["body"] - 0.5, "color": col["muted"]},
           para={"indentLeft": 22, "spaceAfter": lay["space_after"] + 3}),
    ]


def _para(style: str, text: str) -> list[dict[str, Any]]:
    return [_c("para.style", style=style), _c("text.insert", text=text), _c("text.newParagraph")]


def _paragraph_block(b: ParagraphBlock) -> list[dict[str, Any]]:
    style = b.style if b.style in ("Lead", "Normal", "Callout") else "Normal"
    cmds = [_c("para.style", style=style)]
    for run in b.runs:
        if run.bold and style != "Lead":
            cmds += [_c("format.bold", value=True), _c("text.insert", text=run.text), _c("format.bold", value=False)]
        else:
            cmds.append(_c("text.insert", text=run.text))
    cmds.append(_c("text.newParagraph"))
    return cmds


def block_commands(block: Any, theme: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(block, ParagraphBlock):
        return _paragraph_block(block)
    if isinstance(block, ListBlock):
        kind = {"kind": "numbered"} if block.ordered else {}
        cmds = [_c("para.style", style="Normal"),
                _c("para.numbering", **kind) if block.ordered else _c("para.bullets")]
        if block.ordered:
            cmds.append(_c("para.restartNumbering"))
        cmds.append(_c("text.insert", text="\n".join(block.items), paragraphs=True))
        cmds.append(_c("text.newParagraph"))
        cmds.append(_c("para.numbering", off=True) if block.ordered else _c("para.bullets", off=True))
        return cmds
    if isinstance(block, EquationBlock):
        cmds = [_c("para.style", style="Normal"),
                _c("insert.equation", latex=block.latex, display=True, edit=False),
                _c("caret.docEnd"), _c("text.newParagraph")]
        if block.name:
            label = f"Equation {block.number}. {block.name}" if block.number else block.name
            cmds += _para("Caption", label)
        return cmds
    if isinstance(block, TableBlock):
        rows = ([block.headers] if block.headers else []) + block.rows
        if not rows:
            return []
        cmds = []
        if block.caption:
            cmds += _para("Caption", block.caption)
        cmds += [_c("para.style", style="Normal"), _c("insert.spreadsheet", csv=_csv(rows))]
        if not state.get("table_style"):
            col = theme["color"]
            cmds.append(_c(
                "table.newStyle", name=TABLE_STYLE, apply=True,
                para={"lineSpacing": _spacing(1.1), "spaceAfter": 0, "spaceBefore": 0},
                wholeTable={"font": theme["fonts"]["body"], "size": theme["size"]["table"],
                            "borders": [{"edges": "none"},
                                        {"edges": "top", "style": "single", "width": 1.25, "color": col["rule"]},
                                        {"edges": "bottom", "style": "single", "width": 1.25, "color": col["rule"]},
                                        {"edges": "insideH", "style": "single", "width": 0.5, "color": col["rule_soft"]}]},
                headerRow={"bold": True, "color": col["accent"],
                           "borders": [{"edges": "bottom", "style": "single", "width": 0.75, "color": col["rule"]}]},
            ))
            state["table_style"] = True
        else:
            cmds.append(_c("table.style", style=TABLE_STYLE))
        cmds += [_c("table.look", headerRow=True, bandedRows=False, firstColumn=False),
                 _c("table.cellMargins", top=3, bottom=3, left=5, right=5),
                 _c("table.repeatHeader"),
                 _c("caret.docEnd"), _c("para.style", style="Normal"), _c("para.spacing", before=8)]
        return cmds
    if isinstance(block, CalloutBlock):
        text = f"{block.title}. {block.content}" if block.title else block.content
        return [_c("para.style", style="Callout"),
                _c("format.bold", value=True), _c("text.insert", text=f"{block.title}. " if block.title else ""),
                _c("format.bold", value=False), _c("text.insert", text=block.content),
                _c("text.newParagraph")] if block.title else _para("Callout", text)
    if isinstance(block, ImageBlock):
        params: dict[str, Any] = {"path": str(block.path), "width": float(block.width_inches) * 72.0}
        if block.caption:
            params["alt"] = block.caption
        cmds = [_c("para.style", style="Normal"), _c("insert.picture", **params), _c("caret.docEnd"),
                _c("text.newParagraph")]
        if block.caption:
            cmds += _para("Caption", block.caption)
        return cmds
    if isinstance(block, PageBreakBlock):
        return [_c("text.pageBreak")]
    return []


def section_commands(sec: SectionIR, theme: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    level = max(1, min(3, sec.level))
    cmds = _para(f"Heading {level}", sec.title)
    for b in sec.blocks:
        cmds += block_commands(b, theme, state)
    for sub in sec.subsections:
        cmds += section_commands(sub, theme, state)
    return cmds


def build_commands(doc: DocumentIR) -> list[dict[str, Any]]:
    theme = doc.theme or {}
    lay = theme["layout"]
    state: dict[str, Any] = {}
    cmds = style_commands(theme)

    # Running header with the title, footer with page numbers.
    cmds += [_c("insert.header", text=doc.header_text or doc.title), _c("insert.closeHeader")]
    if doc.include_page_numbers:
        cmds += [_c("insert.footer", preset="pageNumber"), _c("insert.closeHeader")]

    # Title block (a cover page when the policy asked for one).
    cmds += _para("Title", doc.title)
    sub = " · ".join(p for p in (doc.subtitle, doc.date_str) if p)
    if sub:
        cmds += _para("Subtitle", sub)
    if doc.cover_page:
        cmds.append(_c("text.pageBreak"))

    if doc.include_toc:
        cmds += [_c("references.toc", levels=int(lay.get("toc_levels", 2)), title="Contents",
                    pageNumbers=True, rightAlign=True, tabLeader="dot", hyperlinks=True),
                 _c("caret.docEnd"), _c("text.pageBreak")]

    for sec in doc.sections:
        cmds += section_commands(sec, theme, state)

    if doc.references:
        cmds += _para("Heading 1", doc.references_title)
        cmds += [_c("para.style", style="Normal"), _c("para.numbering", kind="numbered"),
                 _c("para.restartNumbering"),
                 _c("text.insert", text="\n".join(
                     f"{r.title}. {r.url}" + (f" ({r.snippet})" if r.snippet else "") for r in doc.references),
                    paragraphs=True),
                 _c("text.newParagraph"), _c("para.numbering", off=True)]

    if lay.get("heading_numbering"):
        cmds.append(_c("caret.docStart"))
        cmds.append(_c("list.multilevelPreset", preset="headings"))
    if doc.include_toc:
        cmds.append(_c("references.updateToc"))
    return cmds
