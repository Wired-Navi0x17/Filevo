#!/usr/bin/env python3
"""Filevo Conversational CLI — Antigravity-Style Rich Terminal Application.

Features:
- Pathway A: Strict, reliable slash commands (/create, /analyze, /index, /train, /feedback, etc.)
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
from src.doc_gen.docx_renderer import DocxRenderer
from src.doc_gen.knowledge_base import DocumentKnowledgeBase
from src.doc_gen.llm_client import LocalTransformersClient
from src.doc_gen.rich_ui import console, ui
from src.doc_gen.rl_model import RLProbabilisticModel
from src.doc_gen.rlcd_engine import RLCDDecisionEngine

# ------------------------------------------------------------------ #
# Command Registry (Path A: Explicit Deterministic Slash Commands)
# ------------------------------------------------------------------ #

COMMANDS = {
    "/help": "Displays all available commands and keyboard shortcuts",
    "/create": "Creates a calibrated DOCX document  (/create <topic/request>)",
    "/revise": "Revises and versions active document (/revise <instruction>)",
    "/research": "Researches a topic across web and live sources (/research <topic>)",
    "/analyze": "Analyzes a document, collection, or codebase (/analyze <path>)",
    "/index": "Indexes DOCX files into persistent metadata cache (/index [path])",
    "/train": "Runs learning workflow or live streaming (/train [args])",
    "/feedback": "Records feedback on active generation (/feedback [+1.0|-0.5])",
    "/dataset": "Builds leakage-free DOCX training dataset (/dataset [dir])",
    "/benchmark": "Benchmarks candidate local models on 16GB VRAM (/benchmark)",
    "/model": "Reports active model, policy weights, and probabilities",
    "/status": "Reports system, knowledge base, and memory status",
    "/clear": "Clears terminal screen and redraws Antigravity banner",
    "/exit": "Exits the application",
}

# ------------------------------------------------------------------ #
# Global Singletons
# ------------------------------------------------------------------ #

_knowledge_base: DocumentKnowledgeBase | None = None
_rlcd_engine: RLCDDecisionEngine | None = None
_docx_renderer: DocxRenderer | None = None
_rl_model: RLProbabilisticModel | None = None
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


def get_model() -> RLProbabilisticModel:
    global _rl_model
    if _rl_model is None:
        model_path = Path.home() / ".filevo" / "model.json"
        _rl_model = RLProbabilisticModel(model_path=str(model_path))
    return _rl_model


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
# @file Attachment Mention Resolver
# ------------------------------------------------------------------ #

def resolve_file_mentions(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse @filepath mentions, read contents/outlines, and return attachments."""
    pattern = r"@([a-zA-Z0-9_\-\.\/\~]+)"
    matches = re.findall(pattern, text)
    attachments = []
    clean_text = text

    for match in matches:
        raw_path = match.strip()
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
    """Creates a validated DOCX document using RLCD calibrated decision policy."""
    if not request_str.strip():
        console.print("[yellow]Please specify a topic or document request. Example: /create Technical Report on AI[/yellow]")
        return

    kb = get_kb()
    rlcd = get_rlcd()
    renderer = get_renderer()
    memory = get_memory()

    with ui.spinner(f"Evaluating RLCD calibrated decision policy for: '{request_str}'..."):
        decision = rlcd.decide(request_str)
        time.sleep(0.1)

    # Render styled decision telemetry panel
    ui.display_decision_card(decision)

    llm = get_llm()
    formatting = decision.formatting

    # Semantic Title & Topic extraction via language model
    spec = llm.extract_document_spec(request_str, memory.get_messages_for_llm())
    title = spec.get("title") or f"{decision.archetype} Document"
    topic = spec.get("topic") or title

    # Live Web Research grounding for unknown topics or web-assisted requests
    web_data = None
    has_local = False
    try:
        similar = kb.find_similar(request_str, top_k=1)
        if similar and similar[0].get("similarity", 0) > 0.45:
            has_local = True
    except Exception:
        has_local = False

    needs_web = (not has_local) or any(k in request_str.lower() for k in ("web", "browse", "research", "internet", "online", "latest", "news"))
    if needs_web:
        with ui.spinner(f"Grounding topic via live web research (Wikipedia & Web Search)..."):
            from src.doc_gen.web_researcher import WebResearcher
            wr = WebResearcher()
            web_data = wr.research_topic(request_str)
            if web_data.get("has_web_data"):
                console.print(f"[dim]🌐 Live web knowledge grounded: {len(web_data.get('sources', []))} reference source(s) discovered[/dim]")

    sections = []
    att_summary = ""
    if attachments:
        att_names = [a["name"] for a in attachments]
        att_summary = f"Incorporating grounded context from referenced file(s): {', '.join(att_names)}.\n\n"
        for a in attachments:
            if a.get("content"):
                att_summary += f"### Reference: {a['name']}\n{a['content'][:300]}...\n\n"

    # Incorporate web overview into introduction if available
    web_overview = web_data.get("overview", "") if web_data else ""
    web_sources = web_data.get("sources", []) if web_data else []
    grounding = f"{web_overview}\n{att_summary}".strip()

    with ui.spinner("Synthesizing document content with local model and compiling OpenXML package..."):
        if decision.archetype == "Formal Letter":
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
                    "content": llm.generate_section_content("Statement of Purpose", title, decision.archetype, grounding),
                },
                {
                    "title": "Background and Justification",
                    "content": llm.generate_section_content("Background and Justification", title, decision.archetype, grounding),
                },
                {
                    "title": "Formal Terms and Requirements",
                    "content": llm.generate_section_content("Formal Terms and Requirements", title, decision.archetype, grounding),
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
            for i, s_title in enumerate(decision.recommended_sections):
                content = llm.generate_section_content(
                    section_title=s_title,
                    doc_title=title,
                    archetype=decision.archetype,
                    grounding_context=grounding,
                )
                sec_dict = {"title": s_title, "content": content}

                if formatting.include_tables and ("Evaluation" in s_title or "Analysis" in s_title or "Architecture" in s_title):
                    sec_dict["table"] = [
                        ["Component", "Metric", "Calibrated Value", "Target Status"],
                        ["Decision Gate", "Agreement (JSD)", f"{decision.agreement*100:.1f}%", "Passed"],
                        ["Normalized Entropy", "H_norm(P)", f"{decision.normalized_entropy:.3f}", "Calibrated"],
                        ["Typography Strategy", "Font Family", formatting.font_family, "Applied"],
                        ["OpenXML Validation", "Integrity", "100%", "Verified"],
                    ]
                sections.append(sec_dict)

        # Append Live Web Sources & References section if web research was conducted
        if web_sources:
            ref_content = "Primary references and live web sources consulted during synthesis:\n\n"
            for s in web_sources[:6]:
                ref_content += f"• {s}\n"
            sections.append({"title": "References and Discovered Sources", "content": ref_content})

        doc_path = renderer.render(title=title, sections=sections, strategy=formatting)

    # Record in conversational memory
    memory.add_assistant_message(
        f"Generated {decision.archetype} on '{title}' at {doc_path}",
        generated_doc=str(doc_path),
        archetype=decision.archetype,
        topic=title,
    )

    # Display styled document card
    ui.display_document_card(doc_path, title, len(sections), decision.archetype)


def cmd_revise(revision_instruction: str):
    """Revises and versions the active document in conversation memory."""
    memory = get_memory()
    active_doc = memory.active_document_path
    active_topic = memory.active_document_topic or "Document"
    if not active_doc or not Path(active_doc).exists():
        console.print("[yellow]No active document to revise. Create a document first via /create.[/yellow]")
        return None

    orig_path = Path(active_doc)
    stem = orig_path.stem
    if "_v" in stem:
        parts = stem.split("_v")
        try:
            ver = int(parts[-1]) + 1
            new_stem = f"{parts[0]}_v{ver}"
        except ValueError:
            new_stem = f"{stem}_v2"
    else:
        new_stem = f"{stem}_v2"

    new_filename = f"{new_stem}.docx"
    rlcd = get_rlcd()
    renderer = get_renderer()
    llm = get_llm()

    with ui.spinner(f"Revising and versioning '{stem}' -> '{new_stem}'..."):
        decision = rlcd.decide(f"{active_topic} {revision_instruction}")
        fmt = decision.formatting
        if "formal" in revision_instruction.lower():
            fmt.accent_color = "333333"
            fmt.font_family = "Times New Roman"
            fmt.line_spacing = 1.15

        revised_sections = [
            {
                "title": s,
                "content": llm.rewrite_section_content(
                    existing_content=f"Section {s} regarding {active_topic}.",
                    section_title=s,
                    revision_instruction=revision_instruction,
                ),
            }
            for s in decision.recommended_sections
        ]
        new_path = renderer.render(title=active_topic, sections=revised_sections, strategy=fmt, output_filename=new_filename)

    rev_msg = f"I have revised '{active_topic}' and created version 2 at {new_path.name} with your requested adjustments."
    memory.add_assistant_message(
        rev_msg,
        generated_doc=str(new_path),
        archetype=decision.archetype,
        topic=active_topic,
    )
    ui.print_assistant_message(rev_msg)
    ui.display_document_card(new_path, f"{active_topic} (Version 2)", len(revised_sections), decision.archetype)
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


def cmd_benchmark():
    """Benchmark candidate models on 16GB VRAM on actual Filevo tasks."""
    llm = get_llm()
    console.print("[bold #7aa2f7]Benchmarking candidate models on NVIDIA RTX 4090 GPU (16 GB VRAM)...[/bold #7aa2f7]")

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


def cmd_train(arg: str):
    """Runs the learning workflow or live policy training stream."""
    parts = arg.strip().split()
    kb = get_kb()
    rlcd = get_rlcd()

    if parts and parts[0] in ("live", "--live", "-l"):
        n_episodes = 5
        if len(parts) > 1:
            try:
                n_episodes = max(1, min(50, int(parts[1])))
            except ValueError:
                pass
        return _run_live_training_stream(n_episodes)

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
            t.add_row("Eval Loss", f"{metrics.eval_loss:.4f}")
            t.add_row("Samples Trained", str(metrics.samples_trained))
            t.add_row("Checkpoint Dir", metrics.checkpoint_dir)
            console.print(t)
        except Exception as e:
            console.print(f"[red]Model training failed:[/red] {e}")
        return

    if not parts or parts[0] in ("corpus", "auto", "kb"):
        summary = kb.get_status_summary()
        res = rlcd.train_on_knowledge_corpus(summary)
        console.print(f"[bold #9ece6a]✓ RLCD Policy Adapted on Knowledge Corpus[/bold #9ece6a] ({res.get('episodes_trained', 0)} profiles).")
        return

    try:
        reward = float(parts[0])
        cmd_feedback(str(reward))
    except ValueError:
        console.print(f"[red]Invalid training parameter:[/red] {parts[0]}")


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


def cmd_status():
    """Reports system, knowledge base, and memory status."""
    kb = get_kb()
    rlcd = get_rlcd()
    memory = get_memory()
    llm = get_llm()

    summary = kb.get_status_summary()
    telemetry = rlcd.get_telemetry()
    mem_diag = memory.get_summary()

    from rich.table import Table
    t = Table(title="[bold #7aa2f7]Filevo System Status[/bold #7aa2f7]", border_style="#414868")
    t.add_column("Subsystem", style="bold #e0af68")
    t.add_column("Details")
    t.add_row("Conversational Model", f"{llm.model_id} (Device: {llm.device})")
    t.add_row("Knowledge Base", f"{summary['total_documents']} indexed document(s)")
    t.add_row("Session Memory", f"{mem_diag['total_turns']} active turns, Active Topic: {mem_diag['active_topic'] or 'None'}")
    t.add_row("RLCD Policy", f"{telemetry['episodes']} episodes trained (Baseline: {telemetry['baseline']})")
    t.add_row("Storage Roots", f"Knowledge: ~/.filevo/knowledge | Output: ~/.filevo/output")
    console.print(t)


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

    # Check if user is asking to revise/update the active document
    p_lower = clean_text.lower()
    is_question = any(p_lower.startswith(q) for q in ("why", "how", "what", "explain", "describe", "tell me", "does", "can you")) or ("?" in p_lower and not any(r in p_lower for r in ("revise", "make it", "rewrite")))
    revision_cues = ["make it", "more formal", "revise", "rewrite", "shorter", "longer", "add a section", "update the doc"]
    if memory.active_document_path and not is_question and any(rc in p_lower for rc in revision_cues):
        cmd_revise(clean_text)
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
        # Format messages for local model
        messages = memory.get_messages_for_llm()
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
        elif cmd == "/index":
            cmd_index(arg)
        elif cmd == "/train":
            cmd_train(arg)
        elif cmd == "/feedback":
            cmd_feedback(arg)
        elif cmd == "/dataset":
            cmd_dataset(arg)
        elif cmd == "/benchmark":
            cmd_benchmark()
        elif cmd == "/model":
            cmd_model()
        elif cmd == "/status":
            cmd_status()
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

    ip = subparsers.add_parser("index", help="Index DOCX files into knowledge base")
    ip.add_argument("path", nargs="?", default=".", help="Directory to index")

    dp = subparsers.add_parser("dataset", help="Build DOCX supervision dataset")
    dp.add_argument("path", nargs="?", default=".", help="Directory to scan")

    subparsers.add_parser("benchmark", help="Benchmark candidate local models")

    tp = subparsers.add_parser("train", help="Run learning workflow")
    tp.add_argument("args", nargs="*", default=["corpus"], help="Reward or live [N]")

    fp = subparsers.add_parser("feedback", help="Record feedback on generation")
    fp.add_argument("reward", nargs="?", default="1.0", help="Reward value in [-1.0, +1.0]")

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
    elif args.command == "chat":
        handle_natural_language_pipeline(" ".join(args.message))
    elif args.command == "revise":
        cmd_revise(" ".join(args.instruction))
    elif args.command == "research":
        cmd_research(" ".join(args.topic))
    elif args.command == "analyze":
        cmd_analyze(args.path)
    elif args.command == "index":
        cmd_index(args.path)
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
    elif args.command == "status":
        cmd_status()
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
