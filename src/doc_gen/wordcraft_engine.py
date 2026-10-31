"""WordCraft MCP Integration Engine for Filevo.

Bridges Filevo's LLM planning, RLCD decision policies, and Anti-Slop document
standards to ArtCraft's WordCraft desktop application and CLI via its official
Model Context Protocol (MCP) server.

Capabilities:
1. Primary authoring engine for Filevo document creation.
2. Structured Document Intermediate Representation (DocumentIR) translation.
3. Anti-AI Slop Policy enforcement (BLUF, banned cliches, signature elements, editorial typography).
4. Dual operation modes:
   - Live visible desktop mode: observe document construction in real-time GUI (--control 7981).
   - Headless automated mode: high-throughput background generation and CI/testing.
5. Dual publication output: validated Microsoft Word (.docx) and high-fidelity PDF (.pdf).
6. AST Document Inspection (`inspect_document`) and visual page rendering (`render_page`).
7. Graceful fallback to Filevo's native OpenXML DocxRenderer.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.doc_gen.antislop_policy import AntiSlopPolicy, get_antislop_policy
from src.doc_gen.document_brief import DocumentBrief
from src.doc_gen.document_ir import (
    CalloutBlock,
    DocumentIR,
    ImageBlock,
    ListBlock,
    PageBreakBlock,
    ParagraphBlock,
    SectionIR,
    TableBlock,
)
from src.doc_gen.rlcd_engine import FormattingStrategy
from src.doc_gen.wordcraft_adapter import (
    WordCraftClient,
    WordCraftConfig,
    WordCraftMCPError,
    WordCraftUnreachableError,
)

logger = logging.getLogger("filevo.wordcraft")


@dataclass
class WordCraftResult:
    """Telemetry and output artifacts produced by WordCraft composition."""

    docx_path: Path
    pdf_path: Path | None = None
    preview_image_path: Path | None = None
    doc_md_path: Path | None = None
    words: int = 0
    pages: int = 0
    blocks: int = 0
    tables_count: int = 0
    inspection_data: dict[str, Any] = field(default_factory=dict)
    visible_mode: bool = False
    composition_duration_ms: float = 0.0


class WordCraftEngine:
    """High-level composition orchestrator driving WordCraft via official MCP."""

    DEFAULT_CONTROL_PORT = 7981

    def __init__(self, output_dir: Path | str | None = None, config: WordCraftConfig | None = None):
        self.config = config or WordCraftConfig.load()
        if output_dir is not None:
            self.output_dir = Path(output_dir)
            self.config.output_dir = self.output_dir
        else:
            self.output_dir = self.config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._gui_path: Path | None = None
        self._cli_path: Path | None = None
        self._detect_environment()

    def _detect_environment(self) -> None:
        """Locates WordCraft GUI binary and CLI executable."""
        gui_candidates = [
            Path.home() / ".local" / "opt" / "wordcraft" / "usr" / "bin" / "wordcraft",
            Path.home() / ".local" / "bin" / "wordcraft",
            Path.home() / "Applications" / "WordCraft.AppImage",
        ]
        which_gui = shutil.which("wordcraft")
        if which_gui:
            gui_candidates.insert(0, Path(which_gui))

        for g in gui_candidates:
            if g.exists():
                self._gui_path = g
                break

        try:
            client = WordCraftClient(self.config)
            resolved = client._resolve_executable()
            self._cli_path = Path(resolved[-1])
        except Exception:
            self._cli_path = None

    def is_available(self) -> bool:
        """Returns True if WordCraft CLI is detected and executable."""
        return self._cli_path is not None and self._cli_path.exists()

    def get_info(self) -> dict[str, Any]:
        """Telemetry details about WordCraft installation."""
        sr = Path("/run/current-system/sw/bin/steam-run")
        runner = str(sr) if sr.exists() else "native"
        port = int(self.config.control_address.split(":")[-1]) if ":" in self.config.control_address else 7981
        return {
            "available": self.is_available(),
            "cli_path": str(self._cli_path) if self._cli_path else None,
            "gui_path": str(self._gui_path) if self._gui_path else None,
            "runner": runner,
            "control_port": port,
            "control_address": self.config.control_address,
            "mode": self.config.mode,
        }

    def _wrap_command(self, cmd_args: list[str]) -> list[str]:
        """Wraps invocation with steam-run when on NixOS."""
        sr = Path("/run/current-system/sw/bin/steam-run")
        if sr.exists() and any("opt/wordcraft" in str(arg) for arg in cmd_args):
            return [str(sr)] + cmd_args
        return cmd_args

    def _is_port_in_use(self, port: int) -> bool:
        """Checks if a TCP port is active on localhost."""
        return WordCraftClient.is_desktop_reachable(f"127.0.0.1:{port}")

    def is_desktop_running(self) -> bool:
        """Checks if WordCraft desktop application is actively listening on control address."""
        return WordCraftClient.is_desktop_reachable(self.config.control_address)

    def _ensure_gui_running(self) -> subprocess.Popen | None:
        """Ensures WordCraft desktop application is running on configured control address."""
        addr = self.config.control_address
        if WordCraftClient.is_desktop_reachable(addr):
            logger.info("WordCraft desktop control port %s is already active.", addr)
            return None

        if not self._gui_path:
            port = addr.split(":")[-1] if ":" in addr else "7981"
            raise WordCraftUnreachableError(
                f"WordCraft desktop application is not running on {addr}.\n"
                f"Please launch WordCraft in desktop control mode via:\n"
                f"    wordcraft --control {port}"
            )

        port = addr.split(":")[-1] if ":" in addr else "7981"
        sr = Path("/run/current-system/sw/bin/steam-run")
        if str(self._gui_path).endswith(".local/bin/wordcraft"):
            raw_cmd = [str(self._gui_path), "--control", port]
        elif sr.exists():
            raw_cmd = [str(sr), str(self._gui_path), "--control", port]
        else:
            raw_cmd = [str(self._gui_path), "--control", port]
        cmd = ["setsid"] + raw_cmd if shutil.which("setsid") else raw_cmd

        logger.info("Auto-spawning WordCraft GUI: %s", " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
            start_new_session=True,
        )

        # Wait up to 6 seconds for control port to open
        deadline = time.time() + 6.0
        while time.time() < deadline:
            if WordCraftClient.is_desktop_reachable(addr):
                logger.info("WordCraft desktop control address %s is ready.", addr)
                time.sleep(0.3)
                return proc
            time.sleep(0.2)

        raise WordCraftUnreachableError(
            f"WordCraft desktop failed to open control address {addr} within timeout.\n"
            f"Please manually start WordCraft with:\n"
            f"    wordcraft --control {port}"
        )

    def _build_commands_from_ir(
        self,
        doc_ir: DocumentIR,
        strategy: FormattingStrategy | None = None,
    ) -> list[dict[str, Any]]:
        """Translates structured DocumentIR into semantic WordCraft batch commands."""
        cmds: list[dict[str, Any]] = []
        policy = self.config.antislop

        # 1. Page Margins (Anti-Slop standard: 72pt / 1.0 inch)
        margin_pt = max(36.0, min(108.0, float(doc_ir.margin_inches) * 72.0))
        cmds.append({
            "command": "layout.margins",
            "params": {
                "top": margin_pt,
                "bottom": margin_pt,
                "left": margin_pt,
                "right": margin_pt,
            },
        })
        cmds.append({
            "command": "layout.orientation",
            "params": {"value": "portrait"},
        })

        # 2. Configure Typography Styles per Anti-Slop Editorial Design
        display_font = policy.font_display
        body_font = policy.font_body
        accent = getattr(strategy, "accent_color", "1E3A8A") if strategy else "1E3A8A"

        cmds.append({
            "command": "styles.modify",
            "params": {
                "style": "Normal",
                "chr": {"font": body_font, "size": 11.0, "color": "1E293B"},
                "para": {"spaceBefore": 0.0, "spaceAfter": 6.0, "lineSpacing": {"rule": "multiple", "value": 1.2}},
            },
        })
        cmds.append({
            "command": "styles.modify",
            "params": {
                "style": "Heading1",
                "chr": {"font": display_font, "size": 18.0, "bold": True, "color": accent},
                "para": {"spaceBefore": 14.0, "spaceAfter": 4.0, "keepNext": True},
            },
        })
        cmds.append({
            "command": "styles.modify",
            "params": {
                "style": "Heading2",
                "chr": {"font": display_font, "size": 14.0, "bold": True, "color": "334155"},
                "para": {"spaceBefore": 10.0, "spaceAfter": 3.0, "keepNext": True},
            },
        })

        # 3. Header & Footer Configuration (discreet metadata & page numbering)
        if doc_ir.header_text:
            cmds.append({
                "command": "insert.header",
                "params": {"text": doc_ir.header_text, "preset": "title"},
            })
        if doc_ir.include_page_numbers:
            cmds.append({
                "command": "insert.footer",
                "params": {"text": doc_ir.footer_text, "preset": "pageNumber"},
            })
        cmds.append({"command": "insert.closeHeader"})

        # 4. Document Title
        cmds.append({"command": "text.insert", "params": {"text": doc_ir.title}})
        cmds.append({"command": "caret.home", "params": {"extend": True}})
        cmds.append({"command": "format.bold"})
        cmds.append({"command": "format.size", "params": {"size": 22.0}})
        cmds.append({"command": "format.color", "params": {"color": accent}})
        cmds.append({"command": "para.alignCenter"})
        cmds.append({"command": "caret.docEnd"})
        cmds.append({"command": "text.newParagraph"})

        # 5. Document Subtitle & Tagline
        cmds.append({"command": "text.insert", "params": {"text": doc_ir.subtitle}})
        cmds.append({"command": "caret.home", "params": {"extend": True}})
        cmds.append({"command": "format.italic"})
        cmds.append({"command": "format.size", "params": {"size": 10.5}})
        cmds.append({"command": "format.color", "params": {"color": "64748B"}})
        cmds.append({"command": "para.alignCenter"})
        cmds.append({"command": "caret.docEnd"})
        cmds.append({"command": "text.newParagraph"})
        cmds.append({"command": "text.newParagraph"})

        # 6. Table of Contents
        if doc_ir.include_toc:
            cmds.append({
                "command": "references.toc",
                "params": {"levels": 2, "title": "Table of Contents", "pageNumbers": True, "hyperlinks": True},
            })
            cmds.append({"command": "caret.docEnd"})
            cmds.append({"command": "text.pageBreak"})

        # 7. Iterate over Sections and Content Blocks
        for sec_idx, sec in enumerate(doc_ir.sections):
            if sec_idx > 0 and (sec.title.lower().startswith("chapter ") or getattr(sec, "page_break_before", False)):
                cmds.append({"command": "text.pageBreak"})

            # Heading 1
            cmds.append({"command": "para.heading1"})
            cmds.append({"command": "text.insert", "params": {"text": sec.title}})
            cmds.append({"command": "text.newParagraph"})
            cmds.append({"command": "para.normal"})

            for block in sec.blocks:
                if isinstance(block, ParagraphBlock):
                    # Assemble inline runs
                    for run in block.runs:
                        cmds.append({"command": "text.insert", "params": {"text": run.text}})
                        if run.bold:
                            cmds.append({"command": "caret.home", "params": {"extend": True}})
                            cmds.append({"command": "format.bold"})
                            cmds.append({"command": "caret.docEnd"})
                        if run.italic:
                            cmds.append({"command": "caret.home", "params": {"extend": True}})
                            cmds.append({"command": "format.italic"})
                            cmds.append({"command": "caret.docEnd"})
                    cmds.append({"command": "para.spacing", "params": {"before": 2.0, "after": 6.0}})
                    cmds.append({"command": "text.newParagraph"})

                elif isinstance(block, ListBlock):
                    for item in block.items:
                        cmds.append({"command": "text.insert", "params": {"text": item}})
                        if block.ordered:
                            cmds.append({"command": "para.numbering", "params": {"kind": "decimal"}})
                        else:
                            cmds.append({"command": "para.bullets", "params": {"kind": "bullet"}})
                        cmds.append({"command": "text.newParagraph"})
                    cmds.append({"command": "para.normal"})

                elif isinstance(block, CalloutBlock):
                    # Signature Element Callout Box
                    cmds.append({"command": "text.insert", "params": {"text": f"[{block.title.upper()}]\n{block.content}"}})
                    cmds.append({"command": "caret.home", "params": {"extend": True}})
                    cmds.append({"command": "format.italic"})
                    cmds.append({"command": "format.color", "params": {"color": "0F172A"}})
                    cmds.append({"command": "para.borders", "params": {"left": {"style": "thick", "width": 3.0, "color": accent}}})
                    cmds.append({"command": "para.spacing", "params": {"before": 8.0, "after": 8.0}})
                    cmds.append({"command": "caret.docEnd"})
                    cmds.append({"command": "text.newParagraph"})
                    cmds.append({"command": "para.normal"})

                elif isinstance(block, TableBlock):
                    # Anti-Slop Table with Header Formatting and Horizontal Rules
                    all_rows = [block.headers] + block.rows if block.headers else block.rows
                    rows_cnt = len(all_rows)
                    cols_cnt = max(len(r) for r in all_rows) if rows_cnt > 0 else 0

                    if rows_cnt > 0 and cols_cnt > 0:
                        cmds.append({
                            "command": "insert.table",
                            "params": {"rows": rows_cnt, "cols": cols_cnt},
                        })
                        for r_idx, row in enumerate(all_rows):
                            for c_idx, cell in enumerate(row):
                                cell_text = str(cell).strip()
                                cmds.append({"command": "text.insert", "params": {"text": cell_text}})
                                if r_idx == 0:
                                    cmds.append({"command": "caret.home", "params": {"extend": True}})
                                    cmds.append({"command": "format.bold"})
                                    cmds.append({"command": "format.color", "params": {"color": accent}})
                                    cmds.append({"command": "caret.docEnd"})
                                if not (r_idx == rows_cnt - 1 and c_idx == len(row) - 1):
                                    cmds.append({"command": "text.tab"})

                        cmds.append({"command": "caret.docEnd"})
                        if block.caption:
                            cmds.append({"command": "text.insert", "params": {"text": f"Table: {block.caption}"}})
                            cmds.append({"command": "caret.home", "params": {"extend": True}})
                            cmds.append({"command": "format.italic"})
                            cmds.append({"command": "format.size", "params": {"size": 9.5}})
                            cmds.append({"command": "format.color", "params": {"color": "64748B"}})
                            cmds.append({"command": "caret.docEnd"})
                        cmds.append({"command": "text.newParagraph"})

                elif isinstance(block, PageBreakBlock):
                    cmds.append({"command": "text.pageBreak"})

            cmds.append({"command": "para.spacing", "params": {"before": 4.0, "after": 8.0}})

        # 8. References Section
        if doc_ir.references:
            cmds.append({"command": "para.heading1"})
            cmds.append({"command": "text.insert", "params": {"text": "References & Literature Cited"}})
            cmds.append({"command": "text.newParagraph"})
            cmds.append({"command": "para.normal"})
            for ref in doc_ir.references:
                cmds.append({"command": "text.insert", "params": {"text": f"• {ref.title}: {ref.url}"}})
                cmds.append({"command": "text.newParagraph"})

        # 9. Update Table of Contents
        if doc_ir.include_toc:
            cmds.append({"command": "references.updateToc"})

        return cmds

    def compose_from_ir(
        self,
        doc_ir: DocumentIR,
        strategy: FormattingStrategy | None = None,
        output_filename: str | None = None,
        visible: bool | None = None,
        export_pdf: bool = False,
    ) -> WordCraftResult:
        """Composes a document directly from typed DocumentIR using WordCraft MCP."""
        start_time = time.time()
        is_visible = (self.config.mode == "desktop") if visible is None else visible

        # Generate output paths
        if output_filename is None:
            clean_title = "".join(c for c in doc_ir.title if c.isalnum() or c in (" ", "_", "-")).rstrip()
            clean_title = clean_title.replace(" ", "_")[:35]
            candidate = f"{clean_title}.docx"
            candidate_path = self.output_dir / candidate
            counter = 2
            while candidate_path.exists():
                candidate = f"{clean_title}_{counter}.docx"
                candidate_path = self.output_dir / candidate
                counter += 1
            output_filename = candidate

        out_docx = (self.output_dir / output_filename).resolve()
        out_pdf = out_docx.with_suffix(".pdf")
        preview_png = self.output_dir / f"{out_docx.stem}_page1.png"

        # Generate mandatory per-document DOC.md source of truth
        raw_sections = [{"title": s.title} for s in doc_ir.sections]
        doc_md_path = self.config.antislop.generate_doc_md(
            title=doc_ir.title,
            topic=doc_ir.topic,
            genre=doc_ir.genre,
            output_dir=self.output_dir,
            signature_element=doc_ir.signature_element,
            sections=raw_sections,
        )

        # Prepare WordCraft Client
        client = WordCraftClient(self.config)

        # Ensure GUI is running if in desktop mode
        if is_visible:
            self._ensure_gui_running()

        with client:
            client.start(force_desktop=is_visible)

            # Step 1: Create Blank Document
            client.new_document(template="blank")

            # Step 2: Translate IR to WordCraft Commands
            commands = self._build_commands_from_ir(doc_ir, strategy=strategy)

            # Step 3: Execute Batch Commands
            if is_visible:
                # Paced chunking so user can observe construction live
                chunk_size = 6
                for i in range(0, len(commands), chunk_size):
                    chunk = commands[i : i + chunk_size]
                    client.batch(chunk, keep_going=True)
                    time.sleep(0.08)
            else:
                client.batch(commands, keep_going=True)

            # Step 4: Inspect Document AST
            doc_struct: dict[str, Any] = {}
            if self.config.auto_inspect:
                try:
                    doc_struct = client.inspect_document()
                except Exception as e:
                    logger.warning("Document inspection failed: %s", e)

            words_cnt = doc_struct.get("words", 0)
            pages_cnt = doc_struct.get("pages", 1)
            blocks_cnt = len(doc_struct.get("blocks", []))
            tables_cnt = sum(1 for b in doc_struct.get("blocks", []) if b.get("type") == "table")

            # Step 5: Visual Page Preview (render_page)
            preview_created = False
            try:
                png_bytes = client.render_page(page=1, scale=1.5)
                with open(preview_png, "wb") as f:
                    f.write(png_bytes)
                preview_created = True
            except Exception as e:
                logger.warning("Visual render_page preview failed: %s", e)

            # Step 6: Save Document to DOCX
            client.save_document(out_docx)

            # Step 7: Export to PDF if requested
            pdf_saved = False
            if export_pdf:
                try:
                    client.save_document(out_pdf)
                    if out_pdf.exists() and out_pdf.stat().st_size > 0:
                        pdf_saved = True
                except Exception as e:
                    logger.warning("PDF export step failed: %s", e)

        elapsed_ms = (time.time() - start_time) * 1000.0

        return WordCraftResult(
            docx_path=out_docx,
            pdf_path=out_pdf if pdf_saved else None,
            preview_image_path=preview_png if preview_created else None,
            doc_md_path=doc_md_path,
            words=words_cnt,
            pages=pages_cnt,
            blocks=blocks_cnt,
            tables_count=tables_cnt,
            inspection_data=doc_struct,
            visible_mode=is_visible,
            composition_duration_ms=elapsed_ms,
        )

    def compose(
        self,
        title: str,
        sections: list[dict[str, Any]],
        strategy: FormattingStrategy,
        output_filename: str | None = None,
        metadata: dict[str, Any] | None = None,
        visible: bool = False,
        export_pdf: bool = False,
    ) -> WordCraftResult:
        """Backwards-compatible composition entry point converting brief/sections to DocumentIR."""
        genre = (metadata or {}).get("archetype", "Technical Report")
        topic = title

        # Synthesize brief if not already provided
        brief = DocumentBrief.from_request(
            user_request=f"{genre} on {title}",
            archetype=genre,
            explicit_sections=[s.get("title", "") for s in sections if s.get("title")],
        )

        doc_ir = DocumentIR.from_brief_and_content(
            brief=brief,
            sections_data=sections,
            antislop=self.config.antislop,
        )

        return self.compose_from_ir(
            doc_ir=doc_ir,
            strategy=strategy,
            output_filename=output_filename,
            visible=visible,
            export_pdf=export_pdf,
        )
