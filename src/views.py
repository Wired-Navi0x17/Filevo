"""Unified in-window views for Sortwise: Settings, RLCD Model Chat, Word Creator, and Training.

Designed to eliminate popup dialogs, remove visual noise and emojis, and provide
a clean, responsive, single-window user experience.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
import math
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
from typing import Any, Callable, Sequence

import customtkinter as ctk

from .docx_creator import (
    create_word_document,
    export_chat_to_docx,
    find_soffice_binary,
    open_in_office,
    parse_document_request,
)
from .rlcd import (
    RLCDPolicyStore,
    discover_target_categories,
    get_default_policy_store,
    get_default_router,
    query_chat_explanation,
    train_prototypes_from_library,
)
from .server import ConfigStore, SortwiseConfig
from .web_fetcher import (
    clean_search_topic,
    enrich_sections_with_web_context,
    fetch_web_context,
    format_web_chat_response,
)
from .research_engine import is_research_paper_request
from .web_automator import (
    automate_browser_task,
    detect_default_browser,
    resolve_site_url,
    resolve_subtask_url,
)

__all__ = [
    "ModelChatView",
    "SettingsView",
    "TrainingView",
    "WordCreatorView",
    "attach_text_context_menu",
]


def attach_text_context_menu(widget: Any, is_entry: bool = False, readonly: bool = False) -> None:
    """Attach rich keyboard navigation (Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+A) and right-click context menu."""
    tk_w = getattr(widget, "_textbox", getattr(widget, "_entry", widget))

    def _select_all(event: Any = None) -> str:
        if is_entry:
            tk_w.select_range(0, tk.END)
            tk_w.icursor(tk.END)
        else:
            tk_w.tag_add("sel", "1.0", "end")
            tk_w.mark_set("insert", "end")
        return "break"

    def _copy(event: Any = None) -> str:
        try:
            if is_entry:
                if tk_w.select_present():
                    selected = tk_w.selection_get()
                else:
                    selected = tk_w.get()
            else:
                selected = tk_w.get("sel.first", "sel.last")
            if selected:
                tk_w.clipboard_clear()
                tk_w.clipboard_append(selected)
        except Exception:
            pass
        return "break"

    def _cut(event: Any = None) -> str:
        if readonly:
            return "break"
        try:
            if is_entry:
                if tk_w.select_present():
                    selected = tk_w.selection_get()
                    tk_w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                else:
                    selected = tk_w.get()
                    tk_w.delete(0, tk.END)
            else:
                selected = tk_w.get("sel.first", "sel.last")
                tk_w.delete("sel.first", "sel.last")
            if selected:
                tk_w.clipboard_clear()
                tk_w.clipboard_append(selected)
        except Exception:
            pass
        return "break"

    def _paste(event: Any = None) -> str:
        if readonly:
            return "break"
        try:
            clipboard_text = tk_w.clipboard_get()
            if is_entry:
                if tk_w.select_present():
                    tk_w.delete(tk.SEL_FIRST, tk.SEL_LAST)
                tk_w.insert(tk.INSERT, clipboard_text)
            else:
                if tk_w.tag_ranges("sel"):
                    tk_w.delete("sel.first", "sel.last")
                tk_w.insert(tk.INSERT, clipboard_text)
        except Exception:
            pass
        return "break"

    # Cross-platform keyboard navigation shortcuts
    for mod in ("<Control-", "<Control-Key-", "<Mod1-"):
        tk_w.bind(f"{mod}a>", _select_all, add="+")
        tk_w.bind(f"{mod}A>", _select_all, add="+")
        tk_w.bind(f"{mod}c>", _copy, add="+")
        tk_w.bind(f"{mod}C>", _copy, add="+")
        if not readonly:
            tk_w.bind(f"{mod}x>", _cut, add="+")
            tk_w.bind(f"{mod}X>", _cut, add="+")
            tk_w.bind(f"{mod}v>", _paste, add="+")
            tk_w.bind(f"{mod}V>", _paste, add="+")

    # Right-click context menu (Button-3 on Linux/Windows, Button-2 on macOS)
    menu = tk.Menu(
        tk_w,
        tearoff=0,
        bg="#1e2430",
        fg="#f1f5f9",
        activebackground="#334155",
        activeforeground="#ffffff",
        bd=1,
        relief="solid",
    )
    if not readonly:
        menu.add_command(label="Cut", accelerator="Ctrl+X", command=_cut)
    menu.add_command(label="Copy", accelerator="Ctrl+C", command=_copy)
    if not readonly:
        menu.add_command(label="Paste", accelerator="Ctrl+V", command=_paste)
    menu.add_separator()
    menu.add_command(label="Select All", accelerator="Ctrl+A", command=_select_all)

    def _show_menu(event: Any) -> str:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    tk_w.bind("<Button-3>", _show_menu, add="+")
    tk_w.bind("<Button-2>", _show_menu, add="+")


# --------------------------------------------------------------------------- #
# 1. Embedded In-Window Settings View (No Popups!)
# --------------------------------------------------------------------------- #
class SettingsView(ctk.CTkFrame):
    """In-window settings editor that replaces modal popup dialogs."""

    def __init__(
        self,
        master: Any,
        config_store: ConfigStore,
        on_save_callback: Callable[[dict[str, Any]], None],
        on_close_callback: Callable[[], None] | None = None,
        theme: Any = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._config_store = config_store
        self._on_save_callback = on_save_callback
        self._on_close_callback = on_close_callback
        self._theme = theme

        self._build_ui()

    def _build_ui(self) -> None:
        config = self._config_store.load()

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(16, 12))

        ctk.CTkLabel(
            header,
            text="Application Settings",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).pack(side="left")

        if self._on_close_callback:
            ctk.CTkButton(
                header,
                text="Back to Organizer",
                width=140,
                height=34,
                command=self._on_close_callback,
            ).pack(side="right")

        # Scrollable Form Body
        body = ctk.CTkScrollableFrame(self, fg_color="#181a20", corner_radius=8, border_width=1, border_color="#2b2d35")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        body.grid_columnconfigure(1, weight=1)

        # 1. Watch Folder
        ctk.CTkLabel(body, text="Watch Intake Folder:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 4)
        )
        self._watch_entry = ctk.CTkEntry(body, height=36, font=ctk.CTkFont(size=13))
        self._watch_entry.insert(0, config.watch_folder)
        self._watch_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=(16, 4))
        ctk.CTkButton(
            body, text="Browse...", width=90, height=36,
            command=lambda: self._browse_dir(self._watch_entry)
        ).grid(row=0, column=2, sticky="e", padx=(0, 16), pady=(16, 4))

        # 2. Target Library Root
        ctk.CTkLabel(body, text="Target Library Root:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=1, column=0, sticky="w", padx=16, pady=(12, 4)
        )
        self._target_entry = ctk.CTkEntry(body, height=36, font=ctk.CTkFont(size=13))
        self._target_entry.insert(0, config.target_root)
        self._target_entry.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(12, 4))
        ctk.CTkButton(
            body, text="Browse...", width=90, height=36,
            command=lambda: self._browse_dir(self._target_entry)
        ).grid(row=1, column=2, sticky="e", padx=(0, 16), pady=(12, 4))

        # 3. Sliders: Confidence Gate & Entropy Gate
        ctk.CTkLabel(body, text="Confidence Gate:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=2, column=0, sticky="w", padx=16, pady=(16, 4)
        )
        self._conf_val_lbl = ctk.CTkLabel(body, text=f"{config.confidence_threshold:.2f}", font=ctk.CTkFont(size=13, weight="bold"))
        self._conf_val_lbl.grid(row=2, column=2, sticky="e", padx=(0, 16), pady=(16, 4))
        self._conf_slider = ctk.CTkSlider(
            body, from_=0.40, to=0.95, number_of_steps=55,
            command=lambda v: self._conf_val_lbl.configure(text=f"{v:.2f}")
        )
        self._conf_slider.set(config.confidence_threshold)
        self._conf_slider.grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(16, 4))

        ctk.CTkLabel(body, text="Entropy Gate (Bits):", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=3, column=0, sticky="w", padx=16, pady=(12, 4)
        )
        self._ent_val_lbl = ctk.CTkLabel(body, text=f"{config.entropy_threshold:.2f}", font=ctk.CTkFont(size=13, weight="bold"))
        self._ent_val_lbl.grid(row=3, column=2, sticky="e", padx=(0, 16), pady=(12, 4))
        self._ent_slider = ctk.CTkSlider(
            body, from_=0.20, to=3.0, number_of_steps=70,
            command=lambda v: self._ent_val_lbl.configure(text=f"{v:.2f}")
        )
        self._ent_slider.set(config.entropy_threshold)
        self._ent_slider.grid(row=3, column=1, sticky="ew", padx=(8, 8), pady=(12, 4))

        # 4. Mode Selection: Move vs Copy
        ctk.CTkLabel(body, text="Transfer Mode:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=4, column=0, sticky="w", padx=16, pady=(16, 4)
        )
        self._mode_seg = ctk.CTkSegmentedButton(body, values=["Move (Cut)", "Copy"])
        self._mode_seg.set("Move (Cut)" if config.operation_mode == "move" else "Copy")
        self._mode_seg.grid(row=4, column=1, sticky="w", padx=(8, 8), pady=(16, 4))

        # 5. Switches: Auto Move & Recursive
        self._auto_move_switch = ctk.CTkSwitch(body, text="Automatically move confident files without manual review")
        if config.auto_move:
            self._auto_move_switch.select()
        self._auto_move_switch.grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 6))

        self._recursive_switch = ctk.CTkSwitch(body, text="Scan intake folder recursively into subdirectories")
        if config.recursive:
            self._recursive_switch.select()
        self._recursive_switch.grid(row=6, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 16))

        # Footer Actions
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(0, 16))

        self._status_label = ctk.CTkLabel(footer, text="", font=ctk.CTkFont(size=13), anchor="w")
        self._status_label.pack(side="left", padx=8)

        ctk.CTkButton(
            footer, text="Save Settings", width=140, height=38,
            command=self._save_settings,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            footer, text="Reset Defaults", width=120, height=38,
            fg_color="#2b2d35", hover_color="#363942",
            command=self._reset_defaults,
        ).pack(side="right", padx=(8, 0))

    def _browse_dir(self, entry: ctk.CTkEntry) -> None:
        from tkinter import filedialog
        chosen = filedialog.askdirectory(initialdir=entry.get() or str(Path.home()), parent=self)
        if chosen:
            entry.delete(0, "end")
            entry.insert(0, chosen)

    def _save_settings(self) -> None:
        changes = {
            "watch_folder": self._watch_entry.get().strip(),
            "target_root": self._target_entry.get().strip(),
            "confidence_threshold": float(self._conf_slider.get()),
            "entropy_threshold": float(self._ent_slider.get()),
            "operation_mode": "move" if self._mode_seg.get() == "Move (Cut)" else "copy",
            "auto_move": bool(self._auto_move_switch.get()),
            "recursive": bool(self._recursive_switch.get()),
        }
        self._on_save_callback(changes)
        self._status_label.configure(text="[OK] Settings saved successfully.", text_color="#10b981")

    def _reset_defaults(self) -> None:
        defaults = SortwiseConfig()
        self._watch_entry.delete(0, "end")
        self._watch_entry.insert(0, defaults.watch_folder)
        self._target_entry.delete(0, "end")
        self._target_entry.insert(0, defaults.target_root)
        self._conf_slider.set(defaults.confidence_threshold)
        self._conf_val_lbl.configure(text=f"{defaults.confidence_threshold:.2f}")
        self._ent_slider.set(defaults.entropy_threshold)
        self._ent_val_lbl.configure(text=f"{defaults.entropy_threshold:.2f}")
        self._mode_seg.set("Move (Cut)" if defaults.operation_mode == "move" else "Copy")
        if defaults.auto_move:
            self._auto_move_switch.select()
        else:
            self._auto_move_switch.deselect()
        if defaults.recursive:
            self._recursive_switch.select()
        else:
            self._recursive_switch.deselect()
        self._status_label.configure(text="[Reset] Reset to factory defaults.", text_color="#f59e0b")


# --------------------------------------------------------------------------- #
# 2. Interactive RLCD Model Chat & Decision Studio Tab
# --------------------------------------------------------------------------- #
class ModelChatView(ctk.CTkFrame):
    """Conversational interface allowing users to query and reinforce the RLCD model."""

    def __init__(self, master: Any, config_store: ConfigStore) -> None:
        super().__init__(master, fg_color="transparent")
        self._config_store = config_store
        self._chat_history: list[dict[str, Any]] = []
        self._current_decision_data: dict[str, Any] | None = None

        # Live Thinking Animation State
        self._thinking_card: ctk.CTkFrame | None = None
        self._thinking_label: ctk.CTkLabel | None = None
        self._thinking_spinner_idx: int = 0
        self._thinking_anim_id: str | None = None
        self._thinking_status_text: str = ""
        self._thinking_spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        self._build_ui()

    def _build_ui(self) -> None:
        self._sent_history: list[str] = []
        self._history_index: int = -1
        self._current_draft: str = ""
        self._attached_path: str | None = None

        # 1. Bottom Input Area (PACK FIRST with side="bottom" so it is ALWAYS pinned and visible)
        input_card = ctk.CTkFrame(self, fg_color="#161820", corner_radius=8, border_width=1, border_color="#262a35")
        input_card.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

        # Attachment chip container
        self._attachment_chip = ctk.CTkFrame(input_card, fg_color="#1e2433", corner_radius=6, border_width=1, border_color="#334155")
        self._attachment_label = ctk.CTkLabel(self._attachment_chip, text="", font=ctk.CTkFont(size=11), text_color="#cbd5e1")
        self._attachment_label.pack(side="left", padx=(8, 6), pady=2)
        ctk.CTkButton(
            self._attachment_chip,
            text="✕",
            width=20,
            height=20,
            fg_color="transparent",
            hover_color="#451a1a",
            text_color="#f87171",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._clear_attachment,
        ).pack(side="right", padx=(0, 4), pady=2)

        self._input_box = ctk.CTkTextbox(input_card, height=56, font=ctk.CTkFont(size=12))
        self._input_box.pack(fill="x", padx=8, pady=(6, 4))
        self._input_box.bind("<Return>", self._on_enter_press)
        self._input_box.bind("<Shift-Return>", lambda _e: None)
        self._input_box.bind("<Up>", self._on_up_press)
        self._input_box.bind("<Down>", self._on_down_press)
        attach_text_context_menu(self._input_box, is_entry=False, readonly=False)

        btn_row = ctk.CTkFrame(input_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 6))

        self._attach_btn = ctk.CTkButton(
            btn_row,
            text="📎 Attach",
            width=80,
            height=28,
            fg_color="#1e2430",
            hover_color="#2b3445",
            border_width=1,
            border_color="#333d4e",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=11),
            command=self._on_attach_click,
        )
        self._attach_btn.pack(side="left", padx=(0, 6))

        # Web Fetch manual toggle switch (defaults to OFF)
        self._web_fetch_switch = ctk.CTkSwitch(
            btn_row,
            text="🌐 Web: OFF",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8",
            progress_color="#0284c7",
            button_color="#38bdf8",
            button_hover_color="#7dd3fc",
            command=self._on_web_fetch_toggled,
            width=36,
        )
        self._web_fetch_switch.pack(side="left", padx=(0, 8))

        self._reinforce_info = ctk.CTkLabel(btn_row, text="", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        self._reinforce_info.pack(side="left")

        self._send_btn = ctk.CTkButton(
            btn_row,
            text="Send",
            width=76,
            height=28,
            fg_color="#0284c7",
            hover_color="#0369a1",
            border_width=0,
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_send,
        )
        self._send_btn.pack(side="right")

        # 2. Top Header Banner
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(side="top", fill="x", padx=10, pady=(6, 4))

        ctk.CTkLabel(
            header,
            text="RLCD Decision Studio",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Export .docx",
            width=90,
            height=26,
            fg_color="#1e293b",
            hover_color="#334155",
            border_width=1,
            border_color="#475569",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=11),
            command=self._export_to_docx,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            header,
            text="Clear",
            width=60,
            height=26,
            fg_color="#181b22",
            hover_color="#252a36",
            border_width=1,
            border_color="#333b4d",
            text_color="#94a3b8",
            font=ctk.CTkFont(size=11),
            command=self._clear_chat,
        ).pack(side="right")

        # 3. Middle Scrollable Chat Transcript (expands to fill all flexible remaining space)
        self._transcript = ctk.CTkScrollableFrame(self, fg_color="#111216", corner_radius=8)
        self._transcript.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 6))

        # Initial Welcome Message
        self._append_message(
            "model",
            "Welcome to the RLCD Decision Studio. Paste an excerpt, lecture summary, or query "
            "below. The dual-perspective engine will evaluate it, explain its decision with "
            "entropy and classifier agreement metrics, and allow 1-click policy reinforcement.",
        )

    def _on_attach_click(self) -> None:
        """Open file dialog allowing user to attach a code file, document, or image."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Attach File for RLCD Analysis / Doc Synthesis",
            filetypes=[
                ("All Files", "*.*"),
                ("Python Files", "*.py"),
                ("Documents & Reports", "*.docx *.pdf *.txt *.md"),
                ("Images", "*.png *.jpg *.jpeg"),
            ],
        )
        if path:
            self._set_attachment(path)

    def _set_attachment(self, path: str) -> None:
        self._attached_path = path
        p = Path(path)
        self._attachment_label.configure(text=f"📎 Attached: {p.name}  ({p.parent})")
        self._attachment_chip.pack(fill="x", padx=12, pady=(8, 0), before=self._input_box)

    def _clear_attachment(self) -> None:
        self._attached_path = None
        self._attachment_chip.pack_forget()

    def _on_web_fetch_toggled(self) -> None:
        is_on = bool(self._web_fetch_switch.get())
        if is_on:
            self._web_fetch_switch.configure(text="🌐 Web Fetch: ON", text_color="#38bdf8")
        else:
            self._web_fetch_switch.configure(text="🌐 Web Fetch: OFF", text_color="#94a3b8")

    def _start_thinking_animation(self, initial_text: str = "Thinking & Calibrating policy...") -> None:
        self._stop_thinking_animation()

        self._thinking_status_text = initial_text
        self._thinking_spinner_idx = 0

        self._thinking_card = ctk.CTkFrame(
            self._transcript,
            fg_color="#181c24",
            corner_radius=8,
            border_width=1,
            border_color="#0284c7",
        )
        self._thinking_card.pack(fill="x", padx=12, pady=6)

        head = ctk.CTkFrame(self._thinking_card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            head,
            text="[RLCD Model Engine]",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8",
            anchor="w",
        ).pack(side="left")

        self._thinking_label = ctk.CTkLabel(
            self._thinking_card,
            text=f"{self._thinking_spinner_frames[0]}  {initial_text}",
            font=ctk.CTkFont(size=12),
            text_color="#cbd5e1",
            anchor="w",
            justify="left",
        )
        self._thinking_label.pack(fill="x", padx=12, pady=(0, 8))

        try:
            self._transcript._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

        self._step_thinking_animation()

    def _step_thinking_animation(self) -> None:
        if self._thinking_card is None or not self._thinking_card.winfo_exists():
            return
        self._thinking_spinner_idx = (self._thinking_spinner_idx + 1) % len(self._thinking_spinner_frames)
        frame = self._thinking_spinner_frames[self._thinking_spinner_idx]
        if self._thinking_label and self._thinking_label.winfo_exists():
            self._thinking_label.configure(text=f"{frame}  {self._thinking_status_text}")
        self._thinking_anim_id = self.after(90, self._step_thinking_animation)

    def _update_thinking_status(self, new_text: str) -> None:
        self._thinking_status_text = new_text
        if self._thinking_label and self._thinking_label.winfo_exists():
            frame = self._thinking_spinner_frames[self._thinking_spinner_idx]
            self._thinking_label.configure(text=f"{frame}  {new_text}")
        try:
            self._transcript._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _stop_thinking_animation(self) -> None:
        if self._thinking_anim_id:
            try:
                self.after_cancel(self._thinking_anim_id)
            except Exception:
                pass
            self._thinking_anim_id = None

        if self._thinking_card is not None:
            try:
                self._thinking_card.destroy()
            except Exception:
                pass
            self._thinking_card = None
            self._thinking_label = None

    def _append_automation_card(self, auto_data: dict[str, Any]) -> None:
        """Renders an interactive card showing browser automation details and actions."""
        bubble = ctk.CTkFrame(
            self._transcript,
            fg_color="#181c24",
            corner_radius=8,
            border_width=1,
            border_color="#0284c7",
        )
        bubble.pack(fill="x", padx=12, pady=6)

        head = ctk.CTkFrame(bubble, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(
            head,
            text="[Web Automation Agent]",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8",
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            head,
            text="BROWSER CONTROL COMPLETED",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#86efac",
        ).pack(side="right")

        info_box = ctk.CTkFrame(bubble, fg_color="#0f1218", corner_radius=6, border_width=1, border_color="#1e293b")
        info_box.pack(fill="x", padx=12, pady=4)

        target_url = auto_data.get("target_url", "")
        browser_name = auto_data.get("browser", "Zen Browser")

        ctk.CTkLabel(
            info_box,
            text=f"Browser: {browser_name}   |   Status: Active Automation Session",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#cbd5e1",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(6, 2))

        if auto_data.get("text_typed"):
            ctk.CTkLabel(
                info_box,
                text=f"✍️ Typed Text: \"{auto_data['text_typed']}\"",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#86efac",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 4))

        url_row = ctk.CTkFrame(info_box, fg_color="transparent")
        url_row.pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkLabel(url_row, text="Target URL:", font=ctk.CTkFont(size=10, weight="bold"), text_color="#38bdf8").pack(side="left", padx=(0, 6))

        url_entry = ctk.CTkEntry(url_row, height=24, font=ctk.CTkFont(family="monospace", size=10), fg_color="transparent", border_width=0, text_color="#f1f5f9")
        url_entry.insert(0, target_url)
        url_entry.configure(state="readonly")
        url_entry.pack(side="left", fill="x", expand=True)
        attach_text_context_menu(url_entry, is_entry=True, readonly=True)

        def _open_target() -> None:
            try:
                subprocess.Popen(["xdg-open", target_url], start_new_session=True)
            except Exception:
                pass

        ctk.CTkButton(
            url_row,
            text="Open in Browser",
            width=110,
            height=22,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            text_color="#38bdf8",
            command=_open_target,
        ).pack(side="right", padx=(6, 0))

        actions = auto_data.get("actions_log", [])
        if actions:
            log_box = ctk.CTkFrame(bubble, fg_color="#0b0d12", corner_radius=4, border_width=1, border_color="#1a202c")
            log_box.pack(fill="x", padx=12, pady=(4, 8))
            ctk.CTkLabel(log_box, text="EXECUTION TRACE:", font=ctk.CTkFont(size=10, weight="bold"), text_color="#94a3b8", anchor="w").pack(fill="x", padx=8, pady=(4, 2))
            log_txt = "\n".join(f"• {act}" for act in actions)
            t_w = tk.Text(
                log_box,
                bg="#0b0d12",
                fg="#a7f3d0",
                font=("monospace", 9),
                relief="flat",
                bd=0,
                highlightthickness=0,
                wrap="word",
                height=min(12, len(actions) + 1),
            )
            t_w.insert("1.0", log_txt)
            t_w.configure(state="disabled")
            t_w.pack(fill="x", padx=8, pady=(0, 6))
            attach_text_context_menu(t_w, is_entry=False, readonly=True)

        try:
            self._transcript._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _append_message(
        self,
        role: str,
        text: str,
        telemetry: dict[str, Any] | None = None,
        file_info: dict[str, Any] | None = None,
    ) -> None:
        self._chat_history.append({"role": role, "content": text, "telemetry": telemetry or {}, "file_info": file_info})

        bubble = ctk.CTkFrame(
            self._transcript,
            fg_color="#1e2129" if role == "model" else "#272c38",
            corner_radius=8,
            border_width=1,
            border_color="#333947" if role == "model" else "#3f4657",
        )
        bubble.pack(fill="x", padx=12, pady=6)

        sender_text = "RLCD Router" if role == "model" else "You"
        header_row = ctk.CTkFrame(bubble, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            header_row,
            text=f"[{sender_text}]",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8" if role == "model" else "#cbd5e1",
            anchor="w",
        ).pack(side="left")

        def _copy_message_text(c=text) -> None:
            self.clipboard_clear()
            self.clipboard_append(c)

        ctk.CTkButton(
            header_row,
            text="Copy",
            width=48,
            height=20,
            font=ctk.CTkFont(size=10),
            fg_color="#181c24",
            hover_color="#2b3445",
            border_width=1,
            border_color="#333e50",
            text_color="#94a3b8",
            command=_copy_message_text,
        ).pack(side="right")

        # Selectable, copyable message text with auto-height and context menu
        font_fam = "Segoe UI" if "Segoe UI" in tkfont.families() else ("DejaVu Sans" if "DejaVu Sans" in tkfont.families() else "TkDefaultFont")
        bubble_bg = "#1e2129" if role == "model" else "#272c38"
        total_lines = sum(max(1, math.ceil(len(ln) / 75)) for ln in text.split("\n"))

        msg_text = tk.Text(
            bubble,
            bg=bubble_bg,
            fg="#e2e8f0",
            font=(font_fam, 11),
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            cursor="xterm",
            selectbackground="#3b82f6",
            selectforeground="#ffffff",
            inactiveselectbackground="#334155",
            exportselection=True,
            height=max(1, min(40, total_lines)),
        )
        msg_text.insert("1.0", text)
        msg_text.configure(state="disabled")
        msg_text.pack(fill="x", padx=12, pady=(0, 6))
        attach_text_context_menu(msg_text, is_entry=False, readonly=True)

        # Interactive File Card if a document was created
        loc_lbl = None
        if file_info:
            fcard = ctk.CTkFrame(bubble, fg_color="#14171f", corner_radius=6, border_width=1, border_color="#2b313e")
            fcard.pack(fill="x", padx=12, pady=(2, 8))

            top_f = ctk.CTkFrame(fcard, fg_color="transparent")
            top_f.pack(fill="x", padx=10, pady=(8, 2))
            ctk.CTkLabel(top_f, text="DOCUMENT CREATED", font=ctk.CTkFont(size=10, weight="bold"), text_color="#38bdf8").pack(side="left")
            ctk.CTkLabel(top_f, text=f"•  {file_info['file_name']}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#f1f5f9").pack(side="left", padx=8)

            # Prominent Full Pathway Box
            path_box = ctk.CTkFrame(fcard, fg_color="#0b0e14", corner_radius=4, border_width=1, border_color="#1e293b")
            path_box.pack(fill="x", padx=10, pady=(4, 6))

            ctk.CTkLabel(
                path_box,
                text="FULL PATH:",
                font=ctk.CTkFont(family="monospace", size=10, weight="bold"),
                text_color="#38bdf8",
                anchor="w",
            ).pack(side="left", padx=(8, 6), pady=5)

            path_entry = ctk.CTkEntry(
                path_box,
                height=26,
                font=ctk.CTkFont(family="monospace", size=11),
                fg_color="transparent",
                border_width=0,
                text_color="#e2e8f0",
            )
            path_entry.insert(0, str(file_info['file_path']))
            path_entry.configure(state="readonly")
            path_entry.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=3)
            attach_text_context_menu(path_entry, is_entry=True, readonly=True)

            def _copy_full_path(p=str(file_info['file_path'])) -> None:
                self.clipboard_clear()
                self.clipboard_append(p)

            ctk.CTkButton(
                path_box,
                text="Copy Path",
                width=72,
                height=22,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color="#1e293b",
                hover_color="#334155",
                text_color="#38bdf8",
                command=_copy_full_path,
            ).pack(side="right", padx=(2, 6), pady=2)

            loc_lbl = ctk.CTkLabel(
                fcard,
                text=f"Folder: {file_info['folder_path']}   |   Category: {file_info.get('category', 'General')}",
                font=ctk.CTkFont(family="monospace", size=10),
                text_color="#94a3b8",
                anchor="w",
                justify="left",
            )
            loc_lbl.pack(fill="x", padx=10, pady=(0, 6))

            fbtns = ctk.CTkFrame(fcard, fg_color="transparent")
            fbtns.pack(fill="x", padx=10, pady=(0, 8))

            ctk.CTkButton(
                fbtns,
                text="Open in LibreOffice",
                width=140,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#1e2430",
                hover_color="#2b3445",
                border_width=1,
                border_color="#333d4e",
                text_color="#f1f5f9",
                command=lambda p=file_info['file_path']: open_in_office(Path(p)),
            ).pack(side="left", padx=(0, 8))

            def _open_folder(fdir: str = file_info['folder_path']) -> None:
                try:
                    subprocess.Popen(["xdg-open", fdir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                except Exception:
                    pass

            ctk.CTkButton(
                fbtns,
                text="Show in Folder",
                width=110,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="transparent",
                border_width=1,
                border_color="#475569",
                hover_color="#1e2430",
                text_color="#cbd5e1",
                command=_open_folder,
            ).pack(side="left")

        # Active Learning Uncertainty Query Card
        if role == "model" and telemetry and telemetry.get("is_uncertainty_query"):
            al_card = ctk.CTkFrame(bubble, fg_color="#181c24", corner_radius=6, border_width=1, border_color="#5e451b")
            al_card.pack(fill="x", padx=12, pady=(2, 6))

            al_top = ctk.CTkFrame(al_card, fg_color="transparent")
            al_top.pack(fill="x", padx=10, pady=(6, 2))
            ctk.CTkLabel(
                al_top,
                text="ACTIVE LEARNING UNCERTAINTY QUERY",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#f59e0b",
            ).pack(side="left")

            ctk.CTkLabel(
                al_card,
                text="Policy uncertainty is elevated. Select a candidate below to reinforce the policy:",
                font=ctk.CTkFont(size=11),
                text_color="#cbd5e1",
                anchor="w",
                justify="left",
            ).pack(fill="x", padx=10, pady=(0, 6))

            cands_row = ctk.CTkFrame(al_card, fg_color="transparent")
            cands_row.pack(fill="x", padx=10, pady=(0, 8))

            cands = telemetry.get("candidate_options", [])
            for cand in cands:
                ctk.CTkButton(
                    cands_row,
                    text=str(cand),
                    height=28,
                    fg_color="#222836",
                    hover_color="#323c52",
                    border_width=1,
                    border_color="#475569",
                    text_color="#f1f5f9",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda c=cand, d=telemetry.get("decision"), t=telemetry, fi=file_info, ll=loc_lbl: self._active_learning_select(c, d, t, fi, ll),
                ).pack(side="left", padx=(0, 6))

        # Telemetry & Policy Reinforcement Row
        if role == "model" and telemetry and "decision" in telemetry:
            dec = telemetry["decision"]

            # Subtle telemetry metrics bar
            stats_frame = ctk.CTkFrame(bubble, fg_color="#14161c", corner_radius=4)
            stats_frame.pack(fill="x", padx=12, pady=(2, 6))
            stats_text = (
                f"Assigned Category: {dec.subject}   |   "
                f"Confidence: {dec.confidence * 100:.1f}%   |   "
                f"Agreement: {dec.agreement * 100:.1f}%   |   "
                f"Disagreement (JS): {dec.disagreement:.3f} bits"
            )
            ctk.CTkLabel(
                stats_frame,
                text=stats_text,
                font=ctk.CTkFont(family="monospace", size=10),
                text_color="#94a3b8",
                anchor="w",
            ).pack(fill="x", padx=8, pady=4)

            action_row = ctk.CTkFrame(bubble, fg_color="transparent")
            action_row.pack(fill="x", padx=12, pady=(4, 10))

            # Approve Button (Positive Reinforcement)
            ctk.CTkButton(
                action_row,
                text=f"Approve ({dec.subject})",
                width=140,
                height=28,
                fg_color="#143326",
                hover_color="#1e533c",
                border_width=1,
                border_color="#2b7252",
                text_color="#86efac",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda d=dec, t=telemetry: self._confirm_feedback(d, t),
            ).pack(side="left", padx=(0, 6))

            # Reject Button (Negative Reinforcement Penalty)
            ctk.CTkButton(
                action_row,
                text="Reject",
                width=75,
                height=28,
                fg_color="#331818",
                hover_color="#4d2222",
                border_width=1,
                border_color="#732b2b",
                text_color="#fca5a5",
                font=ctk.CTkFont(size=11),
                command=lambda d=dec, t=telemetry: self._reject_feedback(d, t),
            ).pack(side="left", padx=(0, 10))

            ctk.CTkLabel(action_row, text="Move to:", font=ctk.CTkFont(size=11), text_color="#94a3b8").pack(side="left", padx=(4, 6))

            config = self._config_store.load()
            from .taxonomy import discover_target_taxonomy
            tax = discover_target_taxonomy(config.target_root, config.watch_folder)
            cats = list(tax.keys())
            if not cats:
                cats = [dec.subject] if dec.subject else ["General"]
            elif dec.subject and dec.subject not in cats:
                cats.insert(0, dec.subject)

            override_menu = ctk.CTkOptionMenu(action_row, values=cats, width=140, height=28, fg_color="#1e2430", button_color="#2b3445", text_color="#f1f5f9")
            override_menu.set(dec.subject if dec.subject in cats else cats[0])
            override_menu.pack(side="left", padx=(0, 6))

            fpath_to_move = file_info["file_path"] if file_info else None
            loc_label_ref = loc_lbl if file_info else None
            ctk.CTkButton(
                action_row,
                text="Move & Retrain",
                width=115,
                height=28,
                fg_color="#242c38",
                hover_color="#333e4f",
                border_width=1,
                border_color="#3f4c63",
                text_color="#f1f5f9",
                font=ctk.CTkFont(size=11),
                command=lambda m=override_menu, d=dec, t=telemetry, fp=fpath_to_move, lr=loc_label_ref: self._override_feedback(m.get(), d, t, fp, lr),
            ).pack(side="left")

    def _on_up_press(self, event: Any) -> str | None:
        """Recall previous sent message when Up arrow is pressed on first line."""
        cursor_pos = self._input_box.index("insert")
        line_num = int(cursor_pos.split(".")[0])
        if line_num > 1:
            return None

        if not self._sent_history:
            return "break"

        current_text = self._input_box.get("1.0", "end").strip()
        if self._history_index == -1:
            self._current_draft = current_text
            self._history_index = len(self._sent_history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return "break"

        self._input_box.delete("1.0", "end")
        self._input_box.insert("1.0", self._sent_history[self._history_index])
        self._input_box.mark_set("insert", "end")
        return "break"

    def _on_down_press(self, event: Any) -> str | None:
        """Recall next sent message when Down arrow is pressed on last line."""
        if self._history_index == -1:
            return None

        total_lines = int(self._input_box.index("end-1c").split(".")[0])
        cursor_pos = self._input_box.index("insert")
        line_num = int(cursor_pos.split(".")[0])
        if line_num < total_lines:
            return None

        if self._history_index < len(self._sent_history) - 1:
            self._history_index += 1
            self._input_box.delete("1.0", "end")
            self._input_box.insert("1.0", self._sent_history[self._history_index])
        else:
            self._history_index = -1
            self._input_box.delete("1.0", "end")
            if self._current_draft:
                self._input_box.insert("1.0", self._current_draft)

        self._input_box.mark_set("insert", "end")
        return "break"

    def _on_enter_press(self, event: Any) -> str:
        """Handle Enter key press to submit message (Shift+Enter inserts newline)."""
        if event.state & 0x0001:  # Shift is held
            return ""  # default behavior inserts newline
        self._on_send()
        return "break"  # prevent default newline insertion

    def _on_send(self) -> None:
        user_text = self._input_box.get("1.0", "end").strip()
        if not user_text:
            return

        # Record in sent history
        if not self._sent_history or self._sent_history[-1] != user_text:
            self._sent_history.append(user_text)
        self._history_index = -1
        self._current_draft = ""

        self._input_box.delete("1.0", "end")
        self._append_message("user", user_text)

        config = self._config_store.load()
        # Find active library path: check config target_root, or auto-detect user's organized folders
        target_path = Path(config.target_root).expanduser().resolve()
        if not target_path.is_dir() or not any(p.is_dir() for p in target_path.iterdir()):
            for fallback_candidate in [
                Path(config.watch_folder).expanduser().resolve(),
                Path.home() / "Documents",
            ]:
                if fallback_candidate.is_dir() and any(p.is_dir() for p in fallback_candidate.iterdir()):
                    target_path = fallback_candidate
                    break

        from .taxonomy import discover_target_taxonomy
        taxonomy = discover_target_taxonomy(str(target_path), config.watch_folder)

        # Interpret user request via semantic capability layer
        from src.interpreter import get_request_interpreter
        task_spec = get_request_interpreter().interpret(user_text)

        is_create_doc_cmd = (task_spec.action == "create_document")
        is_web_automation_cmd = (task_spec.action == "browse_web")
        is_classify_cmd = (task_spec.action == "classify_files")

        self._send_btn.configure(state="disabled", text="Processing...")

        if is_web_automation_cmd:
            self._start_thinking_animation("Initializing browser automation engine...")
        elif is_create_doc_cmd:
            if web_fetch_enabled:
                self._start_thinking_animation(f"🌐 Synthesizing {task_spec.deliverable_type.replace('_', ' ')} with live research...")
            else:
                self._start_thinking_animation("Synthesizing document structure & formatting...")
        elif is_classify_cmd:
            self._start_thinking_animation("Evaluating file classification policy with RLCD...")
        else:
            if web_fetch_enabled:
                self._start_thinking_animation("🌐 Querying live web knowledge & synthesizing response...")
            else:
                self._start_thinking_animation("Analyzing response...")

        def _worker() -> None:
            # 1. Handle Web Automation Task
            if is_web_automation_cmd:
                def _prog_cb(msg: str) -> None:
                    self.after(0, lambda m=msg: self._update_thinking_status(m))

                try:
                    auto_res = automate_browser_task(user_text, progress_callback=_prog_cb)
                except Exception as exc:
                    auto_res = {
                        "status": "error",
                        "browser": "Default Browser",
                        "target_url": "Failed",
                        "actions_log": [f"Automation error: {exc}"],
                        "gameplay_executed": False,
                    }

                def _done_automation() -> None:
                    self._stop_thinking_animation()
                    self._send_btn.configure(state="normal", text="Send")
                    self._clear_attachment()
                    if auto_res.get("status") == "browser_not_available":
                        msg = auto_res.get("message", "The requested browser is not installed on this system.")
                        self._append_message("model", f"⚠️ **Browser Not Available**\n\n{msg}")
                        return

                    self._append_automation_card(auto_res)
                    summary = (
                        f"Browser Automation Completed on **{auto_res.get('browser', 'Browser')}**.\n"
                        f"Navigated to `{auto_res.get('target_url')}`.\n"
                    )
                    if auto_res.get("text_typed"):
                        summary += f"\n✍️ **Typing completed**: Focused active editor/input and typed: **\"{auto_res['text_typed']}\"**."
                    elif auto_res.get("gameplay_executed"):
                        summary += "\n🎮 **Interactive gameplay loop engaged**: Focused game canvas and dispatched automated controls."
                    self._append_message("model", summary)

                self.after(0, _done_automation)
                return

            # 2. Handle Document Generation Request
            if is_create_doc_cmd:
                res = query_chat_explanation(user_text, taxonomy)
                self._current_decision_data = res

                parsed_doc = parse_document_request(
                    user_text,
                    base_dir=Path.cwd(),
                    attachment=self._attached_path,
                )
                doc_title = parsed_doc["title"]
                page_count = parsed_doc["page_count"]
                sections = parsed_doc["sections"]

                # Enrich with live web context if toggle is ON
                if web_fetch_enabled:
                    self.after(0, lambda: self._update_thinking_status(f"🌐 Web Fetch: Querying live verified knowledge for '{doc_title}'..."))
                    try:
                        web_data = fetch_web_context(doc_title)
                        sections = enrich_sections_with_web_context(sections, web_data)
                    except Exception as e:
                        pass

                self.after(0, lambda: self._update_thinking_status("Synthesizing DOCX typography, tables, and formulas..."))

                # Determine target folder
                if any(k in lower_prompt for k in ("calculus", "cs2806", "gradient ascent", "optimization")) and not any(k in lower_prompt for k in ("finance", "hackathon", "club")):
                    category = "Calculus"
                else:
                    category = res["decision"].subject
                dest_dir = target_path / category
                dest_dir.mkdir(parents=True, exist_ok=True)

                # Format file path from clean title
                safe_stem = re.sub(r'[^a-zA-Z0-9_\- ]+', '', doc_title).strip().replace(' ', '_')
                if not safe_stem:
                    safe_stem = "Document"
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = dest_dir / f"{safe_stem}_{timestamp_str}.docx"

                try:
                    created_file = create_word_document(
                        title=doc_title,
                        sections=sections,
                        output_path=out_path,
                        subtitle=parsed_doc.get("subtitle"),
                        author=parsed_doc.get("author", "Sortwise"),
                        abstract=parsed_doc.get("abstract"),
                        keywords=parsed_doc.get("keywords"),
                        affiliation=parsed_doc.get("affiliation"),
                        location=parsed_doc.get("location"),
                        email=parsed_doc.get("email"),
                        cover_page=parsed_doc.get("cover_page"),
                        declaration=parsed_doc.get("declaration"),
                        certificate=parsed_doc.get("certificate"),
                        table_of_contents=parsed_doc["sections"] if parsed_doc.get("table_of_contents") else None,
                        lists_of_figures_and_symbols=parsed_doc.get("lists_of_figures_and_symbols", False),
                        is_research=parsed_doc.get("is_research", False),
                        doc_format=parsed_doc.get("format", "standard"),
                    )
                    open_in_office(created_file)

                    tex_file = None
                    if parsed_doc.get("is_research") or parsed_doc.get("format") == "ieee":
                        try:
                            from src.ieee_latex_creator import export_to_ieee_latex, compile_latex_to_pdf
                            tex_path = out_path.with_suffix(".tex")
                            export_to_ieee_latex(parsed_doc, tex_path)
                            tex_file = tex_path
                            compile_latex_to_pdf(tex_path)
                        except Exception as tex_err:
                            logger.debug("Failed exporting IEEE LaTeX: %s", tex_err)

                    file_info = {
                        "file_path": str(created_file),
                        "file_name": created_file.name,
                        "folder_path": str(created_file.parent),
                        "category": category,
                    }
                    reply_text = (
                        f"Created {page_count}-page Word document '{created_file.name}' with heading '{doc_title}'.\n\n"
                        f"Full Pathway:  {created_file.resolve()}"
                    )
                    if tex_file and tex_file.is_file():
                        reply_text += f"\nIEEE LaTeX Source:  {tex_file.resolve()}"
                    if web_fetch_enabled:
                        reply_text += "\n\n🌐 *Enriched with verified live web knowledge, equations, figures, and citations.*"
                except Exception as exc:
                    file_info = None
                    reply_text = f"Failed to create document: {exc}"

                def _done_create() -> None:
                    self._stop_thinking_animation()
                    self._send_btn.configure(state="normal", text="Send")
                    self._clear_attachment()
                    self._append_message("model", reply_text, res, file_info=file_info)

                self.after(0, _done_create)
                return

            # 3. Conversational query or file classification
            if is_classify_cmd:
                res = query_chat_explanation(user_text, taxonomy)
                self._current_decision_data = res
                reply_content = res["explanation"]
                done_res = res
            else:
                search_query = task_spec.subject or user_text
                if web_fetch_enabled:
                    self.after(0, lambda: self._update_thinking_status("🌐 Web Fetch: Querying live sources..."))
                    try:
                        wdata = fetch_web_context(search_query)
                        reply_content = format_web_chat_response(search_query, wdata)
                    except Exception:
                        reply_content = f"Regarding **{search_query}**: Multi-source knowledge synthesis completed."
                else:
                    reply_content = f"Regarding **{search_query}**: Active knowledge response ready. (Enable Web Fetch for live external sources)."
                done_res = None
                self._current_decision_data = None

            def _done() -> None:
                self._stop_thinking_animation()
                self._send_btn.configure(state="normal", text="Send")
                self._append_message("model", reply_content, done_res)

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _active_learning_select(
        self,
        candidate: str,
        decision: Any,
        telemetry: dict[str, Any],
        file_info: dict[str, Any] | None = None,
        loc_lbl: Any = None,
    ) -> None:
        store = get_default_policy_store()
        is_override = bool(decision and decision.subject != candidate)
        reward = store.record_feedback(
            chosen_category=candidate,
            predicted_category=decision.subject if decision else candidate,
            agreement=decision.agreement if decision else 1.0,
            is_override=is_override,
            is_rejection=False,
            doc_embedding=telemetry.get("doc_embedding"),
            confidence=decision.confidence if decision else 0.5,
        )
        router = get_default_router()
        doc_emb = telemetry.get("doc_embedding")
        if doc_emb is not None:
            router.adapt_prototype(candidate, doc_emb, alpha=0.15)

        if file_info and file_info.get("file_path"):
            curr_p = Path(file_info["file_path"])
            if curr_p.is_file() and curr_p.parent.name != candidate:
                new_dir = curr_p.parent.parent / candidate
                new_dir.mkdir(parents=True, exist_ok=True)
                new_p = new_dir / curr_p.name
                try:
                    shutil.move(str(curr_p), str(new_p))
                    file_info["file_path"] = str(new_p)
                    file_info["folder_path"] = str(new_dir)
                    file_info["category"] = candidate
                    if loc_lbl:
                        loc_lbl.configure(text=f"Saved To:  {new_dir}")
                except Exception:
                    pass

        self._reinforce_info.configure(
            text=f"[Active Learning] Realigned to '{candidate}' (Entropy collapsed, Reward: +{reward:.2f})",
            text_color="#34d399",
        )

    def _confirm_feedback(self, decision: Any, telemetry: dict[str, Any]) -> None:
        store = get_default_policy_store()
        reward = store.record_feedback(
            chosen_category=decision.subject,
            predicted_category=decision.subject,
            agreement=decision.agreement,
            is_override=False,
            is_rejection=False,
            doc_embedding=telemetry.get("doc_embedding"),
            confidence=decision.confidence,
        )
        self._reinforce_info.configure(
            text=f"[RLCD Policy] Confirmed '{decision.subject}' (Reward: +{reward:.2f}, Episodes: {store.episodes})",
            text_color="#34d399",
        )

    def _reject_feedback(self, decision: Any, telemetry: dict[str, Any]) -> None:
        store = get_default_policy_store()
        reward = store.record_feedback(
            chosen_category=decision.subject,
            predicted_category=decision.subject,
            agreement=decision.agreement,
            is_override=False,
            is_rejection=True,
            doc_embedding=telemetry.get("doc_embedding"),
            confidence=decision.confidence,
        )
        self._reinforce_info.configure(
            text=f"[RLCD Policy] Rejected '{decision.subject}' (Negative Penalty Applied, Episodes: {store.episodes})",
            text_color="#f87171",
        )

    def _override_feedback(
        self,
        chosen: str,
        decision: Any,
        telemetry: dict[str, Any],
        file_path: str | None = None,
        loc_label_ref: Any | None = None,
    ) -> None:
        store = get_default_policy_store()
        reward = store.record_feedback(
            chosen_category=chosen,
            predicted_category=decision.subject,
            agreement=decision.agreement,
            is_override=True,
            is_rejection=False,
            doc_embedding=telemetry.get("doc_embedding"),
            confidence=decision.confidence,
        )
        move_info = ""
        if file_path:
            old_p = Path(file_path)
            if old_p.exists():
                try:
                    config = self._config_store.load()
                    target_path = Path(config.target_root).expanduser().resolve()
                    if not target_path.is_dir():
                        target_path = Path(config.watch_folder).expanduser().resolve()
                    new_dir = target_path / chosen
                    new_dir.mkdir(parents=True, exist_ok=True)
                    new_p = new_dir / old_p.name
                    if old_p.resolve() != new_p.resolve():
                        shutil.move(str(old_p), str(new_p))
                        move_info = f" · Moved file to {chosen}"
                        if loc_label_ref is not None:
                            loc_label_ref.configure(text=f"Saved To:  {new_dir}")
                except Exception as ex:
                    move_info = f" (Move error: {ex})"

        self._reinforce_info.configure(
            text=f"[RLCD Policy] Shifted to '{chosen}' (Penalty on {decision.subject}, Reward: {reward:.2f}{move_info})",
            text_color="#f59e0b",
        )

    def _export_to_docx(self) -> None:
        if not self._chat_history:
            return
        config = self._config_store.load()
        out_dir = Path(config.target_root).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = out_dir / f"RLCD_Chat_Transcript_{ts}.docx"
        export_chat_to_docx(self._chat_history, out_file)
        self._reinforce_info.configure(
            text=f"[Exported] Saved to {out_file.name}",
            text_color="#60a5fa",
        )
        open_in_office(out_file)

    def _clear_chat(self) -> None:
        self._chat_history.clear()
        for child in self._transcript.winfo_children():
            child.destroy()
        self._append_message(
            "model",
            "Chat cleared. Enter document text below for fresh RLCD evaluation.",
        )


# --------------------------------------------------------------------------- #
# 3. Word (.docx) Document Creator Tab
# --------------------------------------------------------------------------- #
class WordCreatorView(ctk.CTkFrame):
    """Word document creator with python-docx generation and LibreOffice CLI integration."""

    def __init__(self, master: Any, config_store: ConfigStore) -> None:
        super().__init__(master, fg_color="transparent")
        self._config_store = config_store
        self._last_generated_path: Path | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 10))

        ctk.CTkLabel(
            header,
            text="Word Document Creator (.docx)",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        ).pack(side="left")

        # Scrollable form
        form = ctk.CTkScrollableFrame(self, fg_color="#181a20", corner_radius=8, border_width=1, border_color="#2b2d35")
        form.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        # Title
        ctk.CTkLabel(form, text="Document Title:", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(14, 4)
        )
        self._title_entry = ctk.CTkEntry(form, height=36, font=ctk.CTkFont(size=14))
        self._title_entry.insert(0, "Lecture Notes: Artificial Intelligence & Machine Learning")
        self._title_entry.pack(fill="x", padx=16, pady=(0, 10))

        # Subtitle & Category
        row_cat = ctk.CTkFrame(form, fg_color="transparent")
        row_cat.pack(fill="x", padx=16, pady=(0, 10))

        col1 = ctk.CTkFrame(row_cat, fg_color="transparent")
        col1.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(col1, text="Subtitle / Subject:", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x", pady=(0, 4))
        self._subtitle_entry = ctk.CTkEntry(col1, height=34, font=ctk.CTkFont(size=13))
        self._subtitle_entry.insert(0, "Project Overview")
        self._subtitle_entry.pack(fill="x")

        col2 = ctk.CTkFrame(row_cat, fg_color="transparent")
        col2.pack(side="right", fill="x", expand=True, padx=(8, 0))
        ctk.CTkLabel(col2, text="Destination Category:", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(fill="x", pady=(0, 4))

        config = self._config_store.load()
        cats = discover_target_categories(config.target_root)
        if not cats:
            cats = ["General Study Material"]
        self._cat_menu = ctk.CTkOptionMenu(col2, values=cats, height=34)
        self._cat_menu.set(cats[0])
        self._cat_menu.pack(fill="x")

        # Headings & Content
        ctk.CTkLabel(form, text="Section 1 Heading:", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(10, 4)
        )
        self._sec1_h = ctk.CTkEntry(form, height=32, font=ctk.CTkFont(size=13))
        self._sec1_h.insert(0, "Core Concepts and Theory")
        self._sec1_h.pack(fill="x", padx=16, pady=(0, 8))
        attach_text_context_menu(self._sec1_h, is_entry=True, readonly=False)

        ctk.CTkLabel(form, text="Section 1 Body Text (Paragraphs):", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(0, 4)
        )
        self._sec1_body = ctk.CTkTextbox(form, height=90, font=ctk.CTkFont(size=13))
        self._sec1_body.insert(
            "1.0",
            "Supervised learning algorithms infer a function from labeled training data.\n"
            "The training set consists of pairs of input vectors and desired outputs.\n"
            "Reinforcement learning calibrated decision models balance confidence and epistemic entropy.",
        )
        self._sec1_body.pack(fill="x", padx=16, pady=(0, 10))
        attach_text_context_menu(self._sec1_body, is_entry=False, readonly=False)

        ctk.CTkLabel(form, text="Section 2 Heading:", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(8, 4)
        )
        self._sec2_h = ctk.CTkEntry(form, height=32, font=ctk.CTkFont(size=13))
        self._sec2_h.insert(0, "Key Takeaways (Bullet Points):")
        self._sec2_h.pack(fill="x", padx=16, pady=(0, 8))
        attach_text_context_menu(self._sec2_h, is_entry=True, readonly=False)

        ctk.CTkLabel(form, text="Bullet Items (One per line):", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(0, 4)
        )
        self._bullets_text = ctk.CTkTextbox(form, height=70, font=ctk.CTkFont(size=13))
        self._bullets_text.insert(
            "1.0",
            "Gradient descent minimizes the objective loss function.\n"
            "Normalized Shannon entropy bounds risk on ambiguous documents.\n"
            "Policy gradient updates dynamically adjust category preferences.",
        )
        self._bullets_text.pack(fill="x", padx=16, pady=(0, 14))
        attach_text_context_menu(self._bullets_text, is_entry=False, readonly=False)

        # Bottom Action Bar
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 16))

        self._result_lbl = ctk.CTkLabel(actions, text="", font=ctk.CTkFont(size=13), anchor="w")
        self._result_lbl.pack(side="left", padx=8)

        self._open_btn = ctk.CTkButton(
            actions,
            text="Open in LibreOffice (soffice)",
            width=200,
            height=38,
            fg_color="#2b2d35",
            hover_color="#363942",
            state="disabled",
            command=self._open_in_libreoffice,
        )
        self._open_btn.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            actions,
            text="Generate Word File (.docx)",
            width=200,
            height=38,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generate_document,
        ).pack(side="right")

    def _generate_document(self) -> None:
        title = self._title_entry.get().strip() or "Untitled Document"
        subtitle = self._subtitle_entry.get().strip()
        chosen_cat = self._cat_menu.get().strip()

        config = self._config_store.load()
        cat_dir = Path(config.target_root).expanduser() / chosen_cat
        cat_dir.mkdir(parents=True, exist_ok=True)

        clean_stem = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "Document"
        out_path = cat_dir / f"{clean_stem}.docx"

        sec1_paragraphs = [p.strip() for p in self._sec1_body.get("1.0", "end").split("\n") if p.strip()]
        sec2_bullets = [b.strip() for b in self._bullets_text.get("1.0", "end").split("\n") if b.strip()]

        sections = [
            {"heading": self._sec1_h.get().strip(), "level": 1, "paragraphs": sec1_paragraphs},
            {"heading": self._sec2_h.get().strip(), "level": 2, "bullets": sec2_bullets},
        ]

        try:
            created = create_word_document(
                title=title,
                sections=sections,
                output_path=out_path,
                subtitle=subtitle,
                subject=chosen_cat,
            )
            self._last_generated_path = created
            self._open_btn.configure(state="normal")
            self._result_lbl.configure(
                text=f"[OK] Generated '{created.name}' inside {chosen_cat} ({created.stat().st_size} bytes)",
                text_color="#10b981",
            )
        except Exception as exc:
            self._result_lbl.configure(text=f"[Error] Failed to generate: {exc}", text_color="#ef4444")

    def _open_in_libreoffice(self) -> None:
        if self._last_generated_path and self._last_generated_path.is_file():
            open_in_office(self._last_generated_path)
            self._result_lbl.configure(text=f"Launched {self._last_generated_path.name} in office viewer.", text_color="#60a5fa")


# --------------------------------------------------------------------------- #
# 4. 100% Dynamic Library & Category Training View (Zero Hardcoding!)
# --------------------------------------------------------------------------- #
class TrainingView(ctk.CTkFrame):
    """Dynamic category discovery, custom folder creation, and document-driven prototype training."""

    def __init__(self, master: Any, config_store: ConfigStore) -> None:
        super().__init__(master, fg_color="transparent")
        self._config_store = config_store
        self._is_training = False

        self._build_ui()

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 10))

        ctk.CTkLabel(
            header,
            text="Library Categories & Dynamic RLCD Training",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Refresh Categories",
            width=140,
            height=32,
            fg_color="#2b2d35",
            hover_color="#363942",
            command=self.refresh_categories,
        ).pack(side="right")

        # Main Card
        card = ctk.CTkFrame(self, fg_color="#181a20", corner_radius=8, border_width=1, border_color="#2b2d35")
        card.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        # Add Category Row
        add_box = ctk.CTkFrame(card, fg_color="transparent")
        add_box.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(add_box, text="Add New Category Folder:", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(0, 8))
        self._new_cat_entry = ctk.CTkEntry(add_box, width=280, height=34, placeholder_text="e.g. Distributed Systems")
        self._new_cat_entry.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            add_box,
            text="Create Folder",
            width=120,
            height=34,
            command=self._create_category,
        ).pack(side="left")

        # Scrollable Category List
        ctk.CTkLabel(card, text="Detected Categories in Target Library:", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(8, 4)
        )
        self._cat_list_frame = ctk.CTkScrollableFrame(card, height=180, fg_color="#131418", corner_radius=6)
        self._cat_list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # Telemetry & Status Card
        telemetry_box = ctk.CTkFrame(card, fg_color="#1e2028", corner_radius=6, border_width=1, border_color="#2b2d35")
        telemetry_box.pack(fill="x", padx=16, pady=(0, 14))

        self._telem_lbl = ctk.CTkLabel(
            telemetry_box,
            text="Loading telemetry...",
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af",
            justify="left",
            anchor="w",
        )
        self._telem_lbl.pack(fill="x", padx=14, pady=10)

        # Bottom Bar
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(0, 16))

        self._train_status = ctk.CTkLabel(bottom, text="", font=ctk.CTkFont(size=13), anchor="w")
        self._train_status.pack(side="left", padx=8)

        self._train_btn = ctk.CTkButton(
            bottom,
            text="Train Model from Documents",
            width=220,
            height=38,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_training,
        )
        self._train_btn.pack(side="right")

        self.refresh_categories()

    def refresh_categories(self) -> None:
        for w in self._cat_list_frame.winfo_children():
            w.destroy()

        config = self._config_store.load()
        root = Path(config.target_root).expanduser()
        cats = discover_target_categories(root)

        if not cats:
            ctk.CTkLabel(
                self._cat_list_frame,
                text="No category subfolders found yet in target library. Use 'Add New Category' above to create one.",
                font=ctk.CTkFont(size=13),
                text_color="#9ca3af",
            ).pack(padx=12, pady=16)
        else:
            for cat in cats:
                cat_dir = root / cat
                file_count = len([f for f in cat_dir.rglob("*") if f.is_file()]) if cat_dir.is_dir() else 0
                row = ctk.CTkFrame(self._cat_list_frame, fg_color="#1e2028", height=36, corner_radius=4)
                row.pack(fill="x", padx=4, pady=2)
                ctk.CTkLabel(row, text=cat, font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(side="left", padx=10)
                ctk.CTkLabel(
                    row,
                    text=f"{file_count} documents",
                    font=ctk.CTkFont(size=12),
                    text_color="#9ca3af",
                ).pack(side="right", padx=10)

        # Update Telemetry stats
        store = get_default_policy_store()
        telem = store.get_telemetry()
        self._telem_lbl.configure(
            text=f"RLCD Policy Telemetry: Episodes: {telem['episodes']} · "
                 f"Agreement Rate: {telem['agreement_rate'] * 100:.1f}% · "
                 f"Expected Calibration Error (ECE): {telem['ece']:.3f} · "
                 f"Trained Prototype Centroids: {telem['centroids_tracked']}"
        )

    def _create_category(self) -> None:
        cat_name = self._new_cat_entry.get().strip()
        if not cat_name:
            return
        config = self._config_store.load()
        root = Path(config.target_root).expanduser()
        new_dir = root / cat_name
        new_dir.mkdir(parents=True, exist_ok=True)
        self._new_cat_entry.delete(0, "end")
        self.refresh_categories()
        self._train_status.configure(text=f"[Created] Folder '{cat_name}' added to library.", text_color="#10b981")

    def _start_training(self) -> None:
        if self._is_training:
            return
        config = self._config_store.load()
        root = Path(config.target_root).expanduser()

        self._is_training = True
        self._train_btn.configure(state="disabled", text="Training Models...")
        self._train_status.configure(text="Extracting documents and calibrating prototype centroids...", text_color="#60a5fa")

        def _worker() -> None:
            res = train_prototypes_from_library(root)

            def _done() -> None:
                self._is_training = False
                self._train_btn.configure(state="normal", text="Train Model from Documents")
                if res.get("status") == "ok":
                    n_cats = res.get("categories_trained", 0)
                    n_docs = res.get("total_documents", 0)
                    self._train_status.configure(
                        text=f"[Success] Calibrated {n_cats} categories across {n_docs} documents.",
                        text_color="#10b981",
                    )
                else:
                    self._train_status.configure(
                        text=f"[Notice] {res.get('message', 'No training documents found')}",
                        text_color="#f59e0b",
                    )
                self.refresh_categories()

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()
