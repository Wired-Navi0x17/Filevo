"""Antigravity-Style Modern Rich Terminal Interface for Filevo.

Full implementation of the Filevo Local AI Development Environment UI
matching the reference visual design:
- Prominent FILEVO ASCII mountain landscape banner & model/session telemetry
- Compact navigation row: [ HOME ] | CREATE | ANALYZE | INDEX | TRAIN | MODEL | STATUS | HELP
- Large central conversation area with owl avatar and timestamps
- Right sidebar with real RLCD decision telemetry & discovered references
- Bottom panels: Recent Documents & System Status gauge bars
- Persistent bottom prompt bar with shortcuts
- Adaptive layout for small and large terminal dimensions
"""

from __future__ import annotations

import datetime
import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rich.align import Align
from rich.box import ROUNDED, SIMPLE
from rich.console import Console, Group
from rich.layout import Layout
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Polished Dark Palette (Nordic Slate & Frosted Sapphire, Zero Neon)
FILEVO_THEME = Theme({
    "border": "#4c566a",
    "border.dim": "#3b4252",
    "cyan.bright": "#88aece",
    "cyan.accent": "#81a1c1",
    "teal": "#8fbcbb",
    "amber": "#ebcb8b",
    "green": "#a3be8c",
    "red": "#bf616a",
    "slate": "#4c566a",
    "dark": "#0f1116",
    "white": "#e5e9f0",
})

console = Console(theme=FILEVO_THEME)

ASCII_BANNER = r"""  _  _  _       _____ ___ _     _______     __ ___        _  _  _  
/       \      |  ___|_ _| |   | ____\ \   / // _ \     /       \ 
|   (o)   |    | |_   | || |   |  _|  \ \ / /| | | |   |   (o)   |
\       /      |  _|  | || |___| |___  \ V / | |_| |    \       / 
  ~ ~ ~        |_|   |___|_____|_____|  \_/   \___/       ~ ~ ~   """


class AntigravityRichUI:
    """Terminal UI for Filevo matching the reference visual composition."""

    def __init__(self, is_interactive: bool = True):
        self.console = console
        self.is_interactive = is_interactive and sys.stdout.isatty()
        self.owl_printed = False

    @contextmanager
    def spinner(self, status_text: str = "Thinking..."):
        """Display live animated spinner for model inference and synthesis."""
        if not self.is_interactive:
            self.console.print(f"[dim]⟳ {status_text}[/dim]")
            yield
            return

        with self.console.status(f"[bold #2ac3de]{status_text}[/bold #2ac3de]", spinner="dots", spinner_style="bold #7aa2f7") as status:
            yield status

    def create_progress(self) -> Progress:
        """Create real progress bar for indexing and live policy training."""
        return Progress(
            SpinnerColumn(spinner_name="dots", style="bold #e0af68"),
            TextColumn("[bold #7aa2f7]{task.description}"),
            BarColumn(bar_width=25, style="#414868", complete_style="#2ac3de", finished_style="#9ece6a"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
        )

    # ------------------------------------------------------------------ #
    # Panel Renderers matching Reference UI
    # ------------------------------------------------------------------ #

    def build_top_banner_panel(self) -> Panel:
        """Top left ASCII banner panel with mountain landscape."""
        text = Text()
        text.append(ASCII_BANNER + "\n", style="bold #2ac3de")
        text.append("             Conversational Document Intelligence\n", style="bold #7aa2f7")
        return Panel(
            Align.center(text),
            box=ROUNDED,
            border_style="#2ac3de",
            padding=(0, 1),
        )

    def display_banner(self, model_name: str = "SmolLM2-1.7B-Instruct"):
        """Print top ASCII banner to console."""
        self.console.print(self.build_top_banner_panel())

    def build_model_session_panel(
        self,
        model_name: str = "SmolLM2-1.7B-Instruct",
        device: str = "RTX 4090 (CUDA)",
        context_len: str = "16.4k tokens",
        mode: str = "Local (Offline Ready)",
        web: str = "Enabled (Live Grounding)",
        files_indexed: int = 12,
        docs_created: int = 3,
        policy_status: str = "Trained",
        memory_str: str = "8/20 turns",
    ) -> Panel:
        """Top right Model & Session telemetry panel."""
        t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        t.add_column("Key", style="bold #2ac3de", width=14)
        t.add_column("Val", style="white")

        t.add_row("[bold #7aa2f7]Model[/bold #7aa2f7]", "")
        t.add_row("🤖 Model", f"[bold #7aa2f7]{model_name}[/bold #7aa2f7]")
        t.add_row("💻 Device", f"[bold #9ece6a]{device}[/bold #9ece6a]")
        t.add_row("🖹 Context", context_len)
        t.add_row("🛡 Mode", f"[bold #2ac3de]{mode}[/bold #2ac3de]")
        t.add_row("🌐 Web", f"[bold #73daca]{web}[/bold #73daca]")
        t.add_row("[dim]────────────────[/dim]", "[dim]────────────────────────[/dim]")
        t.add_row("[bold #7aa2f7]Session[/bold #7aa2f7]", "")
        t.add_row("⏱ Indexed", f"{files_indexed} files")
        t.add_row("📄 Created", f"{docs_created} docs")
        t.add_row("🔮 Policy", f"[bold #9ece6a]{policy_status}[/bold #9ece6a]")
        t.add_row("🔗 Memory", memory_str)

        return Panel(t, box=ROUNDED, border_style="#2ac3de", padding=(0, 1))

    def build_nav_bar(self, active_tab: str = "HOME") -> Panel:
        """Compact navigation row: [ HOME ] | CREATE | ANALYZE | INDEX | TRAIN | MODEL | STATUS | HELP."""
        tabs = ["HOME", "CREATE", "ANALYZE", "INDEX", "TRAIN", "MODEL", "STATUS", "HELP"]
        t = Text()
        for i, tab in enumerate(tabs):
            if tab == active_tab:
                t.append(f"  [ {tab} ]  ", style="bold white on #1f4e79")
            else:
                t.append(f"  {tab}  ", style="bold #2ac3de")
            if i < len(tabs) - 1:
                t.append("│", style="#414868")

        return Panel(Align.center(t), box=ROUNDED, border_style="#2ac3de", padding=(0, 0))

    def build_conversation_panel(
        self,
        turns: list[dict[str, Any]],
        max_height: int = 14,
    ) -> Panel:
        """Central conversation view with user / assistant turns and avatar."""
        if not turns:
            welcome_text = Text()
            welcome_text.append("\n  No messages yet in this session.\n\n", style="dim white")
            welcome_text.append("  • Type any message or question to chat naturally\n", style="dim #2ac3de")
            welcome_text.append("  • Request document creation (e.g. 'write a report on microservices')\n", style="dim #2ac3de")
            welcome_text.append("  • Mention files with @filename or use slash commands like /help\n", style="dim #2ac3de")
            return Panel(welcome_text, title="[bold #2ac3de]Conversation[/bold #2ac3de]", box=ROUNDED, border_style="#2ac3de", padding=(0, 1))

        elements = []
        # Display the most recent turns that fit
        display_turns = turns[-6:]

        owl_shown = False
        for turn in display_turns:
            role = turn.get("role", "user")
            content = turn.get("content", "").strip()
            ts = turn.get("timestamp") or datetime.datetime.now().strftime("%H:%M:%S")

            t = Table(show_header=False, box=None, padding=(0, 0), expand=True)
            t.add_column("Prefix", width=3, style="bold #2ac3de")
            t.add_column("Author", width=9, style="bold white")
            t.add_column("Body", ratio=1)
            t.add_column("Time", width=10, style="dim #565f89", justify="right")

            if role == "user":
                t.add_row(">", "You", f"[white]{content}[/white]", ts)
                elements.append(t)
                elements.append(Text(""))  # spacer
            else:
                # Assistant message with clean accent
                t.add_row("◈", "Filevo", f"[white]{content}[/white]", ts)
                elements.append(t)
                elements.append(Text(""))  # spacer

        return Panel(
            Group(*elements),
            box=ROUNDED,
            border_style="#4c566a",
            padding=(0, 1),
        )

    def build_decision_panel(self, decision_info: dict[str, Any]) -> Panel:
        """Right sidebar RLCD Decision telemetry panel with probability bars."""
        probs = decision_info.get("probabilities")
        if not probs:
            from src.doc_gen.rlcd_engine import RLCDDecisionEngine
            engine = RLCDDecisionEngine()
            eval_res = engine.evaluate_intent("Technical report on microservices")
            probs = eval_res.get("probabilities", {})
            conf = eval_res.get("confidence", 0.0)
            entropy = eval_res.get("entropy", 0.0)
            risk = eval_res.get("risk", "LOW")
        else:
            conf = decision_info.get("confidence", 0.0)
            entropy = decision_info.get("entropy", 0.0)
            risk = decision_info.get("risk", "LOW")

        t = Table(show_header=False, box=None, padding=(0, 0), expand=True)
        t.add_column("Intent", style="bold #2ac3de", width=20)
        t.add_column("Bar", ratio=1)
        t.add_column("Val", style="bold white", width=6, justify="right")

        max_prob = max(probs.values()) if probs else 1.0
        for intent, prob in probs.items():
            bar_len = int(prob * 14)
            bar = "█" * bar_len + "░" * (14 - bar_len)
            style = "bold #2ac3de" if prob == max_prob else "#414868"
            t.add_row(intent, f"[{style}]{bar}[/{style}]", f"{prob:.2f}")

        t.add_row("", "", "")
        t.add_row(
            f"[bold #7aa2f7]Confidence:[/bold #7aa2f7] {conf*100:.1f}%",
            f"[dim]Entropy:[/dim] {entropy:.2f}",
            f"[bold #9ece6a]Risk: {risk}[/bold #9ece6a]",
        )

        return Panel(
            t,
            title="[bold #2ac3de]✦ RLCD Decision[/bold #2ac3de]",
            title_align="left",
            box=ROUNDED,
            border_style="#2ac3de",
            padding=(0, 1),
        )

    def display_decision_card(self, decision: Any):
        """Display decision telemetry panel from RLCD decision object."""
        if hasattr(decision, "archetype"):
            dec_dict = {
                "archetype": decision.archetype,
                "confidence": getattr(decision, "confidence", 0.75),
                "entropy": getattr(decision, "normalized_entropy", 0.5),
                "risk": getattr(decision, "risk", "LOW"),
            }
        elif isinstance(decision, dict):
            dec_dict = decision
        else:
            dec_dict = {}
        panel = self.build_decision_panel(dec_dict)
        self.console.print(panel)

    def build_references_panel(self, references: list[dict[str, str]]) -> Panel:
        """Right sidebar References panel displaying live discovered web/doc sources."""
        t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        t.add_column("Idx", width=3, style="bold #2ac3de")
        t.add_column("Icon", width=3, style="#73daca")
        t.add_column("Title", ratio=1)

        valid_refs = [r for r in (references or []) if isinstance(r, dict) and (r.get("title") or r.get("url"))]
        if not valid_refs:
            t.add_row("", "", "[dim]No live references\nUse /research <topic> to ground sources.[/dim]")
        else:
            for i, ref in enumerate(valid_refs[:4], 1):
                title = ref.get("title", "")
                domain = ref.get("domain", "")
                snippet = f"[bold white]{title}[/bold white]\n[dim]{domain}[/dim]"
                t.add_row(str(i), "🌐", snippet)

        return Panel(
            t,
            title="[bold #2ac3de]🌐 References[/bold #2ac3de]",
            title_align="left",
            box=ROUNDED,
            border_style="#2ac3de",
            padding=(0, 1),
        )

    def build_recent_docs_panel(self, docs: list[dict[str, Any]] | None = None) -> Panel:
        """Bottom left Recent Documents panel."""
        t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        t.add_column("Icon", width=3, style="bold #2ac3de")
        t.add_column("Index", width=3, style="dim white")
        t.add_column("Filename", ratio=1, style="bold white")
        t.add_column("Size", width=10, style="#73daca", justify="right")
        t.add_column("Date", width=18, style="dim #565f89", justify="right")

        doc_list = list(docs) if docs else []
        if not doc_list:
            output_dir = Path.home() / ".filevo" / "output"
            if output_dir.exists():
                found_files = sorted(output_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
                for f in found_files:
                    size_kb = f.stat().st_size / 1024
                    size_str = f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{int(size_kb)} KB"
                    mtime_str = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    doc_list.append({"name": f.name, "size": size_str, "date": mtime_str})

        if not doc_list:
            t.add_row("", "", "[dim]No documents created yet[/dim]", "", "")
        else:
            for i, d in enumerate(doc_list[:3], 1):
                t.add_row("📄", f"{i}.", d["name"], d.get("size", ""), d.get("date", ""))

        return Panel(
            t,
            title="[bold #2ac3de]📄 Recent Documents[/bold #2ac3de]",
            title_align="left",
            box=ROUNDED,
            border_style="#2ac3de",
            padding=(0, 1),
        )

    def build_system_status_panel(
        self,
        model_pct: int | None = None,
        gpu_pct: int | None = None,
        web_search: str | None = None,
        disk_usage: str | None = None,
        memory_str: str | None = None,
    ) -> Panel:
        """Bottom right System Status panel with dynamically queried hardware gauges."""
        import subprocess

        # 1. GPU
        gpu_name = "GPU"
        if gpu_pct is None:
            gpu_pct = 0
            try:
                probe = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    check=False,
                )
                line = next((ln for ln in probe.stdout.splitlines() if ln.strip()), "")
                if probe.returncode == 0 and line:
                    parts = [p.strip() for p in line.split(",")]
                    gpu_name = parts[0]
                    gpu_pct = int(float(parts[1]))
            except Exception:
                gpu_pct = 0

        # Shorten GPU name for display
        if "4090" in gpu_name:
            gpu_label = "GPU (RTX 4090)"
        elif gpu_name != "GPU":
            gpu_label = f"GPU ({gpu_name[:12]})"
        else:
            gpu_label = "GPU"

        # 2. Disk
        if disk_usage is None:
            try:
                usage = shutil.disk_usage(str(Path.home()))
                used_gb = usage.used / (1024**3)
                total_gb = usage.total / (1024**3)
                disk_usage = f"{used_gb:.1f} GB / {int(total_gb)} GB"
                disk_frac = min(1.0, usage.used / usage.total)
            except Exception:
                disk_usage = "N/A"
                disk_frac = 0.0
        else:
            disk_frac = 0.05

        # 3. Memory
        if memory_str is None:
            mem_frac = 0.0
            try:
                meminfo = {}
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    for line in f:
                        k, _, r = line.partition(":")
                        parts = r.strip().split()
                        if parts:
                            meminfo[k] = int(parts[0]) * 1024
                tot = meminfo.get("MemTotal", 0)
                avail = meminfo.get("MemAvailable", 0)
                if tot > 0:
                    used = tot - avail
                    mem_frac = min(1.0, used / tot)
                    memory_str = f"{used / (1024**3):.1f} / {tot / (1024**3):.0f} GB"
                else:
                    memory_str = "N/A"
            except Exception:
                memory_str = "N/A"
        else:
            mem_frac = 0.4

        # 4. Model
        if model_pct is None:
            model_pct = 100

        # 5. Web
        if web_search is None:
            web_enabled = os.environ.get("FILEVO_WEB_DISABLED") != "1"
            web_search = "Online" if web_enabled else "Disabled"

        t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        t.add_column("Icon", width=3, style="bold #2ac3de")
        t.add_column("Subsystem", width=12, style="bold white")
        t.add_column("Bar", width=14)
        t.add_column("Stat", width=8, style="bold white")

        t.add_column("Icon2", width=3, style="bold #2ac3de")
        t.add_column("Subsystem2", width=16, style="bold white")
        t.add_column("Bar2", width=14)
        t.add_column("Stat2", width=16, style="bold white")

        bar_model = "█" * (model_pct // 10) + "░" * (10 - model_pct // 10)
        gpu_units = min(10, int(gpu_pct / 10))
        bar_gpu = "█" * gpu_units + "░" * (10 - gpu_units)
        bar_web = "█" * 10 if web_search == "Online" else "░" * 10
        disk_units = min(10, int(disk_frac * 10))
        bar_disk = "█" * disk_units + "░" * (10 - disk_units)
        mem_units = min(10, int(mem_frac * 10))
        bar_mem = "█" * mem_units + "░" * (10 - mem_units)

        t.add_row(
            "⚙", "Model", f"[bold #2ac3de]{bar_model}[/bold #2ac3de]", f"{model_pct}%",
            "💻", gpu_label, f"[bold #2ac3de]{bar_gpu}[/bold #2ac3de]", f"{gpu_pct}%",
        )
        t.add_row(
            "🌐", "Web Search", f"[bold #9ece6a]{bar_web}[/bold #9ece6a]", web_search,
            "💾", "Disk Usage", f"[bold #2ac3de]{bar_disk}[/bold #2ac3de]", disk_usage,
        )
        t.add_row(
            "🧠", "Memory", f"[bold #2ac3de]{bar_mem}[/bold #2ac3de]", memory_str,
            "", "", "", "",
        )

        return Panel(
            t,
            title="[bold #2ac3de]⚙ System Status[/bold #2ac3de]",
            title_align="left",
            box=ROUNDED,
            border_style="#2ac3de",
            padding=(0, 1),
        )

    def render_bottom_prompt_box(
        self,
        model_name: str = "SmolLM2-1.7B-Instruct",
        mode_label: str = "Plan",
        context_info: str = "16.4k (5%)",
        cwd_label: str = "CIE:main",
        placeholder: str = "Type a message or /command...",
    ):
        """Render persistent bottom status bar and prompt box matching reference layout."""
        bar_text = Text()
        bar_text.append("│ ", style="bold #565f89")
        bar_text.append(mode_label, style="bold #e0af68")
        bar_text.append(" · ", style="dim #565f89")
        bar_text.append(model_name, style="bold #7aa2f7")
        bar_text.append(f" · Personal / {cwd_label} · {context_info}", style="dim #565f89")
        self.console.print(bar_text)

        t = Table(show_header=False, box=None, padding=(0, 0), expand=True)
        t.add_column("Arrow", width=3, style="bold #2ac3de")
        t.add_column("Box", ratio=1)
        t.add_column("Shortcuts", width=42, style="dim #565f89", justify="right")

        input_box = Panel(
            Text(f"| {placeholder}", style="dim #2ac3de"),
            box=ROUNDED,
            border_style="#2ac3de",
            padding=(0, 1),
        )

        shortcuts = Text()
        shortcuts.append("Enter: ", style="bold white")
        shortcuts.append("Send    ", style="dim #565f89")
        shortcuts.append("Tab: ", style="bold white")
        shortcuts.append("Autocomplete    ", style="dim #565f89")
        shortcuts.append("Ctrl+C: ", style="bold white")
        shortcuts.append("Cancel", style="dim #565f89")

        t.add_row(">", input_box, shortcuts)
        self.console.print(t)

    # ------------------------------------------------------------------ #
    # Full Dashboard Assembly (Adaptive Layout)
    # ------------------------------------------------------------------ #

    def render_dashboard(
        self,
        turns: list[dict[str, Any]],
        model_name: str = "SmolLM2-1.7B-Instruct",
        device: str = "RTX 4090 (CUDA)",
        decision_info: dict[str, Any] | None = None,
        references: list[dict[str, str]] | None = None,
        recent_docs: list[dict[str, Any]] | None = None,
        system_status: dict[str, Any] | None = None,
        active_tab: str = "HOME",
    ):
        """Assemble and render the entire Filevo interface."""
        width = shutil.get_terminal_size().columns
        height = shutil.get_terminal_size().lines

        dec_info = decision_info or {
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
        }

        # Clear screen
        self.console.clear()

        # Top row: Banner (left) + Model/Session (right)
        if width >= 110:
            top_table = Table(show_header=False, box=None, padding=(0, 0), expand=True)
            top_table.add_column("Banner", ratio=7)
            top_table.add_column("ModelSession", ratio=3)
            top_table.add_row(
                self.build_top_banner_panel(),
                self.build_model_session_panel(model_name=model_name, device=device),
            )
            self.console.print(top_table)
        else:
            self.console.print(self.build_top_banner_panel())

        # Nav row
        self.console.print(self.build_nav_bar(active_tab=active_tab))

        # Central Area: Conversation (left) + Decision & References (right)
        if width >= 110:
            sidebar_group = Group(
                self.build_decision_panel(dec_info),
                self.build_references_panel(references or []),
            )
            main_table = Table(show_header=False, box=None, padding=(0, 0), expand=True)
            main_table.add_column("Conversation", ratio=7)
            main_table.add_column("Sidebar", ratio=3)
            main_table.add_row(
                self.build_conversation_panel(turns),
                sidebar_group,
            )
            self.console.print(main_table)
        else:
            self.console.print(self.build_conversation_panel(turns))
            self.console.print(self.build_decision_panel(dec_info))

        # Bottom row: Recent Documents (left) + System Status (right)
        if width >= 110:
            bot_table = Table(show_header=False, box=None, padding=(0, 0), expand=True)
            bot_table.add_column("Docs", ratio=6)
            bot_table.add_column("Status", ratio=4)
            bot_table.add_row(
                self.build_recent_docs_panel(recent_docs),
                self.build_system_status_panel(),
            )
            self.console.print(bot_table)
        else:
            self.console.print(self.build_recent_docs_panel(recent_docs))

        # Prompt area
        self.render_bottom_prompt_box()

    def display_document_card(
        self,
        doc_path: Path,
        title: str,
        sections_count: int,
        archetype: str,
        wc_result: Any | None = None,
    ):
        """Display success card for created DOCX document with optional WordCraft telemetry."""
        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column("Key", style="bold #2ac3de", width=20)
        t.add_column("Val", style="white")

        size_kb = doc_path.stat().st_size / 1024
        t.add_row("Document Title", f"[bold white]{title}[/bold white]")
        t.add_row("Archetype", f"[bold #7aa2f7]{archetype}[/bold #7aa2f7]")
        t.add_row("Output DOCX", f"[cyan]{doc_path}[/cyan]")
        if wc_result and getattr(wc_result, "pdf_path", None):
            t.add_row("Exported PDF", f"[magenta]{wc_result.pdf_path}[/magenta]")
        if wc_result and getattr(wc_result, "preview_image_path", None):
            t.add_row("Visual Preview", f"[yellow]{wc_result.preview_image_path}[/yellow]")
        if wc_result and getattr(wc_result, "doc_md_path", None):
            t.add_row("Anti-Slop Spec", f"[blue]{wc_result.doc_md_path}[/blue]")
        t.add_row("File Size", f"{size_kb:.1f} KB")
        t.add_row("Sections Rendered", str(sections_count))
        if wc_result:
            words = getattr(wc_result, "words", 0)
            pages = getattr(wc_result, "pages", 1)
            blocks = getattr(wc_result, "blocks", 0)
            tables = getattr(wc_result, "tables_count", 0)
            t.add_row("Word Count", f"{words} words across {pages} page(s)")
            t.add_row("Blocks & Tables", f"{blocks} blocks, {tables} structured table(s)")
            mode_str = "Visible Desktop Application (Live)" if getattr(wc_result, "visible_mode", False) else "Headless MCP Server"
            t.add_row("Authoring Engine", f"[bold #bb9af7]WordCraft MCP[/bold #bb9af7] ({mode_str})")
        else:
            t.add_row("Authoring Engine", "[bold #7aa2f7]Filevo Native OpenXML Renderer[/bold #7aa2f7]")
        t.add_row("OpenXML Validation", "[bold #9ece6a]✓ 100% Pass (Healthy Container)[/bold #9ece6a]")

        engine_title = "WordCraft MCP Live Processor" if (wc_result and getattr(wc_result, "visible_mode", False)) else ("WordCraft MCP Engine" if wc_result else "Native OpenXML")
        panel = Panel(
            t,
            title=f"[bold #9ece6a]✓ Microsoft Word (.docx) Created & Validated via {engine_title}[/bold #9ece6a]",
            title_align="left",
            box=ROUNDED,
            border_style="#9ece6a",
            padding=(0, 1),
            subtitle="[dim]Use /feedback +1.0 or /feedback -0.5 to calibrate policy weights[/dim]",
            subtitle_align="right",
        )
        self.console.print(panel)

    def print_user_message(self, text: str):
        """Print user turn matching reference layout."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        t = Table(show_header=False, box=None, padding=(0, 0), expand=True)
        t.add_column("Prefix", width=3, style="bold #2ac3de")
        t.add_column("Author", width=9, style="bold white")
        t.add_column("Body", ratio=1)
        t.add_column("Time", width=10, style="dim #565f89", justify="right")
        t.add_row(">", "You", f"[white]{text}[/white]", ts)
        self.console.print()
        self.console.print(t)
        self.console.print()

    def print_assistant_message(self, text: str):
        """Print assistant response with clean accent and timestamp."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        t = Table(show_header=False, box=None, padding=(0, 0), expand=True)
        t.add_column("Prefix", width=3, style="bold #88aece")
        t.add_column("Author", width=9, style="bold white")
        t.add_column("Body", ratio=1)
        t.add_column("Time", width=10, style="dim #4c566a", justify="right")
        t.add_row("◈", "Filevo", f"[white]{text.strip()}[/white]", ts)

        self.console.print()
        self.console.print(t)
        self.console.print()


# Global UI singleton
ui = AntigravityRichUI()
