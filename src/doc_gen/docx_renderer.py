"""Dedicated OpenXML DOCX Renderer and Validator for Filevo.

Constructs valid, beautifully formatted Microsoft Word (.docx) documents natively
using standard library zipfile and xml.etree.ElementTree, with 0 external C-dependencies.
"""

import os
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.doc_gen.rlcd_engine import FormattingStrategy


class DocxRenderer:
    """Renders structured documents into validated OpenXML DOCX files."""

    def __init__(self, output_dir: str | None = None):
        if output_dir is None:
            self.output_dir = Path.home() / ".filevo" / "output"
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render(
        self,
        title: str,
        sections: list[dict[str, Any]],
        strategy: FormattingStrategy,
        output_filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Render a document according to the specified formatting strategy.

        sections is a list of dicts:
          [{"title": "Section Title", "content": "Paragraph text...", "table": [[...], [...]]}]
        """
        if output_filename is None:
            clean_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).rstrip()
            clean_title = clean_title.replace(" ", "_")[:35]
            output_filename = f"{clean_title}.docx"

        out_path = self.output_dir / output_filename
        font = strategy.font_family
        accent = strategy.accent_color

        # Build document XML parts
        content_types_xml = self._build_content_types_xml()
        root_rels_xml = self._build_root_rels_xml()
        doc_rels_xml = self._build_doc_rels_xml()
        styles_xml = self._build_styles_xml(font, accent)
        document_xml = self._build_document_xml(title, sections, strategy)

        # Write to Zip archive
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types_xml)
            z.writestr("_rels/.rels", root_rels_xml)
            z.writestr("word/_rels/document.xml.rels", doc_rels_xml)
            z.writestr("word/styles.xml", styles_xml)
            z.writestr("word/document.xml", document_xml)

        # Validate result
        self.validate(out_path)
        return out_path

    def validate(self, docx_path: Path) -> bool:
        """Validate that the output DOCX is a healthy, parseable OpenXML container."""
        if not docx_path.exists() or docx_path.stat().st_size == 0:
            raise ValueError(f"DOCX validation failed: file is missing or zero bytes at {docx_path}")

        with zipfile.ZipFile(docx_path, "r") as z:
            names = set(z.namelist())
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml"}
            missing = required - names
            if missing:
                raise ValueError(f"DOCX validation failed: missing OpenXML members {missing}")

            # Verify XML parsing
            try:
                doc_xml = z.read("word/document.xml")
                ET.fromstring(doc_xml)
            except Exception as e:
                raise ValueError(f"DOCX validation failed: corrupted document.xml: {e}")

        return True

    # ------------------------------------------------------------------ #
    # XML Generators
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_content_types_xml() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

    @staticmethod
    def _build_root_rels_xml() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    @staticmethod
    def _build_doc_rels_xml() -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    @staticmethod
    def _build_styles_xml(font: str, accent: str) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:docDefaults>
        <w:rPrDefault>
            <w:rPr>
                <w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>
                <w:sz w:val="22"/>
                <w:color w:val="222222"/>
            </w:rPr>
        </w:rPrDefault>
        <w:pPrDefault>
            <w:pPr>
                <w:spacing w:line="276" w:lineRule="auto" w:after="160"/>
            </w:pPr>
        </w:pPrDefault>
    </w:docDefaults>
    <w:style w:type="paragraph" w:styleId="Title">
        <w:name w:val="Title"/>
        <w:rPr>
            <w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>
            <w:b/>
            <w:sz w:val="52"/>
            <w:color w:val="{accent}"/>
        </w:rPr>
    </w:style>
    <w:style w:type="paragraph" w:styleId="Heading1">
        <w:name w:val="heading 1"/>
        <w:pPr>
            <w:spacing w:before="360" w:after="140"/>
        </w:pPr>
        <w:rPr>
            <w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>
            <w:b/>
            <w:sz w:val="34"/>
            <w:color w:val="{accent}"/>
        </w:rPr>
    </w:style>
    <w:style w:type="paragraph" w:styleId="Heading2">
        <w:name w:val="heading 2"/>
        <w:pPr>
            <w:spacing w:before="260" w:after="100"/>
        </w:pPr>
        <w:rPr>
            <w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>
            <w:b/>
            <w:sz w:val="28"/>
            <w:color w:val="444444"/>
        </w:rPr>
    </w:style>
</w:styles>"""

    @staticmethod
    def _escape_xml(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _build_document_xml(
        self,
        title: str,
        sections: list[dict[str, Any]],
        strategy: FormattingStrategy,
    ) -> str:
        margin_dxa = int(strategy.margin_inches * 1440)  # 1 inch = 1440 dxa
        font = strategy.font_family
        accent = strategy.accent_color

        body_elements = []

        # Document Title
        esc_title = self._escape_xml(title)
        body_elements.append(f"""
        <w:p>
            <w:pPr>
                <w:pStyle w:val="Title"/>
                <w:spacing w:before="200" w:after="280"/>
            </w:pPr>
            <w:r>
                <w:t>{esc_title}</w:t>
            </w:r>
        </w:p>""")

        # Callout highlight box if strategy permits
        if strategy.include_callouts:
            body_elements.append(f"""
        <w:p>
            <w:pPr>
                <w:pBdr>
                    <w:left w:val="single" w:sz="24" w:space="12" w:color="{accent}"/>
                </w:pBdr>
                <w:shd w:val="clear" w:color="auto" w:fill="F4F6F8"/>
                <w:spacing w:before="120" w:after="240"/>
                <w:ind w:left="240" w:right="120"/>
            </w:pPr>
            <w:r>
                <w:rPr>
                    <w:i/>
                    <w:color w:val="555555"/>
                </w:rPr>
                <w:t>Executive Note: Synthesized with Filevo RLCD Engine. Formatting strategy calibrated to {font} typography and {strategy.margin_inches}&quot; geometry.</w:t>
            </w:r>
        </w:p>""")

        # Render each section
        for sec in sections:
            sec_title = sec.get("title", "")
            sec_content = sec.get("content", "")
            table_data = sec.get("table", None)

            if sec_title:
                esc_sec_title = self._escape_xml(sec_title)
                body_elements.append(f"""
        <w:p>
            <w:pPr>
                <w:pStyle w:val="Heading1"/>
            </w:pPr>
            <w:r>
                <w:t>{esc_sec_title}</w:t>
            </w:r>
        </w:p>""")

            # Section paragraphs
            if sec_content:
                paragraphs = sec_content.split("\n\n")
                for p_text in paragraphs:
                    clean_p = p_text.strip()
                    if not clean_p:
                        continue
                    if clean_p.startswith("### "):
                        # Subheading
                        esc_h2 = self._escape_xml(clean_p[4:])
                        body_elements.append(f"""
        <w:p>
            <w:pPr>
                <w:pStyle w:val="Heading2"/>
            </w:pPr>
            <w:r>
                <w:t>{esc_h2}</w:t>
            </w:r>
        </w:p>""")
                    elif clean_p.startswith("- ") or clean_p.startswith("* "):
                        # Bullet points
                        for line in clean_p.split("\n"):
                            bullet_text = line.lstrip("-* ").strip()
                            esc_bullet = self._escape_xml(bullet_text)
                            body_elements.append(f"""
        <w:p>
            <w:pPr>
                <w:ind w:left="400" w:hanging="200"/>
                <w:spacing w:line="240" w:after="80"/>
            </w:pPr>
            <w:r>
                <w:t>• </w:t>
            </w:r>
            <w:r>
                <w:t>{esc_bullet}</w:t>
            </w:r>
        </w:p>""")
                    else:
                        esc_body = self._escape_xml(clean_p)
                        body_elements.append(f"""
        <w:p>
            <w:r>
                <w:t>{esc_body}</w:t>
            </w:r>
        </w:p>""")

            # Render Table if present
            if table_data and strategy.include_tables:
                body_elements.append(self._build_table_xml(table_data, accent))

        # Page Setup (Margins)
        body_elements.append(f"""
        <w:sectPr>
            <w:pgSz w:w="12240" w:h="15840"/>
            <w:pgMar w:top="{margin_dxa}" w:right="{margin_dxa}" w:bottom="{margin_dxa}" w:left="{margin_dxa}" w:header="720" w:footer="720"/>
        </w:sectPr>""")

        xml_body = "\n".join(body_elements)
        return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
{xml_body}
    </w:body>
</w:document>"""

    def _build_table_xml(self, rows: list[list[str]], accent: str) -> str:
        """Render a formatted OpenXML table with header shading and borders."""
        table_rows = []
        for r_idx, row in enumerate(rows):
            is_header = (r_idx == 0)
            cell_xmls = []
            for cell in row:
                esc_cell = self._escape_xml(str(cell))
                shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{accent}"/>' if is_header else '<w:shd w:val="clear" w:color="auto" w:fill="F9FAFB"/>'
                color = '<w:color w:val="FFFFFF"/>' if is_header else '<w:color w:val="222222"/>'
                bold = '<w:b/>' if is_header else ''

                cell_xml = f"""
                <w:tc>
                    <w:tcPr>
                        {shd}
                        <w:tcMar>
                            <w:top w:w="120" w:type="dxa"/>
                            <w:left w:w="160" w:type="dxa"/>
                            <w:bottom w:w="120" w:type="dxa"/>
                            <w:right w:w="160" w:type="dxa"/>
                        </w:tcMar>
                    </w:tcPr>
                    <w:p>
                        <w:r>
                            <w:rPr>
                                {bold}
                                {color}
                            </w:rPr>
                            <w:t>{esc_cell}</w:t>
                        </w:r>
                    </w:p>
                </w:tc>"""
                cell_xmls.append(cell_xml)

            row_xml = f"""
            <w:tr>
                {''.join(cell_xmls)}
            </w:tr>"""
            table_rows.append(row_xml)

        return f"""
        <w:tbl>
            <w:tblPr>
                <w:tblW w:w="5000" w:type="pct"/>
                <w:tblBorders>
                    <w:top w:val="single" w:sz="6" w:space="0" w:color="D0D5DD"/>
                    <w:left w:val="none"/>
                    <w:bottom w:val="single" w:sz="12" w:space="0" w:color="{accent}"/>
                    <w:right w:val="none"/>
                    <w:insideH w:val="single" w:sz="4" w:space="0" w:color="E5E7EB"/>
                    <w:insideV w:val="none"/>
                </w:tblBorders>
            </w:tblPr>
            {''.join(table_rows)}
        </w:tbl>"""
