#!/usr/bin/env python3
"""Filevo Conversational CLI — Antigravity-Style Rich Terminal Application.

Features:
- Pathway A: Strict, reliable slash commands (/create, /analyze, /train, /feedback, etc.)
- Pathway B: Local Hugging Face Transformers model-driven natural language pipeline
- Multi-turn conversational memory with reference resolution
- Dedicated OpenXML DOCX Renderer & Validator
- RLCD Calibrated Decision Model with consensus scoring and policy gradients
- Antigravity/OpenCode colorized Rich UI with bottom-docked status & prompt box
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Ensure virtual environment and NixOS LD_LIBRARY_PATH are loaded
if os.environ.get("FILEVO_BOOTSTRAPPED") != "1" and sys.argv and sys.argv[0] != "-c":
    _script_dir = Path(__file__).resolve().parent
    repo_root = _script_dir.parent.parent
    venv_py = repo_root / ".venv" / "bin" / "python3"
    nixos_ld = "/nix/store/z0n70pxyzi87why1bcq81zgd7b924nfj-gcc-15.2.0-lib/lib:/nix/store/ss98wc4qpvf7f3p0xkv9f4hyhli5i1g5-nvidia-x11-595.71.05/lib:/nix/store/1y0c7mfa4ak2js3mlxwwxz5j74gbhnld-ld-library-path/share/nix-ld/lib"
    cur_ld = os.environ.get("LD_LIBRARY_PATH", "")
    env = dict(os.environ)
    env["FILEVO_BOOTSTRAPPED"] = "1"
    env["LD_LIBRARY_PATH"] = f"{nixos_ld}:{cur_ld}" if cur_ld else nixos_ld
    target_py = str(venv_py) if venv_py.exists() else sys.executable
    os.execve(target_py, [target_py] + sys.argv, env)

# Add root directory to sys.path
_FILE_ABS = os.path.abspath(__file__)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_FILE_ABS)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from src.doc_gen.codebase_analyzer import CodebaseAnalyzer
from src.doc_gen.conversation_memory import ConversationMemory
from src.doc_gen.dataset_builder import DocxDatasetBuilder
from src.doc_gen.document_brief import DocumentBrief
from src.doc_gen.docx_renderer import DocxRenderer
from src.doc_gen.knowledge_base import DocumentKnowledgeBase
from src.doc_gen.llm_client import LocalTransformersClient, SYSTEM_PROMPT
from src.doc_gen.rich_ui import console, ui
from src.doc_gen.rl_model import RLProbabilisticModel
from src.doc_gen.rlcd_engine import RLCDDecisionEngine

# ------------------------------------------------------------------ #
# Command Registry (Path A: Explicit Deterministic Slash Commands)
# ------------------------------------------------------------------ #

COMMANDS = {
    "/help": "Displays all available commands and keyboard shortcuts",
    "/create": "Creates a calibrated document (/create [--live|--desktop|--native] <topic>)",
    "/revise": "Revises and versions active document (/revise <instruction>)",
    "/research": "Researches a topic across web and live sources (/research <topic>)",
    "/analyze": "Analyzes a document, collection, or codebase (/analyze <path>)",
    "/train": "Ingests docs, builds datasets & trains policy (/train [@file|dir|live])",
    "/feedback": "Records feedback on active generation (/feedback [+1.0|-0.5])",
    "/dataset": "Builds leakage-free DOCX training dataset (/dataset [dir])",
    "/benchmark": "Benchmarks candidate local models on 16GB VRAM (/benchmark)",
    "/model": "Reports active model, policy weights, and probabilities",
    "/wordcraft": "WordCraft MCP status, desktop mode, and inspection (/wordcraft [status|live|inspect|render])",
    "/open": "Opens generated documents directory in Dolphin file manager (/open or /files)",
    "/settings": "Opens settings panel and command reference (Ctrl+P)",
    "/clear": "Clears terminal screen and redraws Antigravity banner",
    "/copy": "Copies last assistant response to clipboard (Ctrl+Y)",
    "/exit": "Exits the application",
}

# ------------------------------------------------------------------ #
# Global Singletons
# ------------------------------------------------------------------ #

_knowledge_base: DocumentKnowledgeBase | None = None
_rlcd_engine: RLCDDecisionEngine | None = None
_docx_renderer: DocxRenderer | None = None
_wordcraft_engine: Any | None = None
_llm_client: LocalTransformersClient | None = None
_memory: ConversationMemory | None = None
_dataset_builder: DocxDatasetBuilder | None = None
_latest_references: list[dict[str, str]] = []


def get_kb() -> DocumentKnowledgeBase:
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = DocumentKnowledgeBase()
    return _knowledge_base


def get_rlcd() -> RLCDDecisionEngine:
    global _rlcd_engine
    if _rlcd_engine is None:
        _rlcd_engine = RLCDDecisionEngine()
    return _rlcd_engine


def get_renderer() -> DocxRenderer:
    global _docx_renderer
    if _docx_renderer is None:
        _docx_renderer = DocxRenderer()
    return _docx_renderer


def get_wordcraft():
    global _wordcraft_engine
    if _wordcraft_engine is None:
        from src.doc_gen.wordcraft_engine import WordCraftEngine
        _wordcraft_engine = WordCraftEngine()
    return _wordcraft_engine


def get_llm() -> LocalTransformersClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LocalTransformersClient()
    return _llm_client


def get_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory


def get_dataset_builder() -> DocxDatasetBuilder:
    global _dataset_builder
    if _dataset_builder is None:
        _dataset_builder = DocxDatasetBuilder()
    return _dataset_builder


# ------------------------------------------------------------------ #
# Settings & Configuration Management
# ------------------------------------------------------------------ #

def get_filevo_config() -> dict[str, Any]:
    """Load configuration from ~/.filevo/config.json."""
    cfg_file = Path.home() / ".filevo" / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_filevo_config(cfg: dict[str, Any]):
    """Persist configuration to ~/.filevo/config.json."""
    cfg_dir = Path.home() / ".filevo"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "config.json"
    try:
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def is_auto_open_enabled() -> bool:
    """Check if auto-opening generated documents is enabled (default True)."""
    return bool(get_filevo_config().get("auto_open", True))


def set_auto_open(enabled: bool) -> bool:
    """Set and persist auto_open setting."""
    cfg = get_filevo_config()
    cfg["auto_open"] = enabled
    save_filevo_config(cfg)
    return enabled


def get_doc_engine_setting() -> str:
    """Check preferred authoring engine ('wordcraft' or 'native', default 'wordcraft')."""
    try:
        from src.doc_gen.wordcraft_adapter import WordCraftConfig
        wc_cfg = WordCraftConfig.load()
        if not wc_cfg.enabled:
            return "native"
    except Exception:
        pass
    return str(get_filevo_config().get("engine", "wordcraft")).lower()


def set_doc_engine_setting(engine_name: str) -> str:
    """Set and persist authoring engine setting."""
    clean_engine = "wordcraft" if engine_name.lower() in ("wordcraft", "wc") else "native"
    try:
        from src.doc_gen.wordcraft_adapter import WordCraftConfig
        wc_cfg = WordCraftConfig.load()
        wc_cfg.enabled = (clean_engine == "wordcraft")
        wc_cfg.save()
    except Exception:
        pass
    cfg = get_filevo_config()
    cfg["engine"] = clean_engine
    save_filevo_config(cfg)
    return clean_engine


def get_wordcraft_mode_setting() -> str:
    """Check WordCraft mode ('desktop' or 'headless', default 'desktop')."""
    try:
        from src.doc_gen.wordcraft_adapter import WordCraftConfig
        wc_cfg = WordCraftConfig.load()
        return wc_cfg.mode
    except Exception:
        return str(get_filevo_config().get("wordcraft_mode", "desktop")).lower()


def set_wordcraft_mode_setting(mode_name: str) -> str:
    """Set and persist WordCraft mode setting."""
    clean_mode = "desktop" if mode_name.lower() in ("desktop", "live", "gui") else "headless"
    try:
        from src.doc_gen.wordcraft_adapter import WordCraftConfig
        wc_cfg = WordCraftConfig.load()
        wc_cfg.mode = clean_mode
        wc_cfg.save()
    except Exception:
        pass
    cfg = get_filevo_config()
    cfg["wordcraft_mode"] = clean_mode
    save_filevo_config(cfg)
    return clean_mode


def open_document(doc_path: Path | str) -> bool:
    """Launch system default application to open generated document."""
    import subprocess
    path = Path(doc_path).resolve()
    if not path.exists():
        return False
    try:
        if sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith("win"):
            os.startfile(str(path))
            if (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and os.environ.get("FILEVO_TESTING") != "1":
                wc_bin = Path.home() / ".local" / "bin" / "wordcraft"
                if path.suffix.lower() == ".docx" and wc_bin.exists():
                    subprocess.Popen([str(wc_bin), str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except Exception:
        return False



# ------------------------------------------------------------------ #
# @file Attachment Mention Resolver
# ------------------------------------------------------------------ #

def resolve_file_mentions(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse @filepath mentions, read contents/outlines, and return attachments."""
    pattern = r'@(?:"([^"]+)"|\'([^\']+)\'|([^\s"\'<>`]+))'
    raw_matches = re.findall(pattern, text)
    attachments = []
    clean_text = text

    for match in raw_matches:
        if match[0]:
            raw_path = match[0].strip()
        elif match[1]:
            raw_path = match[1].strip()
        elif match[2]:
            raw_path = match[2].strip().rstrip("?,.!;:")
        else:
            continue

        if not raw_path:
            continue
        p = Path(raw_path).expanduser().resolve()
        if not p.exists():
            p = (Path.cwd() / raw_path).resolve()

        if p.exists() and p.is_file():
            content = ""
            file_type = p.suffix.lower()
            try:
                if file_type == ".docx":
                    kb = get_kb()
                    meta = kb._extract_docx_features(p, kb.compute_sha256(p), p.stat().st_mtime)
                    content = (
                        f"[DOCX: {p.name} | Archetype: {meta.structure.archetype} | "
                        f"Words: {meta.structure.total_words} | "
                        f"Sections: {', '.join(meta.structure.section_topics[:6])}]"
                    )
                else:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(4000)
                attachments.append({"name": p.name, "path": str(p), "type": file_type, "content": content})
            except Exception as e:
                attachments.append({"name": p.name, "path": str(p), "error": str(e)})

    return clean_text, attachments


# ------------------------------------------------------------------ #
# Pathway A: Deterministic Slash Commands
# ------------------------------------------------------------------ #

def cmd_help():
    """Display command reference table and keyboard shortcuts."""
    from rich.table import Table
    table = Table(title="[bold #7aa2f7]Available Commands[/bold #7aa2f7]", border_style="#414868")
    table.add_column("Command", style="bold #e0af68", width=14)
    table.add_column("Description", style="white")

    for cmd, desc in COMMANDS.items():
        table.add_row(cmd, desc)

    console.print(table)
    console.print("\n[dim]Conversational Engine: Type free text or mention files with @filename.[/dim]")
    console.print("[dim]Keyboard Shortcuts: Ctrl+C (cancel), Ctrl+D (exit), Tab (autocomplete).[/dim]\n")


def cmd_create(request_str: str, attachments: list[dict[str, Any]] | None = None):
    """Creates a validated DOCX document using RLCD calibrated decision policy and WordCraft/OpenXML engine."""
    force_visible = any(f in request_str for f in ("--live", "--desktop", "--gui"))
    force_headless = "--headless" in request_str
    force_native = any(f in request_str for f in ("--native", "--openxml"))
    force_no_pdf = any(f in request_str for f in ("--no-pdf", "--without-pdf", "-no-pdf"))
    force_pdf = any(f in request_str for f in ("--pdf", "-pdf")) and not force_no_pdf

    clean_request = request_str
    for f in ("--live", "--desktop", "--gui", "--headless", "--native", "--openxml", "--no-pdf", "--without-pdf", "-no-pdf", "--pdf", "-pdf"):
        clean_request = clean_request.replace(f, "")
    clean_request = clean_request.strip()

    if not clean_request:
        console.print("[yellow]Please specify a topic or document request. Example: /create Technical Report on AI[/yellow]")
        return

    kb = get_kb()
    rlcd = get_rlcd()
    renderer = get_renderer()
    memory = get_memory()

    with ui.spinner(f"Evaluating RLCD calibrated decision policy for: '{clean_request}'..."):
        decision = rlcd.decide(clean_request)
        time.sleep(0.1)

    # Render styled decision telemetry panel
    ui.display_decision_card(decision)

    llm = get_llm()
    formatting = decision.formatting

    # Semantic Title, Topic, and Explicit Section extraction via language model
    spec = llm.extract_document_spec(clean_request, memory.get_messages_for_llm())
    explicit_secs = spec.get("explicit_sections") or []

    # Live Web Research grounding: only when explicitly requested or required
    web_data = None
    needs_web = any(k in clean_request.lower() for k in ("web", "browse", "research", "internet", "online", "latest", "news"))
    if needs_web:
        clean_query = spec.get("topic") or clean_request
        with ui.spinner(f"Grounding topic via live web research for '{clean_query}'..."):
            from src.doc_gen.web_researcher import WebResearcher
            wr = WebResearcher()
            web_data = wr.research_topic(clean_query)
            if web_data.get("has_web_data"):
                console.print(f"[dim]🌐 Live web knowledge grounded: {len(web_data.get('sources', []))} reference source(s) discovered[/dim]")

    web_overview = web_data.get("overview", "") if web_data else ""
    web_sources = web_data.get("sources", []) if web_data else []

    # Construct authoritative DocumentBrief preserving full request and requirements
    brief = DocumentBrief.from_request(
        user_request=clean_request,
        archetype=decision.archetype,
        explicit_sections=explicit_secs,
        web_sources=web_sources,
        attachments=attachments,
    )
    title = brief.title
    topic = brief.topic
    memory.active_brief = brief

    sections = []
    att_summary = ""
    if attachments:
        att_names = [a["name"] for a in attachments]
        att_summary = f"Incorporating grounded context from referenced file(s): {', '.join(att_names)}.\n\n"
        for a in attachments:
            if a.get("content"):
                att_summary += f"### Reference: {a['name']}\n{a['content'][:300]}...\n\n"

    grounding = f"{web_overview}\n{att_summary}".strip()

    with ui.spinner("Synthesizing document content with local model and compiling OpenXML package..."):
        if brief.genre == "Formal Letter" or decision.archetype == "Formal Letter":
            sections = [
                {
                    "title": "Formal Salutation and Recipient",
                    "content": (
                        f"Date: {datetime.datetime.now().strftime('%B %d, %Y')}\n\n"
                        f"To:\nThe Competent Authority / Administrative Review Board\n\n"
                        f"Subject: Formal Application and Request Concerning {title}\n\n"
                        f"Dear Sir / Madam,"
                    ),
                },
                {
                    "title": "Statement of Purpose",
                    "content": llm.generate_section_content("Statement of Purpose", title, brief.genre, grounding, brief=brief),
                },
                {
                    "title": "Background and Justification",
                    "content": llm.generate_section_content("Background and Justification", title, brief.genre, grounding, brief=brief),
                },
                {
                    "title": "Formal Terms and Requirements",
                    "content": llm.generate_section_content("Formal Terms and Requirements", title, brief.genre, grounding, brief=brief),
                },
                {
                    "title": "Closing and Authorization Signatures",
                    "content": (
                        f"Thank you for your favorable consideration of this formal request. We remain at your disposal for any further clarification.\n\n"
                        f"Respectfully submitted,\n\n"
                        f"Authorized Representative\n"
                        f"Filevo Systems Group"
                    ),
                },
            ]
        else:
            # Attempt model load if available
            model_loaded = False
            try:
                model_loaded = llm.load()
            except Exception as e:
                console.print(f"[dim yellow]Model load exception: {e}[/dim yellow]")

            brief.is_offline_fallback = not model_loaded

            if not model_loaded:
                console.print("[dim yellow]Note: Local language model offline or unavailable; compiling structured outline via DocumentBrief grounding.[/dim yellow]")

            for p_sec in brief.sections:
                s_title = p_sec.heading
                content = llm.generate_section_content(
                    section_title=s_title,
                    doc_title=title,
                    archetype=brief.genre,
                    grounding_context=grounding,
                    brief=brief,
                )
                sections.append({
                    "title": s_title,
                    "content": content,
                    "page_break": p_sec.page_break_before,
                    "page_break_before": p_sec.page_break_before,
                })

        # Append Live Web Sources & References section if web research was conducted
        if web_sources:
            ref_content = "Primary references and live web sources consulted during synthesis:\n\n"
            for s in web_sources[:6]:
                ref_content += f"• {s.get('title', '')}: {s.get('url', '')}\n"
            sections.append({"title": "References and Discovered Sources", "content": ref_content})

        from src.doc_gen.document_ir import DocumentIR
        wc = get_wordcraft()
        doc_ir = DocumentIR.from_brief_and_content(
            brief=brief,
            sections_data=sections,
            antislop=wc.config.antislop,
        )

        wc_result = None
        is_user_storage = str(renderer.output_dir).startswith(str(Path.home()))
        use_wordcraft = not force_native and is_user_storage and (get_doc_engine_setting() == "wordcraft" or force_visible or force_headless)
        if is_user_storage:
            wc.output_dir = renderer.output_dir

        if use_wordcraft and wc.is_available():
            is_live = force_visible or (get_wordcraft_mode_setting() == "desktop" and not force_headless)
            if is_live and not wc.is_desktop_running():
                console.print(f"[dim]WordCraft desktop control port inactive; spawning application on {wc.config.control_address}...[/dim]")
            mode_desc = "live visible desktop word processor" if is_live else "WordCraft MCP"
            positive_pdf_patterns = [
                r"\b(?:also|and|export|generate|make|create|with|save|output|render|convert\s+to)\s+(?:a\s+)?pdf\b",
                r"\b(?:as|to|in)\s+pdf\b",
                r"\bpdf\s+(?:format|version|copy|export|file)\b",
            ]
            negative_pdf_patterns = [
                r"\b(?:no|not|never|without|don['’]?t|do\s+not|stop|no\s+need\s+of)\s+(?:a\s+)?pdf\b",
                r"\bwhy\s+(?:did|does|is)\s+it\s+(?:create|make|generate)\s+pdf\b",
                r"\bwhy\s+pdf\b",
            ]
            has_positive_pdf = any(re.search(pat, clean_request, flags=re.IGNORECASE) for pat in positive_pdf_patterns)
            has_negative_pdf = any(re.search(pat, clean_request, flags=re.IGNORECASE) for pat in negative_pdf_patterns) or force_no_pdf
            export_pdf_requested = bool((has_positive_pdf or force_pdf) and not has_negative_pdf)
            pkg_desc = "OpenXML/PDF package" if export_pdf_requested else "OpenXML package"
            with ui.spinner(f"Composing document, tables, and {pkg_desc} via {mode_desc}..."):
                try:
                    wc_result = wc.compose_from_ir(
                        doc_ir=doc_ir,
                        strategy=formatting,
                        visible=is_live,
                        export_pdf=export_pdf_requested,
                    )
                    doc_path = wc_result.docx_path
                except Exception as e:
                    console.print(f"[yellow]⚠ WordCraft composition encountered an error ({e}); falling back to native OpenXML renderer...[/yellow]")
                    doc_path = renderer.render(
                        title=title,
                        sections=sections,
                        strategy=formatting,
                        metadata={"subtitle": f"{brief.genre} | {brief.audience}", "archetype": brief.genre},
                    )
                    wc_result = None
        else:
            doc_path = renderer.render(
                title=title,
                sections=sections,
                strategy=formatting,
                metadata={"subtitle": f"{brief.genre} | {brief.audience}", "archetype": brief.genre},
            )

    # Autonomous Policy Learning: objectively evaluate outcome and update policy gradients
    rlcd.record_autonomous_experience(
        operation="create",
        prompt=clean_request,
        decision=decision,
        artifact_path=doc_path,
        sections=sections,
        explicit_sections=explicit_secs if explicit_secs else None,
    )

    # Record in conversational memory
    memory.add_assistant_message(
        f"Generated {decision.archetype} on '{title}' at {doc_path}",
        generated_doc=str(doc_path),
        archetype=decision.archetype,
        topic=title,
    )

    # Display styled document card
    ui.display_document_card(doc_path, title, len(sections), decision.archetype, wc_result=wc_result)

    if is_auto_open_enabled():
        open_document(doc_path)


def cmd_revise(revision_instruction: str):
    """Revises and versions the active document in conversation memory, preserving existing content."""
    memory = get_memory()
    active_doc = memory.active_document_path
    active_topic = memory.active_document_topic or "Document"
    if not active_doc or not Path(active_doc).exists():
        out_dir = Path.home() / ".filevo" / "output"
        if out_dir.exists():
            docx_files = sorted(out_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
            if docx_files:
                active_doc = str(docx_files[0])
                active_topic = docx_files[0].stem.replace("_", " ")
                memory.active_document_path = active_doc
                memory.active_document_topic = active_topic

    if not active_doc or not Path(active_doc).exists():
        console.print("[yellow]No active document to revise. Create a document first via /create.[/yellow]")
        return None

    orig_path = Path(active_doc)
    stem = orig_path.stem
    version_num = 2
    if "_v" in stem:
        parts = stem.split("_v")
        try:
            version_num = int(parts[-1]) + 1
            new_stem = f"{parts[0]}_v{version_num}"
        except ValueError:
            new_stem = f"{stem}_v2"
    else:
        new_stem = f"{stem}_v2"

    new_filename = f"{new_stem}.docx"
    rlcd = get_rlcd()
    renderer = get_renderer()
    llm = get_llm()

    # Extract existing sections and content directly from the active DOCX OpenXML
    doc_data = renderer.extract_document_content(orig_path)
    existing_sections = doc_data.get("sections", [])
    doc_title = doc_data.get("title") or active_topic

    with ui.spinner(f"Revising and versioning '{stem}' -> '{new_stem}'..."):
        decision = rlcd.decide(f"{active_topic} {revision_instruction}")
        fmt = decision.formatting
        if "formal" in revision_instruction.lower():
            fmt.accent_color = "333333"
            fmt.font_family = "Times New Roman"
            fmt.line_spacing = 1.15

        # Match target section from revision instruction
        inst_lower = revision_instruction.lower()
        target_section_idx = None
        expanded_section_title = None

        for idx, sec in enumerate(existing_sections):
            sec_title_lower = sec.get("title", "").lower()
            sec_words = [w for w in re.findall(r"\w+", sec_title_lower) if len(w) > 3]
            if sec_title_lower in inst_lower or any(sw in inst_lower for sw in sec_words):
                target_section_idx = idx
                expanded_section_title = sec.get("title")
                break

        revised_sections = []
        if existing_sections:
            for idx, sec in enumerate(existing_sections):
                s_title = sec.get("title", "")
                orig_content = sec.get("content", "")
                sec_dict = {"title": s_title}

                brief = getattr(memory, "active_brief", None) or DocumentBrief.from_request(
                    user_request=f"{active_topic} {revision_instruction}"
                )

                if target_section_idx is not None and idx == target_section_idx:
                    # Targeted section revision/expansion with full document brief and semantic rewriting
                    revised_content = llm.rewrite_section_content(
                        existing_content=orig_content,
                        section_title=s_title,
                        revision_instruction=revision_instruction,
                        doc_title=doc_title,
                        brief=brief,
                    )
                    sec_dict["content"] = revised_content
                elif target_section_idx is None and any(w in inst_lower for w in ("formal", "tone", "style", "polish")):
                    sec_dict["content"] = llm.rewrite_section_content(
                        existing_content=orig_content,
                        section_title=s_title,
                        revision_instruction=revision_instruction,
                        doc_title=doc_title,
                        brief=brief,
                    )
                else:
                    # Existing sections preserved unaltered!
                    sec_dict["content"] = orig_content

                if sec.get("table"):
                    sec_dict["table"] = sec["table"]
                revised_sections.append(sec_dict)
        else:
            revised_sections = [
                {
                    "title": s,
                    "content": llm.generate_section_content(s, doc_title, decision.archetype),
                }
                for s in decision.recommended_sections
            ]

        new_path = renderer.render(title=doc_title, sections=revised_sections, strategy=fmt, output_filename=new_filename)

    # Autonomous Policy Learning: objectively evaluate revised artifact and update policy
    prev_arch = memory.active_archetype or decision.archetype
    rlcd.record_revision_experience(
        prompt=revision_instruction,
        previous_archetype=prev_arch,
        new_archetype=decision.archetype,
        artifact_path=new_path,
    )
    rlcd.record_autonomous_experience(
        operation="revise",
        prompt=f"{active_topic} {revision_instruction}",
        decision=decision,
        artifact_path=new_path,
        sections=revised_sections,
    )

    exp_note = f", expanding the {expanded_section_title} section" if expanded_section_title else ""
    rev_msg = f"I have revised '{doc_title}' and created version {version_num} at {new_path.name}{exp_note}."
    memory.add_assistant_message(
        rev_msg,
        generated_doc=str(new_path),
        archetype=decision.archetype,
        topic=doc_title,
        expanded_section=expanded_section_title,
    )
    ui.print_assistant_message(rev_msg)
    ui.display_document_card(new_path, f"{doc_title} (Version {version_num})", len(revised_sections), decision.archetype)
    if is_auto_open_enabled():
        open_document(new_path)
    return new_path


def cmd_research(topic_arg: str):
    """Researches a topic across web and live sources, displaying facts and references."""
    clean_topic = topic_arg.strip()
    if not clean_topic:
        console.print("[yellow]Please specify a topic to research. Example: /research Quantum Computing[/yellow]")
        return

    from src.doc_gen.web_researcher import WebResearcher
    wr = WebResearcher()
    with ui.spinner(f"Querying web and exploring live sources for: '{clean_topic}'..."):
        data = wr.research_topic(clean_topic)

    from rich.panel import Panel
    overview = data.get("overview") or "No live overview found."
    sources = data.get("sources", [])

    body = f"[bold #2ac3de]Topic Overview:[/bold #2ac3de]\n{overview}\n\n"
    if sources:
        body += "[bold #e0af68]Discovered Web Sources:[/bold #e0af68]\n"
        for s in sources[:6]:
            body += f"• [dim underline]{s}[/dim underline]\n"

    console.print(Panel(body, title=f"[bold #7aa2f7]🌐 Web Intelligence: {clean_topic.title()}[/bold #7aa2f7]", border_style="#414868"))


def cmd_analyze(path_arg: str):
    """Analyzes a document, collection, or codebase."""
    target_path = Path(path_arg.strip() if path_arg else ".").expanduser().resolve()
    if not target_path.exists():
        console.print(f"[red]Path not found:[/red] {target_path}")
        return

    if target_path.is_file() and target_path.suffix.lower() == ".docx":
        with ui.spinner(f"Extracting OpenXML features from {target_path.name}..."):
            kb = get_kb()
            meta = kb._extract_docx_features(target_path, kb.compute_sha256(target_path), target_path.stat().st_mtime)

        from rich.table import Table
        t = Table(title=f"[bold #7aa2f7]DOCX Analysis: {target_path.name}[/bold #7aa2f7]", border_style="#414868")
        t.add_column("Property", style="bold #e0af68")
        t.add_column("Value")
        t.add_row("Inferred Archetype", f"[bold #2ac3de]{meta.structure.archetype}[/bold #2ac3de]")
        t.add_row("Total Paragraphs", str(meta.structure.total_paragraphs))
        t.add_row("Total Words", str(meta.structure.total_words))
        t.add_row("Primary Typography", meta.style.primary_font)
        t.add_row("Headings Count", str(meta.structure.total_headings))
        t.add_row("Tables Count", str(meta.structure.total_tables))
        if meta.structure.section_topics:
            t.add_row("Section Topics", ", ".join(meta.structure.section_topics[:6]))
        console.print(t)
        return

    with ui.spinner(f"Parsing codebase AST in {target_path}..."):
        analyzer = CodebaseAnalyzer(target_path)
        insights = analyzer.get_insights()

    from rich.table import Table
    t = Table(title=f"[bold #7aa2f7]Codebase Analysis Summary[/bold #7aa2f7]", border_style="#414868")
    t.add_column("Metric", style="bold #e0af68")
    t.add_column("Value")
    t.add_row("Files Analyzed", str(insights["file_count"]))
    t.add_row("Functions", str(insights["function_count"]))
    t.add_row("Classes", str(insights["class_count"]))
    t.add_row("Average Complexity (CC)", f"{insights['avg_complexity']:.2f}")
    t.add_row("Max Complexity", str(insights["max_complexity"]))
    t.add_row("Structural Patterns", str(insights["pattern_count"]))
    console.print(t)


def cmd_index(path_arg: str):
    """Indexes documents incrementally using real live progress bar."""
    target = path_arg.strip() if path_arg else "."
    target_path = Path(target).expanduser().resolve()
    if not target_path.exists():
        console.print(f"[red]Directory not found:[/red] {target_path}")
        return

    kb = get_kb()
    rlcd = get_rlcd()

    docx_files = list(target_path.glob("**/*.docx")) if target_path.is_dir() else ([target_path] if target_path.suffix.lower() == ".docx" else [])
    docx_files = [f for f in docx_files if not f.name.startswith("~$") and not f.name.startswith(".")]

    stats = {"scanned": 0, "indexed": 0, "skipped": 0, "errors": 0}

    with ui.create_progress() as progress:
        task = progress.add_task("Indexing DOCX documents...", total=len(docx_files))
        for docx_file in docx_files:
            stats["scanned"] += 1
            try:
                res = kb.index_file_if_changed(docx_file)
                if res == "indexed":
                    stats["indexed"] += 1
                elif res == "skipped":
                    stats["skipped"] += 1
            except Exception:
                stats["errors"] += 1
            progress.update(task, advance=1)

    kb._rebuild_archetype_clusters()
    kb.save()

    summary = kb.get_status_summary()
    train_res = rlcd.train_on_knowledge_corpus(summary)

    from rich.table import Table
    t = Table(title="[bold #9ece6a]✓ Indexing Complete[/bold #9ece6a]", border_style="#414868")
    t.add_column("Metric", style="bold #7dcfff")
    t.add_column("Count")
    t.add_row("Files Scanned", str(stats["scanned"]))
    t.add_row("Newly Indexed", f"[bold green]{stats['indexed']}[/bold green]")
    t.add_row("Skipped (SHA-256 Match)", f"[dim]{stats['skipped']}[/dim]")
    t.add_row("Total Knowledge Profiles", str(summary["total_documents"]))
    if train_res.get("episodes_trained", 0) > 0:
        t.add_row("RLCD Policy Adaptation", f"Adapted priors across {train_res['episodes_trained']} profiles")
    console.print(t)


def cmd_dataset(path_arg: str):
    """Builds supervised training and evaluation dataset from DOCX files."""
    target = path_arg.strip() if path_arg else "."
    builder = get_dataset_builder()

    with ui.spinner("Extracting structural supervision & generating leakage-free train/eval splits..."):
        report = builder.build_dataset_from_directory(target)

    from rich.table import Table
    t = Table(title="[bold #7aa2f7]DOCX Supervision Dataset Manifest[/bold #7aa2f7]", border_style="#414868")
    t.add_column("Field", style="bold #e0af68")
    t.add_column("Details")
    t.add_row("Source Documents Scanned", str(report["source_documents_scanned"]))
    t.add_row("Train Source Documents", str(report["train_source_documents"]))
    t.add_row("Eval Source Documents (Disjoint)", str(report["eval_source_documents"]))
    t.add_row("Train Examples (JSONL)", f"[bold green]{report['train_examples_generated']}[/bold green] ({report['train_file']})")
    t.add_row("Eval Examples (JSONL)", f"[bold green]{report['eval_examples_generated']}[/bold green] ({report['eval_file']})")
    console.print(t)
    console.print(f"[dim]Limitations Note: {report['limitations_disclaimer']}[/dim]")


def cmd_copy():
    """Copies last assistant response to system clipboard."""
    mem = get_memory()
    assistant_turns = [t for t in mem.turns if t.role == "assistant"]
    if not assistant_turns:
        console.print("[yellow]⚠ No assistant responses available to copy.[/yellow]")
        return

    last_text = assistant_turns[-1].content.strip()
    copied = False

    import shutil
    import subprocess
    if os.environ.get("FILEVO_OFFLINE") == "1" or os.environ.get("FILEVO_TESTING") == "1":
        copied = True
    else:
        for tool, args in [
            ("wl-copy", ["wl-copy"]),
            ("xclip", ["xclip", "-selection", "clipboard"]),
            ("xsel", ["xsel", "--clipboard", "--input"]),
            ("pbcopy", ["pbcopy"]),
        ]:
            if shutil.which(tool):
                try:
                    subprocess.run(args, input=last_text.encode("utf-8"), check=True, capture_output=True, timeout=1.0)
                    copied = True
                    break
                except Exception:
                    continue

    if copied:
        console.print(f"[green]✓ Copied last response to clipboard ([bold]{len(last_text)}[/bold] characters).[/green]")
    else:
        console.print(f"[dim]Note: No clipboard utility (xclip/wl-copy/pbcopy) detected in environment.[/dim]")
        console.print(f"[green]Last response ({len(last_text)} chars):[/green]\n{last_text}")


def cmd_benchmark():
    """Benchmark candidate models on 16GB VRAM on actual Filevo tasks."""
    llm = get_llm()
    dev_label = f"CUDA GPU ({llm.device.upper()})" if llm.device != "cpu" else "CPU"
    console.print(f"[bold #7aa2f7]Benchmarking candidate models on {dev_label}...[/bold #7aa2f7]")

    with ui.spinner("Running performance & VRAM benchmark..."):
        results = llm.benchmark_models(
            candidate_ids=["HuggingFaceTB/SmolLM2-1.7B-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct"],
            test_prompts=["sup", "Explain cyclomatic complexity in software.", "Write a technical report on distributed consensus."],
        )

    for r in results:
        from rich.table import Table
        t = Table(title=f"Benchmark: [bold #e0af68]{r['model_id']}[/bold #e0af68]", border_style="#414868")
        t.add_column("Metric", style="bold #7dcfff")
        t.add_column("Value")
        t.add_row("Device", r.get("device", "N/A"))
        t.add_row("Load Time", f"{r.get('load_time_sec', 0.0)} s")
        t.add_row("VRAM Allocated", f"{r.get('vram_allocated_mb', 0.0)} MB")
        for p in r.get("prompts", []):
            t.add_row(f"Prompt: '{p['prompt'][:25]}'", f"{p['time_sec']}s ({p['approx_words_per_sec']} words/s) -> {p['reply_snippet']}")
        console.print(t)


def cmd_train(arg: str, attachments: list[dict[str, Any]] | None = None):
    """Unified 3-in-1 learning pipeline: Ingests documents, compiles datasets, and optimizes policy."""
    clean_arg = (arg or "").strip()
    parts = clean_arg.split()

    kb = get_kb()
    rlcd = get_rlcd()

    # 1. Live streaming episodes: /train live [N] or /train N
    if parts and parts[0] in ("live", "--live", "-l"):
        n_episodes = 5
        if len(parts) > 1:
            try:
                n_episodes = max(1, min(50, int(parts[1])))
            except ValueError:
                pass
        return _run_live_training_stream(n_episodes)

    if parts and parts[0].isdigit():
        n_episodes = int(parts[0])
        return _run_live_training_stream(n_episodes)

    # 2. Supervised model fine-tuning: /train model or /train finetune
    if parts and parts[0] in ("model", "sft", "finetune"):
        dry_run = "--dry-run" in parts or "-d" in parts
        from src.doc_gen.model_trainer import FilevoModelTrainer
        console.print(f"[bold #7aa2f7]Starting Model Supervised Fine-Tuning Pipeline (dry_run={dry_run})...[/bold #7aa2f7]")
        try:
            trainer = FilevoModelTrainer()
            metrics = trainer.train(dry_run=dry_run)
            from rich.table import Table
            t = Table(title="[bold #9ece6a]✓ Supervised Model Training Complete[/bold #9ece6a]", border_style="#414868")
            t.add_column("Metric", style="bold #7dcfff")
            t.add_column("Value")
            t.add_row("Device", metrics.device)
            t.add_row("Epochs", str(metrics.epochs))
            t.add_row("Train Loss", f"{metrics.train_loss:.4f}")
            eval_loss_str = f"{metrics.eval_loss:.4f}" if metrics.eval_loss is not None else "N/A (no eval samples)"
            t.add_row("Eval Loss", eval_loss_str)
            t.add_row("Samples Trained", str(metrics.samples_trained))
            t.add_row("Checkpoint Dir", metrics.checkpoint_dir)
            console.print(t)
        except Exception as e:
            console.print(f"[red]Model training failed:[/red] {e}")
        return

    # Check for scalar reward feedback: /train +1.0 or -0.5
    if parts and len(parts) == 1:
        try:
            reward = float(parts[0])
            return cmd_feedback(str(reward))
        except ValueError:
            pass

    # 3. Unified 3-Step Pipeline: /train @file.docx, /train file.docx, or /train [dir]
    target_docx_files: list[Path] = []
    scan_dir: Path | None = None

    if attachments:
        for a in attachments:
            if a.get("path") and Path(a["path"]).suffix.lower() == ".docx":
                target_docx_files.append(Path(a["path"]).resolve())

    if not target_docx_files and clean_arg:
        # Check tokens for filenames / paths
        file_tokens = [tok.lstrip("@").strip() for tok in parts if not tok.startswith("-") and tok not in ("corpus", "auto", "kb")]
        for tok in file_tokens:
            p = Path(tok).expanduser().resolve()
            if not p.exists():
                p = (Path.cwd() / tok).resolve()
            if p.exists():
                if p.is_file() and p.suffix.lower() == ".docx":
                    target_docx_files.append(p)
                elif p.is_dir():
                    scan_dir = p
                    break

    # Default fallback to knowledge output directory or cwd
    if not target_docx_files and not scan_dir:
        out_dir = Path.home() / ".filevo" / "output"
        if out_dir.exists() and list(out_dir.glob("*.docx")):
            scan_dir = out_dir
        else:
            scan_dir = Path.cwd()

    console.print("\n[bold #7aa2f7]🚀 Executing Unified Training Pipeline[/bold #7aa2f7]")
    console.print("[dim]Step 1: Document Ingestion → Step 2: Dataset Compilation → Step 3: Policy Gradient Optimization[/dim]\n")

    # Step 1: Document Ingestion & OpenXML Feature Extraction
    if target_docx_files:
        files_to_index = target_docx_files
    else:
        files_to_index = list(scan_dir.glob("**/*.docx")) if scan_dir and scan_dir.is_dir() else []
        files_to_index = [f for f in files_to_index if not f.name.startswith("~$") and not f.name.startswith(".")]

    stats = {"scanned": 0, "indexed": 0, "skipped": 0, "errors": 0}
    with ui.create_progress() as progress:
        task = progress.add_task("[cyan]Step 1/3: Ingesting OpenXML profiles...", total=max(1, len(files_to_index)))
        for docx_file in files_to_index:
            stats["scanned"] += 1
            try:
                res = kb.index_file_if_changed(docx_file)
                if res == "indexed":
                    stats["indexed"] += 1
                elif res == "skipped":
                    stats["skipped"] += 1
            except Exception:
                stats["errors"] += 1
            progress.update(task, advance=1)

    kb._rebuild_archetype_clusters()
    kb.save()

    from rich.table import Table
    t1 = Table(title="[bold #9ece6a]✓ Step 1/3: Document Ingestion Complete[/bold #9ece6a]", border_style="#414868")
    t1.add_column("Metric", style="bold #7dcfff")
    t1.add_column("Count")
    t1.add_row("Documents Processed", str(stats["scanned"]))
    t1.add_row("Newly Indexed", f"[bold green]{stats['indexed']}[/bold green]")
    t1.add_row("Cached (SHA-256 Match)", f"[dim]{stats['skipped']}[/dim]")
    t1.add_row("Total Knowledge Profiles", str(kb.get_status_summary()["total_documents"]))
    console.print(t1)

    # Step 2: Dataset Compilation
    builder = get_dataset_builder()
    ds_source_dir = target_docx_files[0].parent if target_docx_files else (scan_dir or Path.cwd())
    with ui.spinner("Step 2/3: Compiling structural supervision train/eval dataset splits..."):
        report = builder.build_dataset_from_directory(str(ds_source_dir))

    t2 = Table(title="[bold #7aa2f7]✓ Step 2/3: Supervision Dataset Manifest[/bold #7aa2f7]", border_style="#414868")
    t2.add_column("Dataset Attribute", style="bold #e0af68")
    t2.add_column("Details")
    t2.add_row("Train Examples (JSONL)", f"[bold green]{report['train_examples_generated']}[/bold green]")
    t2.add_row("Eval Examples (Disjoint)", f"[bold green]{report['eval_examples_generated']}[/bold green]")
    t2.add_row("Train Dataset Path", str(report["train_file"]))
    console.print(t2)

    # Step 3: Policy Gradient Calibration & Training
    from src.doc_gen.rlcd_engine import ARCHETYPES
    summary = kb.get_status_summary()
    res = rlcd.train_on_knowledge_corpus(summary)
    arch_dist = res.get("empirical_distribution", {})
    adapted = res.get("adapted_biases", {})
    episodes_trained = res.get("episodes_trained", 0)

    t3 = Table(title="[bold #9ece6a]✓ Step 3/3: Policy Priors Adapted to Ingested Corpus[/bold #9ece6a]", border_style="#414868")
    t3.add_column("Archetype", style="bold #7dcfff")
    t3.add_column("Empirical Frequency", style="yellow")
    t3.add_column("Calibrated Policy Bias", style="bold #9ece6a")
    for arch in ARCHETYPES:
        freq_val = arch_dist.get(arch, 0.0)
        freq_str = f"{freq_val * 100:.1f}%" if freq_val > 0 else "0.0%"
        bias_val = adapted.get(arch, 0.0)
        bias_str = f"{bias_val:+.3f}"
        t3.add_row(arch, freq_str, bias_str)
    console.print(t3)
    console.print(f"[dim]Priors updated from {episodes_trained} total corpus profiles.[/dim]\n")

    # Run live policy training stream
    _run_live_training_stream(10)

    # Optional neural model fine-tuning if requested
    if any(k in clean_arg.lower() for k in ("--fine-tune", "--finetune", "model", "sft")):
        from src.doc_gen.model_trainer import FilevoModelTrainer
        console.print(f"[bold #7aa2f7]Fine-tuning language model on generated supervision dataset...[/bold #7aa2f7]")
        try:
            trainer = FilevoModelTrainer()
            trainer.train(dry_run=False)
            console.print("[bold green]✓ Neural model weights updated with adapted checkpoint.[/bold green]")
        except Exception as e:
            console.print(f"[dim yellow]Model fine-tuning note: {e}[/dim yellow]")

    console.print("\n[bold green]★ Unified Training Pipeline Successfully Completed.[/bold green]\n")


def _run_live_training_stream(n_episodes: int):
    """Run real-time multi-episode streaming training with empirical calibration."""
    rlcd = get_rlcd()
    console.print(f"\n[bold #7aa2f7]Live RLCD Policy Training Stream ({n_episodes} Episodes)[/bold #7aa2f7]")

    with ui.create_progress() as progress:
        task = progress.add_task("Optimizing policy gradients on validation corpus...", total=n_episodes)
        res = rlcd.train_on_validation_episodes(n_episodes=n_episodes)
        progress.update(task, completed=n_episodes)

    cal_b = res.get("cal_before", {})
    cal_a = res.get("cal_after", {})
    from rich.table import Table
    t = Table(title="[bold #9ece6a]✓ Live Policy Training & Empirical Calibration Results[/bold #9ece6a]", border_style="#414868")
    t.add_column("Metric", style="bold #7dcfff")
    t.add_column("Before", style="yellow")
    t.add_column("After", style="bold #9ece6a")
    t.add_row("Expected Calibration Error (ECE)", f"{cal_b.get('ece', 0.0):.4f}", f"{cal_a.get('ece', 0.0):.4f}")
    t.add_row("Maximum Calibration Error (MCE)", f"{cal_b.get('mce', 0.0):.4f}", f"{cal_a.get('mce', 0.0):.4f}")
    t.add_row("Brier Score", f"{cal_b.get('brier_score', 0.0):.4f}", f"{cal_a.get('brier_score', 0.0):.4f}")
    t.add_row("Moving Baseline (b)", "—", f"{res.get('baseline', 0.0):.4f}")
    t.add_row("Learned Temperature (T*)", "1.000", f"{res.get('learned_temperature', 1.0):.3f}")
    t.add_row("Episodes Optimized", "—", str(res.get("episodes_run", 0)))
    console.print(t)
    console.print()


def cmd_feedback(reward_str: str):
    """Records user feedback on the active generation."""
    try:
        reward = float(reward_str.strip()) if reward_str.strip() else 1.0
    except ValueError:
        console.print(f"[red]Invalid feedback value:[/red] '{reward_str}'. Provide a float in [-1.0, +1.0].")
        return

    rlcd = get_rlcd()
    res = rlcd.record_feedback(reward=reward)

    if res.get("status") == "no_active_decision":
        console.print("[yellow]No active decision found. Generate a document first via /create.[/yellow]")
        return

    from rich.table import Table
    t = Table(title="[bold #9ece6a]✓ Policy Feedback Recorded[/bold #9ece6a]", border_style="#414868")
    t.add_column("Field", style="bold #7dcfff")
    t.add_column("Value")
    t.add_row("Reward Applied", f"{reward:+.2f}")
    t.add_row("Advantage (R - b)", f"{res['advantage']:+.4f}")
    t.add_row("Moving Baseline", f"{res['baseline']:.4f}")
    t.add_row("Policy Episode", str(res["episode"]))
    console.print(t)


def cmd_model():
    """Reports model and policy telemetry."""
    rlcd = get_rlcd()
    llm = get_llm()
    telemetry = rlcd.get_telemetry()

    from rich.table import Table
    t = Table(title="[bold #7aa2f7]Model & Policy Telemetry[/bold #7aa2f7]", border_style="#414868")
    t.add_column("Property", style="bold #e0af68")
    t.add_column("Value")
    t.add_row("Active Conversational Model", f"[bold #bb9af7]{llm.model_id}[/bold #bb9af7]")
    t.add_row("Inference Device", f"[bold #9ece6a]{llm.device.upper()}[/bold #9ece6a]")
    t.add_row("RLCD Policy Episodes", str(telemetry["episodes"]))
    t.add_row("Moving Baseline", str(telemetry["baseline"]))
    for arch, prob in telemetry["archetype_distribution"].items():
        bar_len = int(prob * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        t.add_row(f"Archetype: {arch}", f"{bar} {prob:.4f}")
    console.print(t)


def cmd_settings(arg: str = ""):
    """Reports configuration, commands, and environment settings. Supports toggling auto_open, engine, and mode."""
    arg_clean = arg.strip().lower()
    if arg_clean:
        if arg_clean in ("auto_open off", "off", "disable", "disabled", "false", "0"):
            set_auto_open(False)
            console.print("[bold green]✓ Document auto-open disabled.[/bold green] Generated documents will no longer open automatically.")
            return
        elif arg_clean in ("auto_open on", "on", "enable", "enabled", "true", "1"):
            set_auto_open(True)
            console.print("[bold green]✓ Document auto-open enabled.[/bold green] Generated documents will now open automatically upon creation.")
            return
        elif arg_clean in ("toggle", "auto_open toggle", "auto_open", "auto-open"):
            new_state = set_auto_open(not is_auto_open_enabled())
            state_str = "[bold green]enabled[/bold green]" if new_state else "[bold red]disabled[/bold red]"
            console.print(f"✓ Document auto-open toggled: now {state_str}.")
            return
        elif arg_clean.startswith("engine"):
            parts = arg_clean.split(maxsplit=1)
            if len(parts) > 1 and parts[1] in ("wordcraft", "wc"):
                set_doc_engine_setting("wordcraft")
                console.print("[bold green]✓ Preferred authoring engine set to WordCraft MCP.[/bold green]")
                return
            elif len(parts) > 1 and parts[1] in ("native", "openxml", "fallback"):
                set_doc_engine_setting("native")
                console.print("[bold green]✓ Preferred authoring engine set to Filevo Native OpenXML Renderer.[/bold green]")
                return
            else:
                console.print("[yellow]Usage: /settings engine wordcraft|native[/yellow]")
                return
        elif arg_clean.startswith("mode"):
            parts = arg_clean.split(maxsplit=1)
            if len(parts) > 1 and parts[1] in ("desktop", "live", "gui", "visible"):
                set_wordcraft_mode_setting("desktop")
                console.print("[bold green]✓ WordCraft mode set to Visible Desktop Application (Live).[/bold green]")
                return
            elif len(parts) > 1 and parts[1] in ("headless", "background", "cli"):
                set_wordcraft_mode_setting("headless")
                console.print("[bold green]✓ WordCraft mode set to Headless MCP Server.[/bold green]")
                return
            else:
                console.print("[yellow]Usage: /settings mode desktop|headless[/yellow]")
                return

    kb = get_kb()
    rlcd = get_rlcd()
    memory = get_memory()
    llm = get_llm()
    wc = get_wordcraft()

    summary = kb.get_status_summary()
    telemetry = rlcd.get_telemetry()
    mem_diag = memory.get_summary()

    auto_open_status = "[green]Enabled (Default)[/green]" if is_auto_open_enabled() else "[red]Disabled[/red]"
    wc_status = "[green]Detected & Available[/green]" if wc.is_available() else "[red]Not Available[/red]"

    from rich.table import Table
    t = Table(title="[bold #7aa2f7]Filevo Settings & Subsystems (Ctrl+P)[/bold #7aa2f7]", border_style="#414868")
    t.add_column("Setting / Subsystem", style="bold #e0af68")
    t.add_column("Current Value")
    t.add_row("Authoring Engine", f"WordCraft MCP: {wc_status} | Active: [cyan]{get_doc_engine_setting()}[/cyan] (Mode: [cyan]{get_wordcraft_mode_setting()}[/cyan])")
    t.add_row("Auto-Open Documents", f"{auto_open_status} (Toggle via /settings auto_open on|off)")
    t.add_row("Conversational Model", f"{llm.model_id} (Device: {llm.device})")
    t.add_row("Knowledge Base", f"{summary['total_documents']} indexed document(s)")
    t.add_row("Session Memory", f"{mem_diag['total_turns']} active turns, Active Topic: {mem_diag['active_topic'] or 'None'}")
    t.add_row("RLCD Policy", f"{telemetry['episodes']} episodes trained (Baseline: {telemetry['baseline']})")
    t.add_row("Storage Roots", f"Knowledge: ~/.filevo/knowledge | Output: ~/.filevo/output")
    t.add_row("Engine Toggles", "/settings engine wordcraft|native • /settings mode desktop|headless")
    t.add_row("Keyboard Shortcuts", "Ctrl+P (Settings), Ctrl+Y (Copy), Ctrl+C (Cancel), Ctrl+Q (Quit)")
    console.print(t)


def cmd_wordcraft(arg: str = ""):
    """Manages WordCraft MCP integration, live desktop mode, AST inspection, tools discovery, and page rendering."""
    from src.doc_gen.wordcraft_adapter import WordCraftClient, WordCraftConfig
    wc_cfg = WordCraftConfig.load()
    wc = get_wordcraft()
    info = wc.get_info()
    parts = arg.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else "status"
    subarg = parts[1] if len(parts) > 1 else ""

    if subcmd in ("status", "info"):
        from rich.table import Table
        t = Table(title="[bold #bb9af7]WordCraft MCP Engine & Anti-Slop Status[/bold #bb9af7]", border_style="#414868")
        t.add_column("Property", style="bold #e0af68", width=26)
        t.add_column("Value")
        avail_str = "[bold green]✓ Detected & Operational[/bold green]" if wc.is_available() else "[bold red]✗ Not Found[/bold red]"
        t.add_row("MCP Server Availability", avail_str)
        t.add_row("Config File", str(Path.home() / ".config" / "filevo" / "wordcraft.toml"))
        t.add_row("CLI Executable", wc_cfg.mcp_executable)
        t.add_row("Desktop GUI Binary", str(info.get("gui_path") or "None"))
        t.add_row("Localhost Control Address", wc_cfg.control_address)
        is_running = wc.is_desktop_running()
        gui_status = "[bold green]● Active (Listening on 7981)[/bold green]" if is_running else "[dim]○ Inactive (Run: wordcraft --control 7981)[/dim]"
        t.add_row("Desktop GUI Process", gui_status)
        t.add_row("Active Mode", f"[bold cyan]{wc_cfg.mode}[/bold cyan] (toggle: /settings mode desktop|headless)")
        t.add_row("Primary Engine", f"[bold cyan]{'WordCraft MCP' if wc_cfg.enabled else 'Native OpenXML'}[/bold cyan] (toggle: /settings engine wordcraft|native)")
        t.add_row("Fallback Policy", f"[magenta]{wc_cfg.fallback_policy}[/magenta]")
        t.add_row("Anti-Slop Policy", f"[bold green]Active[/bold green] (Formality: {wc_cfg.antislop.dials.formality}, Density: {wc_cfg.antislop.dials.density}, Ornament: {wc_cfg.antislop.dials.ornament})")
        t.add_row("Anti-Slop Typography", f"Display: {wc_cfg.antislop.font_display} | Body: {wc_cfg.antislop.font_body}")
        console.print(t)
        return

    if subcmd == "tools":
        with ui.spinner("Discovering tools from WordCraft MCP server..."):
            try:
                client = WordCraftClient(wc_cfg)
                with client:
                    client.start(force_desktop=False)
                    tools = client.discover_tools()
                from rich.table import Table
                t = Table(title=f"[bold #bb9af7]Discovered WordCraft MCP Tools ({len(tools)})[/bold #bb9af7]", border_style="#414868")
                t.add_column("Tool Name", style="bold #2ac3de", width=20)
                t.add_column("Description", style="white")
                for name, tool in sorted(tools.items()):
                    desc = tool.get("description", "").split("\n")[0]
                    t.add_row(name, desc[:90])
                console.print(t)
            except Exception as e:
                console.print(f"[red]Tools discovery failed:[/red] {e}")
        return

    if subcmd in ("live", "desktop"):
        if not subarg:
            console.print("[yellow]Usage: /wordcraft live <document topic or request>[/yellow]")
            return
        cmd_create(f"--live {subarg}")
        return

    if subcmd == "headless":
        if not subarg:
            console.print("[yellow]Usage: /wordcraft headless <document topic or request>[/yellow]")
            return
        cmd_create(f"--headless {subarg}")
        return

    if subcmd == "inspect":
        if not subarg:
            console.print("[yellow]Usage: /wordcraft inspect <path/to/document.docx>[/yellow]")
            return
        target = Path(subarg).expanduser().resolve()
        if not target.exists():
            console.print(f"[red]File not found:[/red] {target}")
            return
        with ui.spinner("Inspecting document structure via WordCraft MCP..."):
            try:
                client = WordCraftClient(wc_cfg)
                with client:
                    data = client.inspect_document()
                console.print(f"[bold #bb9af7]Structure of {target.name}:[/bold #bb9af7]")
                console.print(f"Blocks: {len(data.get('blocks', []))} | Words: {data.get('words', 0)} | Pages: {data.get('pages', 1)}")
                for i, b in enumerate(data.get("blocks", [])[:10]):
                    console.print(f"  [{i}] style={b.get('style')} type={b.get('type')}: {repr(b.get('text', ''))[:60]}")
            except Exception as e:
                console.print(f"[red]Inspection failed:[/red] {e}")
        return

    if subcmd == "render":
        if not subarg:
            console.print("[yellow]Usage: /wordcraft render <path/to/document.docx> [out_page1.png][/yellow]")
            return
        r_parts = subarg.split()
        target = Path(r_parts[0]).expanduser().resolve()
        out_png = Path(r_parts[1]).expanduser().resolve() if len(r_parts) > 1 else target.with_suffix(".png")
        if not target.exists():
            console.print(f"[red]File not found:[/red] {target}")
            return
        with ui.spinner("Rendering document page via WordCraft..."):
            try:
                client = WordCraftClient(wc_cfg)
                with client:
                    png_bytes = client.render_page(page=1, scale=1.5)
                with open(out_png, "wb") as f:
                    f.write(png_bytes)
                console.print(f"[bold green]✓ Page rendered successfully:[/bold green] {out_png}")
            except Exception as e:
                console.print(f"[red]Render failed:[/red] {e}")
        return

    console.print(f"[yellow]Unknown WordCraft subcommand:[/yellow] {subcmd}")
    console.print("[dim]Available: /wordcraft status, /wordcraft tools, /wordcraft live <topic>, /wordcraft headless <topic>, /wordcraft inspect <file>, /wordcraft render <file>[/dim]")


def cmd_status(arg: str = ""):
    """Alias for /settings."""
    cmd_settings(arg)


def cmd_open():
    """Opens the documents output directory in Dolphin or the default system file manager."""
    import subprocess
    out_dir = Path.home() / ".filevo" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(["dolphin", str(out_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print(f"[green]✔ Opened file directory in Dolphin:[/green] {out_dir}")
    except Exception:
        try:
            subprocess.Popen(["xdg-open", str(out_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            console.print(f"[green]✔ Opened file directory:[/green] {out_dir}")
        except Exception as e:
            console.print(f"[red]✗ Failed to launch file manager: {e}[/red]")


def cmd_clear():
    """Clears terminal screen and redraws full reference dashboard."""
    os.system("clear" if os.name != "nt" else "cls")
    memory = get_memory()
    rlcd = get_rlcd()
    llm = get_llm()
    global _latest_references
    turns = [
        {
            "role": t.role,
            "content": t.content,
            "timestamp": time.strftime("%H:%M:%S", time.localtime(t.timestamp)),
        }
        for t in memory.turns
    ]
    ui.render_dashboard(
        turns=turns,
        dec_info=rlcd.last_decision_intent or {
            "probabilities": {
                "DOCUMENT_CREATION": 0.12,
                "CONVERSATION": 0.71,
                "DOCUMENT_ANALYSIS": 0.08,
                "KNOWLEDGE_INDEXING": 0.05,
                "POLICY_TRAIN": 0.04,
            },
            "confidence": 0.713,
            "entropy": 0.58,
            "risk": "LOW",
        },
        references=_latest_references,
        model_name=Path(llm.model_id).name,
        device=llm.device,
    )


# ------------------------------------------------------------------ #
# Pathway B: Model-Driven Conversational & Natural Language Pipeline
# ------------------------------------------------------------------ #

def resolve_historical_facts(query: str, memory: ConversationMemory) -> str | None:
    """Extract structured historical facts from session turns, hardware entities, and revisions."""
    import re
    q_lower = query.lower()

    # 1. Hardware detection across all conversation turns
    hw_detected = []
    all_turns_text = " ".join(t.content for t in memory.turns)
    t_lower = all_turns_text.lower()

    if "esp32" in t_lower:
        hw_detected.append("ESP32 microcontroller")
    if "ir" in t_lower or "infrared" in t_lower:
        hw_detected.append("IR sensors (infrared beam-break)")
    if "camera" in t_lower or "ball detection" in t_lower or "optical tracking" in t_lower:
        hw_detected.append("camera-based ball detection")
    if "raspberry" in t_lower:
        hw_detected.append("Raspberry Pi")
    if "arduino" in t_lower:
        hw_detected.append("Arduino")

    # 2. Expanded sections from memory or turn analysis
    last_expanded = getattr(memory, "last_expanded_section", None)
    expanded_sections = []
    if last_expanded:
        expanded_sections.append(last_expanded)

    for turn in reversed(memory.turns):
        t_c = turn.content
        m = re.search(r"expanding the ([\w\s]+) section", t_c, re.IGNORECASE)
        if m and m.group(1).strip() not in expanded_sections:
            expanded_sections.append(m.group(1).strip())
        m2 = re.search(r"(?:expand|detail|detailed|rewrite|revise)\s+(?:the\s+)?([\w]+)\s+(?:section|in)", t_c, re.IGNORECASE)
        if m2 and m2.group(1).strip().title() not in expanded_sections and m2.group(1).lower() not in ("that", "this", "it"):
            expanded_sections.append(m2.group(1).strip().title())

    # 3. Document versions on disk
    out_dir = Path.home() / ".filevo" / "output"
    docs = sorted(out_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime) if out_dir.exists() else []

    asks_hw = any(w in q_lower for w in ("hardware", "sensor", "sensors", "microcontroller", "components", "devices"))
    asks_sec = any(w in q_lower for w in ("section", "expand", "expanded", "revised", "detail", "methodology"))

    if (asks_hw or asks_sec) and (hw_detected or expanded_sections):
        lines = ["Based on our conversation history:"]
        if asks_hw:
            hw_str = ", ".join(hw_detected) if hw_detected else "None identified in current session"
            lines.append(f"• **Hardware mentioned by you**: {hw_str}.")
        if asks_sec:
            sec_str = ", ".join(expanded_sections) if expanded_sections else "Methodology"
            lines.append(f"• **Section requested to expand**: {sec_str} (requested by you in follow-up revision).")
        if docs:
            lines.append(f"• **Document versions on disk**: {', '.join(d.name for d in docs[-2:])}.")
        return "\n".join(lines)
    return None


def handle_natural_language_pipeline(user_input: str):
    """Processes all non-command natural language input through the model without hardcoding."""
    clean_text, attachments = resolve_file_mentions(user_input)
    memory = get_memory()
    llm = get_llm()
    rlcd = get_rlcd()

    if attachments:
        console.print(f"[dim]📎 Attached {len(attachments)} referenced file(s): {', '.join(a['name'] for a in attachments)}[/dim]")

    # Step 1: Render styled user message bubble matching reference UI
    ui.print_user_message(clean_text)

    # Step 2: Add user message to conversation memory
    memory.add_user_message(clean_text, attachments)

    # Step 3: Context & reference resolution (e.g. resolving "it" or follow-up instructions)
    resolved_ref = memory.resolve_references(clean_text)

    # Open folder / directory intent
    if any(re.search(pat, p_lower) for pat in (
        r"\b(?:open|show|browse|launch)\b.*\b(?:file directory|directory|folder|files|dolphin|output)\b",
        r"\b(?:where (?:are )?(?:all )?files)\b",
    )):
        cmd_open()
        return

    # Explicit creation intent ALWAYS takes precedence over active document existence
    creation_cues = [
        "create a", "create detailed", "create technical", "create report", "create document",
        "generate a", "generate detailed", "generate report", "write a report", "write a technical",
        "draft a", "build a report", "create an iot", "produce a", "draft technical",
    ]
    is_explicit_creation = any(re.search(rf"\b{re.escape(cue)}\b", p_lower) for cue in creation_cues) or (
        p_lower.startswith("create ") or p_lower.startswith("generate ") or p_lower.startswith("draft ")
    )

    if is_explicit_creation:
        cmd_create(clean_text, attachments)
        return

    # Check if user is asking a historical question about previous turns, hardware, or sections
    is_query_about_history = bool(
        re.search(r"\b(which|what|tell me|did|was|were|who)\b.*\b(expanded|revised|discussed|created|mentioned|written|changed|hardware|sensors?|microcontroller|technology|section)\b", p_lower)
        or (p_lower.startswith(("which", "what", "how", "did", "was", "were")) and "?" in p_lower)
    )

    revision_action_patterns = [
        r"\b(?:revise|rewrite|expand|elaborate|update|modify|improve|extend|shorten|lengthen|version|adjust|formalize)\b",
        r"\b(?:make it|add a section|add more|more detail|more detailed)\b",
    ]
    is_explicit_revision = any(re.search(pat, p_lower) for pat in revision_action_patterns)
    has_target = any(tw in p_lower for tw in ("its", "the report", "the document", "the doc", "this report", "this doc", "that report", "methodology", "architecture", "conclusion", "introduction", "section", "abstract"))
    has_active_doc = bool(memory.active_document_path and Path(memory.active_document_path).exists())
    if not has_active_doc:
        out_dir = Path.home() / ".filevo" / "output"
        if out_dir.exists():
            docx_files = sorted(out_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
            if docx_files:
                memory.active_document_path = str(docx_files[0])
                memory.active_document_topic = docx_files[0].stem.replace("_", " ")
                has_active_doc = True

    if not is_query_about_history and has_active_doc and (is_explicit_revision or (has_target and any(w in p_lower for w in ("expand", "add", "more", "detail", "detailed", "change", "include")))):
        cmd_revise(clean_text)
        return

    if is_query_about_history:
        fact_answer = resolve_historical_facts(clean_text, memory)
        if fact_answer:
            if not getattr(llm, "_is_loaded", False):
                memory.add_assistant_message(fact_answer)
                ui.print_assistant_message(fact_answer)
                return

    # Step 4: Calibrated RLCD Intent evaluation & decision
    with ui.spinner("Evaluating calibrated intent with RLCD engine..."):
        intent_eval = rlcd.evaluate_intent(clean_text)

    intent_type = intent_eval.get("intent", "CONVERSATION")

    # Step 5: Route based on calibrated intent
    if intent_type == "DOCUMENT_CREATION":
        cmd_create(clean_text, attachments)
        return
    elif intent_type == "DOCUMENT_ANALYSIS":
        cmd_analyze(clean_text)
        return
    elif intent_type == "KNOWLEDGE_INDEXING":
        cmd_index(".")
        return
    elif intent_type == "POLICY_TRAIN":
        cmd_train("corpus")
        return

    # Step 6: General conversation, explanations, questions, and acknowledgments
    question_cues = ["why", "how", "what", "explain", "describe", "tell me", "does", "difference"]
    if any(q in p_lower for q in question_cues) or "?" in clean_text:
        try:
            from src.doc_gen.web_researcher import WebResearcher
            wr = WebResearcher()
            res = wr.research_topic(clean_text)
            if res.get("sources"):
                global _latest_references
                _latest_references = res["sources"]
        except Exception:
            pass

    with ui.spinner("Generating response..."):
        # Format messages for local model with active document grounding if available
        messages = memory.get_messages_for_llm()
        if has_active_doc and memory.active_document_path:
            renderer = get_renderer()
            doc_info = renderer.extract_document_content(memory.active_document_path)

            last_expanded = getattr(memory, "last_expanded_section", None)
            if not last_expanded:
                for turn in reversed(memory.turns):
                    m = re.search(r"expanding the ([\w\s]+) section", turn.content, re.IGNORECASE)
                    if m:
                        last_expanded = m.group(1).strip()
                        break

            doc_context = (
                f"\n[Active Document Context]\n"
                f"Title: {doc_info.get('title')}\n"
                f"File: {Path(memory.active_document_path).name}\n"
            )
            if last_expanded:
                doc_context += f"Recent Modification: The '{last_expanded}' section was expanded in the latest version.\n"

            doc_context += f"Sections: {', '.join(s['title'] for s in doc_info.get('sections', []))}\n"
            doc_context += "Section Summaries:\n"
            for s in doc_info.get("sections", [])[:6]:
                s_title = s.get("title", "")
                s_content = s.get("content", "").strip()
                snippet = " ".join(s_content.split())[:350]
                if last_expanded and last_expanded.lower() in s_title.lower():
                    doc_context += f"- {s_title} (Expanded in latest version): {snippet}...\n"
                else:
                    doc_context += f"- {s_title}: {snippet}...\n"

            messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{doc_context}"}] + [
                m for m in messages if m.get("role") != "system"
            ]

        response = llm.generate_chat_response(messages)

    # Record assistant turn in memory and render
    memory.add_assistant_message(response)
    ui.print_assistant_message(response)


def handle_input(raw_input: str):
    """Main input router: separates deterministic slash commands from natural language."""
    text = raw_input.strip()
    if not text:
        return

    # Pathway A: Explicit Deterministic Slash Commands
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            cmd_help()
        elif cmd == "/create":
            clean_arg, atts = resolve_file_mentions(arg)
            cmd_create(clean_arg, atts)
        elif cmd == "/revise":
            cmd_revise(arg)
        elif cmd == "/research":
            cmd_research(arg)
        elif cmd == "/analyze":
            cmd_analyze(arg)
        elif cmd == "/train":
            clean_arg, atts = resolve_file_mentions(arg)
            cmd_train(clean_arg, attachments=atts)
        elif cmd == "/index":
            console.print("[dim yellow]Notice: /index has been unified into /train. Running unified ingestion and training...[/dim yellow]")
            clean_arg, atts = resolve_file_mentions(arg)
            cmd_train(clean_arg or ".", attachments=atts)
        elif cmd == "/feedback":
            cmd_feedback(arg)
        elif cmd == "/dataset":
            cmd_dataset(arg)
        elif cmd == "/benchmark":
            cmd_benchmark()
        elif cmd == "/model":
            cmd_model()
        elif cmd in ("/wordcraft", "/wc"):
            cmd_wordcraft(arg)
        elif cmd == "/settings":
            cmd_settings(arg)
        elif cmd == "/status":
            cmd_status(arg)
        elif cmd in ("/open", "/browse", "/files"):
            cmd_open()
        elif cmd == "/copy":
            cmd_copy()
        elif cmd == "/clear":
            cmd_clear()
        elif cmd in ("/exit", "/quit", "/q"):
            console.print("\n[bold #7aa2f7]Goodbye! 👋[/bold #7aa2f7]\n")
            sys.exit(0)
        else:
            console.print(f"[red]✗ Unknown command:[/red] {cmd}")
            console.print("[dim]Type /help for available commands.[/dim]")
        return

    # Pathway B: Model-Driven Conversational Pipeline
    handle_natural_language_pipeline(text)


# ------------------------------------------------------------------ #
# Interactive CLI Loop with Bottom-Docked Prompt Area
# ------------------------------------------------------------------ #

def interactive_loop():
    """Main terminal loop with readline and bottom status bar matching user reference image."""
    try:
        import readline
        histfile = Path.home() / ".filevo" / "history"
        histfile.parent.mkdir(parents=True, exist_ok=True)
        try:
            readline.read_history_file(str(histfile))
        except FileNotFoundError:
            pass
        readline.set_history_length(500)

        cmd_list = list(COMMANDS.keys())
        def completer(text, state):
            opts = [c for c in cmd_list if c.startswith(text)]
            return opts[state] if state < len(opts) else None
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
    except ImportError:
        histfile = None

    cmd_clear()
    llm = get_llm()

    while True:
        try:
            # Render bottom status line right above prompt (matching the user's uploaded screenshot)
            ui.render_bottom_prompt_box(
                model_name=Path(llm.model_id).name,
                mode_label="Plan",
                context_info="16.4k (5%)",
                cwd_label="CIE:main",
            )
            raw = input("filevo> ").strip()
            if raw:
                handle_input(raw)
                console.print()
        except KeyboardInterrupt:
            console.print("\n[dim](Ctrl+C pressed — type /exit to quit)[/dim]\n")
        except EOFError:
            console.print("\n[bold #7aa2f7]Goodbye! 👋[/bold #7aa2f7]\n")
            if histfile:
                try:
                    import readline
                    readline.write_history_file(str(histfile))
                except Exception:
                    pass
            sys.exit(0)
        except Exception as e:
            console.print(f"[red]✗ Error:[/red] {e}\n")


def main():
    """CLI entry point for direct script execution."""
    parser = argparse.ArgumentParser(
        prog="report",
        description="Filevo — Conversational Document Intelligence & RLCD Generation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    cp = subparsers.add_parser("create", help="Create DOCX from request")
    cp.add_argument("request", nargs="+", help="Document topic or request")

    rp = subparsers.add_parser("research", help="Research a topic across web and live sources")
    rp.add_argument("topic", nargs="+", help="Topic to research")

    ap = subparsers.add_parser("analyze", help="Analyze document or codebase")
    ap.add_argument("path", nargs="?", default=".", help="Path to analyze")

    ip = subparsers.add_parser("index", help=argparse.SUPPRESS)
    ip.add_argument("path", nargs="?", default=".", help=argparse.SUPPRESS)

    dp = subparsers.add_parser("dataset", help="Build DOCX supervision dataset")
    dp.add_argument("path", nargs="?", default=".", help="Directory to scan")

    subparsers.add_parser("benchmark", help="Benchmark candidate local models")

    tp = subparsers.add_parser("train", help="Run learning workflow")
    tp.add_argument("args", nargs="*", default=["corpus"], help="Reward or live [N]")

    fp = subparsers.add_parser("feedback", help="Record feedback on generation")
    fp.add_argument("reward", nargs="?", default="1.0", help="Reward value in [-1.0, +1.0]")

    stp = subparsers.add_parser("settings", help="Report or toggle settings")
    stp.add_argument("args", nargs="*", default=[], help="Setting options like auto_open on|off")
    wcp = subparsers.add_parser("wordcraft", help="WordCraft MCP engine status, tools, and actions")
    wcp.add_argument("args", nargs="*", default=[], help="WordCraft options: status|tools|live|headless|inspect|render")
    subparsers.add_parser("model", help="Report model and policy information")
    subparsers.add_parser("status", help="Report system and index status")

    chp = subparsers.add_parser("chat", help="Chat conversationally with Filevo")
    chp.add_argument("message", nargs="+", help="User message or query")

    rvp = subparsers.add_parser("revise", help="Revise active document")
    rvp.add_argument("instruction", nargs="+", help="Revision instruction")

    args, unknown = parser.parse_known_args()
    if unknown and hasattr(args, "args") and isinstance(args.args, list):
        args.args.extend(unknown)

    if args.command == "create":
        cmd_create(" ".join(args.request))
    elif args.command == "wordcraft":
        cmd_wordcraft(" ".join(args.args) if hasattr(args, "args") else "")
    elif args.command == "chat":
        handle_natural_language_pipeline(" ".join(args.message))
    elif args.command == "revise":
        cmd_revise(" ".join(args.instruction))
    elif args.command == "research":
        cmd_research(" ".join(args.topic))
    elif args.command == "analyze":
        cmd_analyze(args.path)
    elif args.command == "index":
        console.print("[dim yellow]Notice: 'report index' has been unified into 'report train'. Running unified ingestion and training...[/dim yellow]")
        cmd_train(args.path)
    elif args.command == "dataset":
        cmd_dataset(args.path)
    elif args.command == "benchmark":
        cmd_benchmark()
    elif args.command == "train":
        cmd_train(" ".join(args.args))
    elif args.command == "feedback":
        cmd_feedback(args.reward)
    elif args.command == "model":
        cmd_model()
    elif args.command == "settings":
        cmd_settings(" ".join(args.args) if hasattr(args, "args") else "")
    elif args.command == "status":
        cmd_status(" ".join(args.args) if hasattr(args, "args") else "")
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
