#!/usr/bin/env python3
"""Sortwise -- native desktop application (CustomTkinter).

This is a *physical* desktop program: a real X11/Wayland window rendered by Tk
through CustomTkinter.  There is no browser, no webview and no HTTP server
anywhere in this module -- the FastAPI application is never started.  Only the
pure service layer inside :mod:`src.server` (:class:`~src.server.SortwiseService`,
:class:`~src.server.ConfigStore`, :class:`~src.server.Ledger`) is imported and
called in-process, so extraction, calibration, in-flight renaming and the undo
ledger are the same code paths the backend uses.

Layout
------
The window is a two-pane desktop file browser that mirrors the reference
designs:

* **Sidebar** (left) -- three window control dots, a *Semester 3 / Target
  Storage* summary built around the ``disk.png`` glyph, and a navigation list
  with live count badges (All Documents, Downloads, Subjects, Review Queue,
  Activity Ledger).
* **Top navigation** -- ``<`` ``>`` history arrows, a disk glyph with
  breadcrumbs, a live search entry and the router action buttons (Scan Watch
  Dir, Auto-Route Confident, Undo Last, Settings).
* **Folder shelf** -- a row of large desktop folder cards; clicking one filters
  the table and draws a highlighted rounded border around the active card.
* **Proportion table** -- columns ``Name``, ``Size`` and ``Calibrated Routing /
  Space``: expandable ``>`` / ``v`` arrows, file-format icons, a rounded pastel
  confidence pill and a ``CONFIDENT`` / ``REVIEW`` status badge.
* **Inspector** -- the selected document's details and the in-flight rename
  field with the ``Route Document`` action.
* **Activity ledger** -- every transfer with 1-click undo.
* **Startup scanner** -- on launch, a *Scan for documents* dialog offers
  **Scan a folder** (Downloads / Documents / Desktop / browse) or a **Deep
  System Scan** (walk the whole home folder).  The walk runs multi-threaded on
  the BCUninstaller-inspired engine in :mod:`src.scanner`, streams live progress
  (current path, folders, files, elapsed) with a cancel button, skips
  ``/proc``, ``/sys``, ``/dev``, ``/nix/store``, ``.git``, ``node_modules`` and
  ``.cache`` before they are opened, and rates every hit CONFIDENT / REVIEW.  A
  bulk toolbar then offers *Select All Confident* and *Batch Route* with
  in-flight renaming.

Every icon is loaded from :data:`src/assets/icons` with :class:`PIL.Image` and
wrapped in :class:`customtkinter.CTkImage`.  Missing icons degrade to a plain
label instead of raising.

Usage
-----
    python src/native_app.py
    python src/native_app.py --config ~/.config/sortwise/config.json
    python src/native_app.py --watch ~/Downloads --target ~/Documents/Semester3
    python src/native_app.py --no-scan-dialog
"""

from __future__ import annotations

import argparse
import math
import os
import queue
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# --------------------------------------------------------------------------- #
# Path bootstrap: the app is launched as a script, so make ``src`` importable.
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from src.calibrator import STATUS_AMBIGUOUS, STATUS_CONFIDENT
from src.extractors import extract_document
from src.server import (
    SUPPORTED_EXTENSIONS,
    ConfigStore,
    Ledger,
    SortwiseConfig,
    SortwiseError,
    SortwiseService,
    default_config_path,
    default_ledger_path,
    expand_path,
    human_size,
    sanitize_filename,
)
from src.taxonomy import get_subject_taxonomy, subject_labels
from src.scanner import (
    DiskScanner,
    ScanProgress,
    ScannedDocument,
    default_workers,
    preset_targets,
    rate_document,
)

__all__ = [
    "APP_NAME",
    "DocItem",
    "Icons",
    "PillBar",
    "ScanProgressDialog",
    "ScanSetupDialog",
    "SettingsDialog",
    "SortwiseApp",
    "Theme",
    "build_document_tree",
    "inspect_document",
    "main",
    "parse_args",
    "suggest_filename",
]

APP_NAME = "Sortwise"
WINDOW_TITLE = "Sortwise - Calibrated Document Router"
WINDOW_SIZE = (1560, 1000)
MIN_WINDOW_SIZE = (1280, 860)

SIDEBAR_WIDTH = 300
SHELF_HEIGHT = 178
LEDGER_HEIGHT = 232
INSPECTOR_WIDTH = 428
BULK_HEIGHT = 54

# Sentinel shown in the subject override menu when the calibrated prediction
# should be trusted instead of a manual choice.
AUTO_SUBJECT = "Automatic (calibrated)"

# Scan-view row identifiers.
SCAN_MODE = "scan"

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


# --------------------------------------------------------------------------- #
# Theme -- matte graphite surfaces with the reference pastel functional tints
# --------------------------------------------------------------------------- #
class Theme:
    """One place for every colour, size and radius the app uses."""

    # Surfaces
    BG = "#0e1014"
    SIDEBAR = "#14171f"
    SURFACE = "#191d26"
    ELEVATED = "#20242f"
    HOVER = "#272d39"
    BORDER = "#282e3a"
    BORDER_STRONG = "#39414f"

    # Type
    TEXT = "#f1f3f7"
    TEXT_MUTED = "#98a0b2"
    TEXT_FAINT = "#5f6775"

    # Typography scale (points).  The whole UI reads its sizes from here so the
    # scale can be raised or lowered in one place.  Base body text is 14pt,
    # headers 18-22pt, section labels 15-16pt.
    FONT_HEADER = 20        # window / pane headers
    FONT_HEADER_SMALL = 18  # secondary headers (ledger, inspector)
    FONT_SUBHEADER = 16     # storage block title
    FONT_SECTION = 15       # small-caps section labels
    FONT_BASE = 14          # body / navigation text
    FONT_TABLE = 14         # table rows
    FONT_PILL = 13          # pill + badge labels
    FONT_BUTTON = 14        # action buttons
    FONT_MONO = 13          # telemetry / monospace
    FONT_MONO_SMALL = 12    # dense monospace
    FONT_HINT = 12          # helper / muted copy

    # Functional tints
    ACCENT = "#3b82f6"
    ACCENT_DEEP = "#2f6ad0"
    SUCCESS = "#10b981"
    WARN = "#f59e0b"
    DANGER = "#f43f5e"

    # Reference palette for the proportion pills and the window dots
    PILL_COLORS = ("#f43f5e", "#a855f7", "#f59e0b", "#10b981", "#3b82f6")
    WINDOW_DOTS = ("#ff5f56", "#ffbd2e", "#27c93f")

    # Geometry
    RADIUS = 14
    RADIUS_SMALL = 9
    PAD = 14
    GAP = 10


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #
def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _hex(rgb: Iterable[float]) -> str:
    r, g, b = (max(0, min(255, int(round(channel)))) for channel in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(color_a: str, color_b: str, amount: float) -> str:
    """Blend ``color_a`` towards ``color_b`` by ``amount`` in ``[0, 1]``."""
    amount = max(0.0, min(1.0, amount))
    a, b = _rgb(color_a), _rgb(color_b)
    return _hex(a[i] + (b[i] - a[i]) * amount for i in range(3))


def lighten(color: str, amount: float) -> str:
    return mix(color, "#ffffff", amount)


def darken(color: str, amount: float) -> str:
    return mix(color, "#000000", amount)


def readable_on(color: str) -> str:
    """Pick a legible foreground for a coloured surface."""
    r, g, b = _rgb(color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return "#0e1014" if luminance > 0.62 else "#ffffff"


# --------------------------------------------------------------------------- #
# Font resolution -- never assume a family exists on the host
# --------------------------------------------------------------------------- #
UI_FONT_CANDIDATES: tuple[str, ...] = (
    "Inter",
    "IBM Plex Sans",
    "Noto Sans",
    "Open Sans",
    "Cantarell",
    "Ubuntu",
    "DejaVu Sans",
    "Liberation Sans",
)
MONO_FONT_CANDIDATES: tuple[str, ...] = (
    "JetBrains Mono",
    "IBM Plex Mono",
    "Noto Sans Mono",
    "DejaVu Sans Mono",
    "Hack",
    "Liberation Mono",
    "monospace",
)


def pick_font_family(widget: tk.Misc, candidates: Sequence[str]) -> str | None:
    """Return the first installed family from ``candidates`` (or ``None``)."""
    try:
        available = {name.casefold() for name in tkfont.families(widget)}
    except Exception:  # pragma: no cover - defensive, Tk should be up
        return None
    for candidate in candidates:
        if candidate.casefold() in available:
            return candidate
    return None


# --------------------------------------------------------------------------- #
# Icon library -- PIL images wrapped in CTkImage, cached per size
# --------------------------------------------------------------------------- #
class Icons:
    """Lazy, cached loader for ``src/assets/icons/*.png``.

    Every failure mode (missing file, unreadable PNG, Tk photo-image error)
    degrades to ``None`` so a widget can fall back to a text label rather than
    crashing the window.
    """

    def __init__(self, directory: Path = ICON_DIR, theme: type[Theme] = Theme) -> None:
        self.directory = Path(directory)
        self._theme = theme
        self._cache: dict[tuple[str, int], ctk.CTkImage | None] = {}

    def image(self, name: str, size: int) -> ctk.CTkImage | None:
        key = (name, int(size))
        if key in self._cache:
            return self._cache[key]
        image: ctk.CTkImage | None = None
        path = self.directory / name
        try:
            if path.is_file():
                with Image.open(path) as handle:
                    pil = handle.convert("RGBA").copy()
                image = ctk.CTkImage(light_image=pil, dark_image=pil, size=(int(size), int(size)))
        except Exception:  # noqa: BLE001 - never let a missing icon kill the UI
            image = None
        self._cache[key] = image
        return image

    def exists(self, name: str) -> bool:
        return (self.directory / name).is_file()


def file_icon_name(file_type: str) -> str:
    return {
        "pdf": "file-pdf.png",
        "docx": "file-docx.png",
        "pptx": "file-pptx.png",
        "txt": "file-text.png",
    }.get((file_type or "").casefold(), "file-text.png")


# --------------------------------------------------------------------------- #
# Shelf / subject configuration
# --------------------------------------------------------------------------- #
# The eight top-level cards of the folder shelf, exactly as in the reference.
SHELF_CARDS: tuple[tuple[str, str, str], ...] = (
    ("documents", "Documents", "folder-documents.png"),
    ("downloads", "Downloads", "folder-downloads.png"),
    ("calculus", "Calculus", "folder-calculus.png"),
    ("algorithms", "Algorithms", "folder-algorithms.png"),
    ("aiml", "AI & ML", "folder-aiml.png"),
    ("datascience", "Data Science", "folder-datascience.png"),
    ("cybersecurity", "Cyber Security", "folder-cybersecurity.png"),
    ("cloudcomputing", "Cloud Computing", "folder-cloudcomputing.png"),
)

CARD_TO_SUBJECT: dict[str, str] = {
    "calculus": "CS2806 - Calculus",
    "algorithms": "CS2000 - Design and Analysis of Algorithms",
    "aiml": "CS2227 - AI and ML",
    "datascience": "CS2235 - Data Science",
    "cybersecurity": "CS2405 - Cyber Security",
    "cloudcomputing": "CS2500 - Cloud Computing and Big Data",
}
SUBJECT_TO_CARD: dict[str, str] = {label: card for card, label in CARD_TO_SUBJECT.items()}

SUBJECT_ICONS: dict[str, str] = {
    "CS2806 - Calculus": "folder-calculus.png",
    "CS2000 - Design and Analysis of Algorithms": "folder-algorithms.png",
    "CS2227 - AI and ML": "folder-aiml.png",
    "CS2235 - Data Science": "folder-datascience.png",
    "CS2405 - Cyber Security": "folder-cybersecurity.png",
    "CS2500 - Cloud Computing and Big Data": "folder-cloudcomputing.png",
    "CS2403 - Computer Networks": "folder-cloud.png",
    "CS2404 - Internet of Things": "folder-default.png",
}

# Sidebar navigation entries: (view, label, icon).
NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("all", "All Documents", "folder-documents.png"),
    ("downloads", "Downloads", "folder-downloads.png"),
    ("subjects", "Subjects", "folder-cloud.png"),
    ("review", "Review Queue", "file-text.png"),
    ("ledger", "Activity Ledger", "disk.png"),
)

COLUMNS = (
    ("arrow", 34, 0),
    ("icon", 42, 0),
    ("name", 264, 1),
    ("size", 112, 0),
    ("pill", 184, 0),
    ("status", 128, 0),
)


# --------------------------------------------------------------------------- #
# Document tree model
# --------------------------------------------------------------------------- #
@dataclass
class DocItem:
    """One row of the proportion table (a folder or a document)."""

    key: str
    label: str
    kind: str = "folder"                 # "folder" | "file"
    path: str | None = None
    size: int = 0
    file_type: str = ""
    subject: str = ""                    # taxonomy label ("CS2806 - Calculus")
    card: str | None = None              # shelf card key for top-level folders
    pending: bool = False                # in the intake folder, not yet routed
    modified: str = ""
    confidence: float | None = None
    status: str = ""                     # CONFIDENT | REVIEW
    exists: bool = True
    scan: bool = False                   # discovered by the disk scanner
    selected: bool = False               # ticked in the bulk-action toolbar
    children: list["DocItem"] = field(default_factory=list)

    @property
    def is_file(self) -> bool:
        return self.kind == "file"

    @property
    def is_folder(self) -> bool:
        return self.kind == "folder"

    @property
    def code(self) -> str:
        return self.subject.split(" - ")[0] if self.subject else ""


def _score_subject(filename: str, taxonomy: dict[str, dict]) -> tuple[int, str]:
    """Cheap, model-free filename heuristic -> ``(score, subject_label)``."""
    haystack = (filename or "").casefold().replace("_", " ").replace("-", " ")
    best: tuple[int, str] = (0, "")
    for label, entry in taxonomy.items():
        code = str(entry.get("code", "")).casefold()
        name = str(entry.get("name", "")).casefold()
        score = 0
        if code and code in haystack.replace(" ", ""):
            score += 3
        for token in name.replace("/", " ").split():
            if len(token) > 3 and token in haystack:
                score += 1
        if score > best[0]:
            best = (score, label)
    return best


def heuristic_confidence(score: int) -> float:
    """Map a heuristic keyword score to a plausible confidence in ``[0, 1]``."""
    if score <= 0:
        return 0.0
    return min(0.99, 0.55 + 0.17 * score)


def _flat(config: SortwiseConfig) -> SortwiseConfig:
    """A copy of ``config`` that always scans a single directory level."""
    data = config.to_dict()
    data["recursive"] = False
    return SortwiseConfig.from_dict(data)


def build_document_tree(
    service: SortwiseService,
    config: SortwiseConfig,
    ledger_entries: Sequence[dict[str, Any]] | None = None,
) -> tuple[list[DocItem], dict[str, Any]]:
    """Scan the archive and the intake folder, and build the table model.

    Returns ``(top_level_items, stats)``.  Every folder is optional: a missing
    or unreadable directory simply yields an empty branch instead of raising.
    """
    taxonomy = get_subject_taxonomy()
    flat = _flat(config)

    filed: dict[str, dict[str, Any]] = {}
    for entry in ledger_entries or []:
        if entry.get("action") == "move" and not entry.get("undone"):
            destination = str(entry.get("destination") or "")
            if destination:
                filed[destination] = entry

    def make_file(record: dict[str, Any], *, subject: str = "", pending: bool = False) -> DocItem:
        path = str(record.get("path", ""))
        name = str(record.get("name", "?") or "?")
        item = DocItem(
            key=f"file:{path}",
            label=name,
            kind="file",
            path=path,
            size=int(record.get("size", 0) or 0),
            file_type=str(record.get("file_type", "") or Path(name).suffix.lstrip(".")),
            pending=pending,
            modified=str(record.get("modified", "") or ""),
        )
        entry = filed.get(path)
        if entry is not None:
            item.subject = str(entry.get("subject") or subject)
            item.confidence = float(entry.get("confidence", 0.0) or 0.0)
            item.status = str(entry.get("status") or "")
        elif pending:
            score, label = _score_subject(name, taxonomy)
            item.subject = label
            item.confidence = heuristic_confidence(score)
        else:
            item.subject = subject
            item.confidence = 0.94
            item.status = STATUS_CONFIDENT
        if not item.status:
            threshold = float(config.confidence_threshold)
            item.status = STATUS_CONFIDENT if (item.confidence or 0.0) >= threshold else STATUS_AMBIGUOUS
        return item

    def scan_dir(folder: Path) -> list[dict[str, Any]]:
        try:
            if folder.is_dir():
                return list(service.scan(flat, path=str(folder)).get("files", []))
        except (SortwiseError, OSError):
            return []
        return []

    top: list[DocItem] = []
    subject_nodes: list[DocItem] = []

    # Documents -- the archive: every filed document, aggregated flat.
    target_root = expand_path(config.target_root)
    documents = DocItem(
        key="folder:documents", label="Documents", kind="folder",
        path=str(target_root), card="documents", exists=target_root.is_dir(),
    )
    documents.children = [make_file(record) for record in scan_dir(target_root)]
    top.append(documents)

    # Downloads -- the intake folder, respect the recursive setting.
    watch = expand_path(config.watch_folder)
    downloads = DocItem(
        key="folder:downloads", label="Downloads", kind="folder",
        path=str(watch), card="downloads", exists=watch.is_dir(),
    )
    try:
        intake_files = list(service.scan(config).get("files", [])) if watch.is_dir() else []
    except (SortwiseError, OSError):
        intake_files = []
    downloads.children = [make_file(record, pending=True) for record in intake_files]
    downloads.size = sum(child.size for child in downloads.children)
    top.append(downloads)

    # Subjects -- one folder per taxonomy course.
    archived_size = 0
    archived_count = 0
    for label in subject_labels():
        entry = taxonomy.get(label, {})
        folder = service.destination_folder(label, config)
        node = DocItem(
            key=f"folder:subject:{label}",
            label=label,
            kind="folder",
            path=str(folder),
            subject=label,
            card=SUBJECT_TO_CARD.get(label),
            exists=folder.is_dir(),
        )
        node.children = [make_file(record, subject=label) for record in scan_dir(folder)]
        node.size = sum(child.size for child in node.children)
        archived_size += node.size
        archived_count += len(node.children)
        subject_nodes.append(node)
        top.append(node)

    # "Documents" shows the whole archive, flattened across every subject.
    documents.children.extend(
        child for node in subject_nodes for child in node.children
    )
    documents.size = sum(child.size for child in documents.children)

    review_count = 0
    seen: set[str] = set()
    for item in _iter_files([downloads, *subject_nodes]):
        if item.key in seen:
            continue
        seen.add(item.key)
        if item.status == STATUS_AMBIGUOUS:
            review_count += 1
    stats = {
        "archived_size": archived_size,
        "archived_count": archived_count,
        "pending_count": len(downloads.children),
        "review_count": review_count,
        "total_count": archived_count + len(downloads.children),
        "folder_sizes": {
            item.card: item.size for item in top if item.card
        },
        "folder_counts": {
            item.card: len(item.children) for item in top if item.card
        },
    }
    return top, stats


def _iter_files(items: Sequence[DocItem]) -> list[DocItem]:
    """Flatten every file in a tree of :class:`DocItem` objects."""
    found: list[DocItem] = []
    for item in items:
        if item.is_file:
            found.append(item)
        found.extend(_iter_files(item.children))
    return found


# --------------------------------------------------------------------------- #
# Document inspection (never raises, safe to call from a worker thread)
# --------------------------------------------------------------------------- #
def _page_count(path: Path, file_type: str, word_count: int) -> tuple[int | None, str]:
    """Best-effort page/slide count with an honest label for each format."""
    try:
        if file_type == "pdf":
            import pymupdf as fitz  # PyMuPDF

            with fitz.open(str(path)) as document:
                return int(document.page_count), "pages"
        if file_type == "pptx":
            from pptx import Presentation

            return len(Presentation(str(path)).slides), "slides"
        if file_type == "docx":
            if word_count <= 0:
                return None, "pages"
            return max(1, math.ceil(word_count / 500)), "pages (est.)"
    except Exception:
        return None, "pages"
    return None, "pages"


def inspect_document(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Collect the metadata the inspector pane shows for one file."""
    target = expand_path(path)
    file_type = target.suffix.lstrip(".").casefold()
    info: dict[str, Any] = {
        "path": str(target),
        "name": target.name,
        "file_type": file_type,
        "size": 0,
        "size_human": "-",
        "title": target.stem,
        "word_count": 0,
        "headings": [],
        "pages": None,
        "page_label": "pages",
        "error": None,
    }
    try:
        info["size"] = target.stat().st_size
        info["size_human"] = human_size(info["size"])
    except OSError:
        pass
    try:
        document = extract_document(str(target))
        info["title"] = document.title
        info["word_count"] = document.word_count
        info["headings"] = list(document.headings[:6])
        info["file_type"] = document.file_type
    except Exception as exc:  # noqa: BLE001 - shown to the user, never fatal
        info["error"] = str(exc)
    info["pages"], info["page_label"] = _page_count(
        target, info["file_type"], int(info["word_count"])
    )
    return info


def suggest_filename(title: str, subject_label: str | None, file_type: str) -> str:
    """Smart default: ``"CS2806 - Calculus notes.pdf"`` style."""
    stem = (title or "").strip() or "document"
    code = ""
    if subject_label:
        code = str(get_subject_taxonomy().get(subject_label, {}).get("code", "") or "")
    if code and not stem.casefold().startswith(code.casefold()):
        stem = f"{code} - {stem}"
    stem = sanitize_filename(stem, fallback="document")
    return f"{stem[:120]}.{file_type}" if file_type else stem[:120]


# --------------------------------------------------------------------------- #
# Rounded pastel proportion pill (Image 2 style)
# --------------------------------------------------------------------------- #
def rounded_rect(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float,
                 radius: float, **kwargs: Any) -> int:
    """Draw a smooth rounded rectangle on ``canvas`` and return its item id."""
    radius = max(0.0, min(radius, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    points = [
        x0 + radius, y0, x1 - radius, y0, x1, y0,
        x1, y0 + radius, x1, y1 - radius, x1, y1,
        x1 - radius, y1, x0 + radius, y1, x0, y1,
        x0, y1 - radius, x0, y0 + radius, x0, y0,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class PillBar(tk.Canvas):
    """A horizontal rounded track whose coloured fill encodes a proportion.

    The pastel/coral/violet/amber/emerald/blue palette and the floating
    percentage label reproduce the ``Calibrated Routing / Space`` column of the
    reference design.
    """

    def __init__(self, master: tk.Misc, theme: type[Theme] = Theme,
                 width: int = 156, height: int = 22, bg: str | None = None,
                 font: tuple | None = None, **kwargs: Any) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg or theme.SURFACE,
            highlightthickness=0,
            borderwidth=0,
            **kwargs,
        )
        self._theme = theme
        self._width = int(width)
        self._height = int(height)
        self._radius = self._height / 2.0
        self._font = font or ("TkDefaultFont", 10, "bold")
        self._track = rounded_rect(
            self, 1, 1, self._width - 1, self._height - 1, self._radius,
            fill=theme.BORDER, outline="",
        )
        self._fill = rounded_rect(
            self, 1, 1, 2, self._height - 1, self._radius,
            fill=theme.TEXT_FAINT, outline="",
        )
        self._text = self.create_text(
            self._width / 2.0, self._height / 2.0, text="", fill=theme.TEXT,
            font=self._font,
        )

    def set(self, fraction: float, text: str, color: str) -> None:
        fraction = max(0.0, min(1.0, float(fraction)))
        inner = self._width - 2
        fill_width = inner * fraction
        if fraction > 0.0:
            fill_width = max(self._height - 2, fill_width)
        coords = (1, 1, 1 + fill_width, self._height - 1)
        self.coords(self._fill, *_rounded_points(coords, self._radius))
        self.itemconfigure(self._fill, fill=color)
        self.itemconfigure(self._text, text=text, fill=readable_on(color) if fraction > 0.55 else self._theme.TEXT)
        self.tag_raise(self._text)
        self._relayout_text()

    def _relayout_text(self) -> None:
        self.coords(self._text, self._width / 2.0, self._height / 2.0)


def _rounded_points(box: tuple[float, float, float, float], radius: float) -> list[float]:
    """Point list for a smooth rounded rectangle (used by :class:`PillBar`)."""
    x0, y0, x1, y1 = box
    radius = max(0.0, min(radius, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    return [
        x0 + radius, y0, x1 - radius, y0, x1, y0,
        x1, y0 + radius, x1, y1 - radius, x1, y1,
        x1 - radius, y1, x0 + radius, y1, x0, y1,
        x0, y1 - radius, x0, y0 + radius, x0, y0,
    ]


# --------------------------------------------------------------------------- #
# Settings dialog
# --------------------------------------------------------------------------- #
class SettingsDialog(ctk.CTkToplevel):
    """Modal editor for the persisted :class:`SortwiseConfig`."""

    def __init__(
        self,
        master: tk.Misc,
        config: SortwiseConfig,
        on_save: Callable[[dict[str, Any]], None],
        theme: type[Theme] = Theme,
    ) -> None:
        super().__init__(master)
        self._theme = theme
        self._config = config
        self._on_save = on_save

        self.title("Sortwise settings")
        self.geometry("780x720")
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)
        self.transient(master)  # type: ignore[arg-type]
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(
            self, text="ROUTER SETTINGS", font=ctk.CTkFont(size=theme.FONT_HEADER_SMALL, weight="bold"),
            text_color=theme.TEXT, anchor="w",
        ).pack(fill="x", padx=26, pady=(24, 6))
        ctk.CTkLabel(
            self,
            text="Where documents are collected from, where they are filed, and how\n"
                 "confident the router must be before it acts on its own.",
            font=ctk.CTkFont(size=theme.FONT_BASE), text_color=theme.TEXT_FAINT,
            justify="left", anchor="w",
        ).pack(fill="x", padx=26, pady=(0, 18))

        body = ctk.CTkFrame(
            self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS,
            border_width=1, border_color=theme.BORDER,
        )
        body.pack(fill="both", expand=True, padx=26, pady=(0, 18))
        body.grid_columnconfigure(1, weight=1)

        self._watch = self._path_row(body, 0, "WATCH FOLDER", config.watch_folder)
        self._target = self._path_row(body, 2, "TARGET ROOT", config.target_root)

        ctk.CTkFrame(body, height=1, fg_color=theme.BORDER).grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=12
        )

        self._confidence, _ = self._slider_row(
            body, 5, "CONFIDENCE GATE", 0.0, 1.0, float(config.confidence_threshold), 2
        )
        self._entropy, _ = self._slider_row(
            body, 7, "ENTROPY GATE (BITS)", 0.0, 5.0, float(config.entropy_threshold), 2
        )

        self._auto_move = ctk.CTkSwitch(
            body, text="Move files automatically once a decision is confident",
            font=ctk.CTkFont(size=theme.FONT_BASE), text_color=theme.TEXT_MUTED,
            fg_color=theme.BORDER_STRONG, progress_color=theme.ACCENT,
            button_color=theme.TEXT, button_hover_color=theme.TEXT, width=520,
        )
        self._auto_move.grid(row=9, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 8))
        if config.auto_move:
            self._auto_move.select()

        self._recursive = ctk.CTkSwitch(
            body, text="Scan the watch folder recursively",
            font=ctk.CTkFont(size=theme.FONT_BASE), text_color=theme.TEXT_MUTED,
            fg_color=theme.BORDER_STRONG, progress_color=theme.ACCENT,
            button_color=theme.TEXT, button_hover_color=theme.TEXT, width=520,
        )
        self._recursive.grid(row=10, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 20))
        if config.recursive:
            self._recursive.select()

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=26, pady=(0, 24))
        ctk.CTkButton(
            actions, text="Cancel", width=140, height=44, corner_radius=theme.RADIUS_SMALL,
            fg_color=theme.ELEVATED, hover_color=theme.HOVER, border_width=1,
            border_color=theme.BORDER, text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.FONT_BUTTON), command=self.destroy,
        ).pack(side="right", padx=(12, 0))
        ctk.CTkButton(
            actions, text="Save settings", width=180, height=44, corner_radius=theme.RADIUS_SMALL,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_DEEP, text_color="#ffffff",
            font=ctk.CTkFont(size=theme.FONT_BUTTON, weight="bold"), command=self._save,
        ).pack(side="right")

        self.after(60, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:  # pragma: no cover - window already gone
            pass

    def _path_row(self, parent: ctk.CTkFrame, row: int, label: str, value: str) -> ctk.CTkEntry:
        ctk.CTkLabel(
            parent, text=label, font=ctk.CTkFont(size=self._theme.FONT_SECTION, weight="bold"),
            text_color=self._theme.TEXT_FAINT, anchor="w",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 6))

        entry = ctk.CTkEntry(
            parent, height=44, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.BG, border_color=self._theme.BORDER,
            text_color=self._theme.TEXT, font=ctk.CTkFont(size=self._theme.FONT_BASE),
        )
        entry.insert(0, value)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=(20, 10), pady=(0, 2))
        ctk.CTkButton(
            parent, text="Browse", width=104, height=44, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.ELEVATED, hover_color=self._theme.HOVER, border_width=1,
            border_color=self._theme.BORDER, text_color=self._theme.TEXT_MUTED,
            font=ctk.CTkFont(size=self._theme.FONT_BASE), command=lambda: self._browse(entry),
        ).grid(row=row + 1, column=1, sticky="e", padx=(0, 20), pady=(0, 2))
        return entry

    def _slider_row(
        self, parent: ctk.CTkFrame, row: int, label: str,
        low: float, high: float, value: float, decimals: int,
    ) -> tuple[ctk.CTkSlider, ctk.CTkLabel]:
        ctk.CTkLabel(
            parent, text=label, font=ctk.CTkFont(size=self._theme.FONT_SECTION, weight="bold"),
            text_color=self._theme.TEXT_FAINT, anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=20, pady=(8, 2))
        value_label = ctk.CTkLabel(
            parent, text=f"{value:.{decimals}f}",
            font=ctk.CTkFont(size=self._theme.FONT_BASE, weight="bold"),
            text_color=self._theme.TEXT, anchor="e",
        )
        value_label.grid(row=row, column=1, sticky="e", padx=20, pady=(8, 2))

        slider = ctk.CTkSlider(
            parent, from_=low, to=high, number_of_steps=100, height=22,
            fg_color=self._theme.BG, progress_color=self._theme.ACCENT,
            button_color=self._theme.TEXT, button_hover_color=self._theme.TEXT,
            command=lambda number: value_label.configure(text=f"{number:.{decimals}f}"),
        )
        slider.set(value)
        slider.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 6))
        return slider, value_label

    def _browse(self, entry: ctk.CTkEntry) -> None:
        initial = entry.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(initialdir=initial, parent=self)
        if chosen:
            entry.delete(0, "end")
            entry.insert(0, chosen)

    def _save(self) -> None:
        changes = {
            "watch_folder": self._watch.get().strip(),
            "target_root": self._target.get().strip(),
            "confidence_threshold": float(self._confidence.get()),
            "entropy_threshold": float(self._entropy.get()),
            "auto_move": bool(self._auto_move.get()),
            "recursive": bool(self._recursive.get()),
        }
        self.destroy()
        self._on_save(changes)


# --------------------------------------------------------------------------- #
# Startup scanner dialogs
# --------------------------------------------------------------------------- #
class ScanSetupDialog(ctk.CTkToplevel):
    """The launch-time chooser: scan one folder or the whole system.

    ``on_start(mode, roots, recursive)`` is invoked when the user commits, with
    ``mode`` either ``"folder"`` (Mode A) or ``"deep"`` (Mode B).  ``on_skip``
    is called when the dialog is dismissed without scanning.
    """

    def __init__(
        self,
        master: tk.Misc,
        theme: type[Theme] = Theme,
        *,
        on_start: Callable[[str, list[str], bool], None],
        on_skip: Callable[[], None] | None = None,
        home: str | os.PathLike[str] | None = None,
        default_folder: str | None = None,
    ) -> None:
        super().__init__(master)
        self._theme = theme
        self._on_start = on_start
        self._on_skip = on_skip
        self._home = Path(expand_path(home)) if home else Path.home()

        self.title(f"{APP_NAME} - scan for documents")
        self.geometry("940x690")
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._skip)

        ctk.CTkLabel(
            self, text="SCAN FOR DOCUMENTS",
            font=ctk.CTkFont(size=theme.FONT_HEADER, weight="bold"),
            text_color=theme.TEXT, anchor="w",
        ).pack(fill="x", padx=28, pady=(26, 4))
        ctk.CTkLabel(
            self,
            text="Sortwise walks the tree on a worker-thread pool, skips system and cache\n"
                 "folders, and rates every document it finds as CONFIDENT or REVIEW.",
            font=ctk.CTkFont(size=theme.FONT_BASE), text_color=theme.TEXT_FAINT,
            justify="left", anchor="w",
        ).pack(fill="x", padx=28, pady=(0, 18))

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="both", expand=True, padx=28, pady=(0, 12))
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)
        cards.grid_rowconfigure(0, weight=1)

        self._folder = self._build_folder_card(cards, default_folder)
        self._build_deep_card(cards)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=28, pady=(0, 24))
        self._recursive = ctk.CTkSwitch(
            footer, text="Scan sub-folders recursively",
            font=ctk.CTkFont(size=theme.FONT_BASE), text_color=theme.TEXT_MUTED,
            fg_color=theme.BORDER_STRONG, progress_color=theme.ACCENT,
            button_color=theme.TEXT, button_hover_color=theme.TEXT, width=360,
        )
        self._recursive.select()
        self._recursive.pack(side="left")
        ctk.CTkButton(
            footer, text="Skip for now", width=170, height=46,
            corner_radius=theme.RADIUS_SMALL, fg_color=theme.ELEVATED,
            hover_color=theme.HOVER, border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=theme.FONT_BUTTON),
            command=self._skip,
        ).pack(side="right")

        self.after(60, self._grab)

    # -- cards ------------------------------------------------------------- #
    def _build_folder_card(self, parent: tk.Misc, default_folder: str | None) -> ctk.CTkEntry:
        theme = self._theme
        card = ctk.CTkFrame(
            parent, fg_color=theme.SURFACE, corner_radius=theme.RADIUS,
            border_width=1, border_color=theme.BORDER,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Mode A - Scan a folder",
            font=ctk.CTkFont(size=theme.FONT_HEADER_SMALL, weight="bold"),
            text_color=theme.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 2))
        ctk.CTkLabel(
            card, text="Point Sortwise at Downloads, Documents or any directory.",
            font=ctk.CTkFont(size=theme.FONT_HINT), text_color=theme.TEXT_FAINT,
            anchor="w", justify="left", wraplength=380,
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 14))

        presets = preset_targets(self._home)
        preset_row = ctk.CTkFrame(card, fg_color="transparent")
        preset_row.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        for index, (label, path) in enumerate(presets):
            column = index % 2
            row = index // 2
            ctk.CTkButton(
                preset_row, text=label, width=176, height=40,
                corner_radius=theme.RADIUS_SMALL, fg_color=theme.ELEVATED,
                hover_color=theme.HOVER, border_width=1, border_color=theme.BORDER,
                text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=theme.FONT_BASE),
                command=lambda p=path: self._choose(p),
            ).grid(row=row, column=column, padx=4, pady=4, sticky="w")

        entry = ctk.CTkEntry(
            card, height=44, corner_radius=theme.RADIUS_SMALL,
            fg_color=theme.BG, border_color=theme.BORDER,
            text_color=theme.TEXT, placeholder_text="Folder to scan",
            font=ctk.CTkFont(size=theme.FONT_BASE),
        )
        entry.grid(row=3, column=0, sticky="ew", padx=22, pady=(4, 8))
        entry.insert(0, default_folder or (presets[0][1] if presets else str(self._home)))

        browse = ctk.CTkFrame(card, fg_color="transparent")
        browse.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 10))
        ctk.CTkButton(
            browse, text="Browse...", width=130, height=42,
            corner_radius=theme.RADIUS_SMALL, fg_color=theme.ELEVATED,
            hover_color=theme.HOVER, border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=theme.FONT_BUTTON),
            command=lambda: self._browse(entry),
        ).pack(side="left")

        ctk.CTkButton(
            card, text="Scan this folder", height=46,
            corner_radius=theme.RADIUS_SMALL, fg_color=theme.ACCENT_DEEP,
            hover_color=theme.ACCENT, text_color="#ffffff",
            font=ctk.CTkFont(size=theme.FONT_BUTTON, weight="bold"),
            command=lambda: self._start("folder", entry),
        ).grid(row=5, column=0, sticky="ew", padx=22, pady=(4, 20))
        return entry

    def _build_deep_card(self, parent: tk.Misc) -> None:
        theme = self._theme
        card = ctk.CTkFrame(
            parent, fg_color=theme.SURFACE, corner_radius=theme.RADIUS,
            border_width=1, border_color=theme.BORDER,
        )
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Mode B - Deep system scan",
            font=ctk.CTkFont(size=theme.FONT_HEADER_SMALL, weight="bold"),
            text_color=theme.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 2))
        ctk.CTkLabel(
            card,
            text="High-throughput multi-threaded walk for unorganised study documents.",
            font=ctk.CTkFont(size=theme.FONT_HINT), text_color=theme.TEXT_FAINT,
            anchor="w", justify="left", wraplength=380,
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 10))

        self._deep_target = "home"
        target_frame = ctk.CTkFrame(card, fg_color="transparent")
        target_frame.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 8))
        target_frame.grid_columnconfigure(0, weight=1)
        target_frame.grid_columnconfigure(1, weight=1)

        def set_target(t: str) -> None:
            self._deep_target = t
            if t == "home":
                self._deep_target_lbl.configure(text=f"Target: {self._home}")
                btn_home.configure(fg_color=theme.ACCENT, text_color="#ffffff")
                btn_os.configure(fg_color=theme.ELEVATED, text_color=theme.TEXT_MUTED)
            else:
                self._deep_target_lbl.configure(text="Target: / (Entire OS Filesystem)")
                btn_os.configure(fg_color=theme.ACCENT, text_color="#ffffff")
                btn_home.configure(fg_color=theme.ELEVATED, text_color=theme.TEXT_MUTED)

        btn_home = ctk.CTkButton(
            target_frame, text="User Home (~)", height=38,
            corner_radius=theme.RADIUS_SMALL, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_DEEP, text_color="#ffffff",
            font=ctk.CTkFont(size=theme.FONT_BASE, weight="bold"),
            command=lambda: set_target("home"),
        )
        btn_home.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        btn_os = ctk.CTkButton(
            target_frame, text="Entire OS (/)", height=38,
            corner_radius=theme.RADIUS_SMALL, fg_color=theme.ELEVATED,
            hover_color=theme.HOVER, border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.FONT_BASE, weight="bold"),
            command=lambda: set_target("os"),
        )
        btn_os.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        self._deep_target_lbl = ctk.CTkLabel(
            card, text=f"Target: {self._home}",
            font=ctk.CTkFont(size=theme.FONT_MONO), text_color=theme.TEXT_MUTED,
            anchor="w", justify="left", wraplength=380,
        )
        self._deep_target_lbl.grid(row=3, column=0, sticky="w", padx=22, pady=(0, 8))

        excludes = ctk.CTkLabel(
            card,
            text="Skips /proc  /sys  /dev  /nix/store  .git  node_modules  .cache",
            font=ctk.CTkFont(size=theme.FONT_HINT), text_color=theme.TEXT_FAINT,
            anchor="w", justify="left", wraplength=380,
        )
        excludes.grid(row=4, column=0, sticky="w", padx=22, pady=(0, 8))

        for row, line in enumerate(
            (
                "BCUninstaller-style worker pool with live status ticker.",
                "Every file scored against semester taxonomy and confidence-rated.",
                "Safe preview first: nothing is moved until you commit.",
            ),
            start=5,
        ):
            ctk.CTkLabel(
                card, text=f"• {line}", font=ctk.CTkFont(size=theme.FONT_HINT),
                text_color=theme.TEXT_MUTED, anchor="w", justify="left", wraplength=380,
            ).grid(row=row, column=0, sticky="w", padx=22, pady=2)

        ctk.CTkButton(
            card, text="Start deep scan", height=46,
            corner_radius=theme.RADIUS_SMALL, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_DEEP, text_color="#ffffff",
            font=ctk.CTkFont(size=theme.FONT_BUTTON, weight="bold"),
            command=lambda: self._start("deep", None),
        ).grid(row=9, column=0, sticky="ew", padx=22, pady=(16, 20), rowspan=1)

    # -- actions ----------------------------------------------------------- #
    def _choose(self, path: str) -> None:
        self._folder.delete(0, "end")
        self._folder.insert(0, path)

    def _browse(self, entry: ctk.CTkEntry) -> None:
        initial = entry.get().strip() or str(self._home)
        chosen = filedialog.askdirectory(initialdir=initial, parent=self)
        if chosen:
            entry.delete(0, "end")
            entry.insert(0, chosen)

    def _start(self, mode: str, entry: ctk.CTkEntry | None) -> None:
        if mode == "deep":
            target = getattr(self, "_deep_target", "home")
            roots = ["/"] if target == "os" else [str(self._home)]
        else:
            raw = (entry.get().strip() if entry is not None else "") or str(self._home)
            folder = expand_path(raw)
            if not folder.is_dir():
                messagebox.showwarning(
                    APP_NAME, f"Not a folder:\n{folder}", parent=self
                )
                return
            roots = [str(folder)]
        recursive = bool(self._recursive.get())
        self.destroy()
        self._on_start(mode, roots, recursive)

    def _skip(self) -> None:
        self.destroy()
        if self._on_skip is not None:
            self._on_skip()

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:  # pragma: no cover - window already gone
            pass


class ScanProgressDialog(ctk.CTkToplevel):
    """A live, cancellable view of the multi-threaded disk walk."""

    def __init__(
        self,
        master: tk.Misc,
        theme: type[Theme] = Theme,
        *,
        on_cancel: Callable[[], None] | None = None,
        roots: Sequence[str] | None = None,
    ) -> None:
        super().__init__(master)
        self._theme = theme
        self._on_cancel = on_cancel
        self._cancelled = False

        self.title(f"{APP_NAME} - scanning")
        self.geometry("760x440")
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        ctk.CTkLabel(
            self, text="SCANNING DISK",
            font=ctk.CTkFont(size=theme.FONT_HEADER, weight="bold"),
            text_color=theme.TEXT, anchor="w",
        ).pack(fill="x", padx=28, pady=(26, 2))
        where = " · ".join(roots) if roots else "the selected folders"
        self._roots = ctk.CTkLabel(
            self, text=where, font=ctk.CTkFont(size=theme.FONT_MONO_SMALL),
            text_color=theme.TEXT_FAINT, anchor="w", justify="left", wraplength=700,
        )
        self._roots.pack(fill="x", padx=28, pady=(0, 16))

        self._bar = ctk.CTkProgressBar(
            self, mode="indeterminate", height=10, corner_radius=5,
            fg_color=theme.ELEVATED, progress_color=theme.ACCENT,
        )
        self._bar.pack(fill="x", padx=28, pady=(0, 18))
        try:
            self._bar.start()
        except Exception:  # pragma: no cover - very old customtkinter
            pass

        stats = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS,
                             border_width=1, border_color=theme.BORDER)
        stats.pack(fill="x", padx=28, pady=(0, 14))
        for column in range(3):
            stats.grid_columnconfigure(column, weight=1)
        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        for column, (key, caption) in enumerate(
            (("documents", "DOCUMENTS"), ("files", "FILES"), ("folders", "FOLDERS"))
        ):
            ctk.CTkLabel(
                stats, text=caption, font=ctk.CTkFont(size=theme.FONT_MONO_SMALL, weight="bold"),
                text_color=theme.TEXT_FAINT,
            ).grid(row=0, column=column, pady=(14, 0))
            value = ctk.CTkLabel(
                stats, text="0", font=ctk.CTkFont(size=theme.FONT_HEADER_SMALL, weight="bold"),
                text_color=theme.TEXT,
            )
            value.grid(row=1, column=column, pady=(0, 14))
            self._stat_labels[key] = value

        self._current = ctk.CTkLabel(
            self, text="Starting…", font=ctk.CTkFont(size=theme.FONT_MONO),
            text_color=theme.TEXT_MUTED, anchor="w", justify="left", wraplength=700,
        )
        self._current.pack(fill="x", padx=28, pady=(0, 6))
        self._elapsed = ctk.CTkLabel(
            self, text="elapsed 0.0s", font=ctk.CTkFont(size=theme.FONT_MONO_SMALL),
            text_color=theme.TEXT_FAINT, anchor="w",
        )
        self._elapsed.pack(fill="x", padx=28)

        ctk.CTkButton(
            self, text="Cancel scan", width=180, height=46,
            corner_radius=theme.RADIUS_SMALL, fg_color=theme.ELEVATED,
            hover_color=theme.HOVER, border_width=1, border_color=theme.BORDER,
            text_color=theme.TEXT_MUTED, font=ctk.CTkFont(size=theme.FONT_BUTTON),
            command=self.cancel,
        ).pack(pady=(14, 22))

        self.after(60, self._grab)

    # -- updates ----------------------------------------------------------- #
    def update_progress(self, progress: ScanProgress) -> None:
        if self._cancelled:
            return
        try:
            self._stat_labels["documents"].configure(text=str(progress.documents))
            self._stat_labels["files"].configure(text=str(progress.files_seen))
            self._stat_labels["folders"].configure(text=str(progress.directories))
            current = progress.current or "…"
            if len(current) > 96:
                current = "…" + current[-95:]
            self._current.configure(text=current)
            self._elapsed.configure(
                text=f"elapsed {progress.elapsed:.1f}s · {human_size(progress.bytes_seen)} seen"
            )
        except tk.TclError:  # pragma: no cover - dialog torn down mid-update
            pass

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        try:
            self._current.configure(text="Cancelling…")
            self._bar.stop()
        except tk.TclError:  # pragma: no cover
            pass
        if self._on_cancel is not None:
            self._on_cancel()

    def _grab(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:  # pragma: no cover - window already gone
            pass


# --------------------------------------------------------------------------- #
# Application shell
# --------------------------------------------------------------------------- #
class SortwiseApp(ctk.CTk):
    """The physical Sortwise desktop window (finder-style two-pane browser)."""

    POLL_INTERVAL_MS = 90

    def __init__(
        self,
        master: tk.Misc | None = None,
        *,
        config_path: str | os.PathLike[str] | None = None,
        ledger_path: str | os.PathLike[str] | None = None,
        service: SortwiseService | None = None,
        classifier: Any | None = None,
        autoload: bool = True,
        show_scan_dialog: bool = True,
        theme: type[Theme] = Theme,
    ) -> None:
        ctk.set_appearance_mode("dark")
        self._theme = theme
        try:
            super().__init__(fg_color=theme.BG, className="sortwise")
        except TypeError:  # pragma: no cover - very old Tk builds
            super().__init__(fg_color=theme.BG)

        self._config_store = ConfigStore(
            Path(config_path) if config_path else default_config_path()
        )
        self._ledger = Ledger(Path(ledger_path) if ledger_path else default_ledger_path())
        self._service = service or SortwiseService(
            self._config_store, self._ledger, classifier=classifier
        )
        self._icons = Icons(theme=theme)

        self._events: "queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]]" = queue.Queue()
        self._busy = False
        self._closed = False
        self._poll_job: str | None = None
        self._classify_running = False

        # Disk-scan state (BCUninstaller-inspired startup + bulk flow)
        self._scan_dialog: ScanProgressDialog | None = None
        self._scan_cancel: threading.Event | None = None
        self._scan_running = False
        self._scan_results: list[DocItem] = []
        self._bulk_selected: set[str] = set()

        # Model state
        self._tree: list[DocItem] = []
        self._stats: dict[str, Any] = {}
        self._tree_size = 1
        self._items_by_key: dict[str, DocItem] = {}
        self._items_by_path: dict[str, DocItem] = {}
        self._expanded: set[str] = set()
        self._selected: DocItem | None = None
        self._doc_info: dict[str, Any] | None = None
        self._rename_dirty = False
        self._subject_values: list[str] = [AUTO_SUBJECT, *subject_labels()]

        # View + navigation history
        self._view: tuple[str, str | None] = ("all", None)
        self._history: list[tuple[str, str | None]] = [("all", None)]
        self._history_index = 0

        # Widget registries
        self._table_rows: list[tk.Misc] = []
        self._shelf_cards: dict[str, ctk.CTkFrame] = {}
        self._shelf_counts: dict[str, ctk.CTkLabel] = {}
        self._nav_rows: dict[str, ctk.CTkFrame] = {}
        self._nav_badges: dict[str, ctk.CTkLabel] = {}
        self._ledger_rows: list[tk.Misc] = []

        # Fonts
        self._family_ui: str | None = pick_font_family(self, UI_FONT_CANDIDATES)
        self._family_mono: str | None = pick_font_family(self, MONO_FONT_CANDIDATES)

        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}")
        self.minsize(*MIN_WINDOW_SIZE)
        self.configure(fg_color=theme.BG)
        self._center_window()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_ledger()
        self._set_view(("all", None), record=False)

        self._poll_job = self.after(self.POLL_INTERVAL_MS, self._drain_events)
        if autoload:
            self.after(120, self.load_document_tree)
        if show_scan_dialog:
            self.after(420, self.open_scan_dialog)

    # -- window ------------------------------------------------------------ #
    def _center_window(self) -> None:
        try:
            self.update_idletasks()
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            width, height = WINDOW_SIZE
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 3)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:  # pragma: no cover - headless
            pass

    def _on_close(self) -> None:
        self._closed = True
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except tk.TclError:  # pragma: no cover
                pass
            self._poll_job = None
        self.destroy()

    # -- fonts ------------------------------------------------------------- #
    def _ui_font(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        if self._family_ui:
            return ctk.CTkFont(family=self._family_ui, size=size, weight=weight)
        return ctk.CTkFont(size=size, weight=weight)

    def _mono_font(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        if self._family_mono:
            return ctk.CTkFont(family=self._family_mono, size=size, weight=weight)
        return self._ui_font(size, weight)

    def _tk_font(self, size: int, weight: str = "normal") -> tuple:
        """A plain tuple font, for widgets drawn on a raw :class:`tk.Canvas`."""
        if self._family_ui:
            return (self._family_ui, size, weight)
        return ("TkDefaultFont", size, weight)

    def _icon(self, name: str, size: int) -> ctk.CTkImage | None:
        return self._icons.image(name, size)

    # -- UI construction --------------------------------------------------- #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        main = ctk.CTkFrame(self, fg_color=self._theme.BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(0, self._theme.PAD),
                  pady=self._theme.PAD)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)
        self._main = main

        self._build_topnav(main)
        self._build_shelf(main)
        self._build_bulk_toolbar(main)
        self._build_content(main)
        self._build_ledger(main)

    def _card(self, parent: tk.Misc, **kwargs: Any) -> ctk.CTkFrame:
        options: dict[str, Any] = {
            "fg_color": self._theme.SURFACE,
            "corner_radius": self._theme.RADIUS,
            "border_width": 1,
            "border_color": self._theme.BORDER,
        }
        options.update(kwargs)
        return ctk.CTkFrame(parent, **options)

    def _section_label(self, parent: tk.Misc, text: str, **kwargs: Any) -> ctk.CTkLabel:
        options: dict[str, Any] = {
            "text": text,
            "font": self._ui_font(self._theme.FONT_SECTION, "bold"),
            "text_color": self._theme.TEXT_FAINT,
            "anchor": "w",
        }
        options.update(kwargs)
        return ctk.CTkLabel(parent, **options)

    @staticmethod
    def _bind_recursive(widget: tk.Misc, sequence: str, func: Callable) -> None:
        """Bind ``func`` to ``widget`` and every descendant."""
        try:
            widget.bind(sequence, func)
        except Exception:  # noqa: BLE001 - some Tk widgets refuse binds
            pass
        for child in widget.winfo_children():
            SortwiseApp._bind_recursive(child, sequence, func)

    # -- sidebar ----------------------------------------------------------- #
    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, fg_color=self._theme.SIDEBAR, corner_radius=0,
                            width=SIDEBAR_WIDTH)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(6, weight=1)
        self._sidebar = side

        # window control dots -------------------------------------------------
        dots = ctk.CTkFrame(side, fg_color="transparent")
        dots.grid(row=0, column=0, sticky="w", padx=18, pady=(16, 6))
        for colour in self._theme.WINDOW_DOTS:
            dot = ctk.CTkFrame(dots, width=12, height=12, corner_radius=6,
                               fg_color=colour, border_width=0)
            dot.pack(side="left", padx=(0, 8))
            dot.pack_propagate(False)
        ctk.CTkLabel(dots, text="SORTWISE", font=self._ui_font(self._theme.FONT_BASE, "bold"),
                     text_color=self._theme.TEXT_FAINT).pack(side="left", padx=(8, 0))

        # storage header ------------------------------------------------------
        storage = self._card(side, fg_color=self._theme.SURFACE)
        storage.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 8))
        storage.grid_columnconfigure(1, weight=1)
        disk = self._icon("disk.png", 42)
        if disk is not None:
            ctk.CTkLabel(storage, image=disk, text="").grid(
                row=0, column=0, rowspan=3, padx=(12, 12), pady=12
            )
        else:
            ctk.CTkLabel(storage, text="◍", font=self._ui_font(26, "bold"),
                         text_color=self._theme.ACCENT).grid(
                row=0, column=0, rowspan=3, padx=(12, 12), pady=12
            )
        ctk.CTkLabel(storage, text="Semester 3", font=self._ui_font(self._theme.FONT_SUBHEADER, "bold"),
                     text_color=self._theme.TEXT, anchor="w").grid(
            row=0, column=1, sticky="w", pady=(12, 0))
        ctk.CTkLabel(storage, text="Target Storage", font=self._ui_font(self._theme.FONT_HINT),
                     text_color=self._theme.TEXT_FAINT, anchor="w").grid(
            row=1, column=1, sticky="w")
        self._storage_size = ctk.CTkLabel(storage, text="—", font=self._mono_font(self._theme.FONT_MONO, "bold"),
                                          text_color=self._theme.SUCCESS, anchor="w")
        self._storage_size.grid(row=2, column=1, sticky="w", pady=(0, 12))

        ctk.CTkLabel(side, text="LOCATIONS", font=self._ui_font(self._theme.FONT_SECTION, "bold"),
                     text_color=self._theme.TEXT_FAINT, anchor="w").grid(
            row=2, column=0, sticky="w", padx=20, pady=(16, 6))

        # navigation list -----------------------------------------------------
        nav = ctk.CTkFrame(side, fg_color="transparent")
        nav.grid(row=3, column=0, sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        for index, (view, label, icon_name) in enumerate(NAV_ITEMS):
            self._nav_rows[view] = self._nav_row(nav, index, view, label, icon_name)

        # footer --------------------------------------------------------------
        footer = ctk.CTkFrame(side, fg_color="transparent")
        footer.grid(row=6, column=0, sticky="sew", padx=18, pady=14)
        self._status_dot = ctk.CTkLabel(footer, text="●", font=self._ui_font(self._theme.FONT_MONO),
                                        text_color=self._theme.TEXT_FAINT)
        self._status_dot.pack(side="left", padx=(0, 6))
        self._status_label = ctk.CTkLabel(footer, text="Idle", font=self._ui_font(self._theme.FONT_BASE),
                                          text_color=self._theme.TEXT_MUTED, anchor="w")
        self._status_label.pack(side="left")

    def _nav_row(self, parent: tk.Misc, row: int, view: str, label: str,
                 icon_name: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=self._theme.RADIUS_SMALL,
                             height=48)
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
        frame.grid_columnconfigure(2, weight=1)
        frame.grid_propagate(False)

        bar = ctk.CTkFrame(frame, width=3, height=26, corner_radius=2,
                           fg_color="transparent")
        bar.grid(row=0, column=0, padx=(4, 8), pady=11)

        icon = self._icon(icon_name, 22)
        if icon is not None:
            ctk.CTkLabel(frame, image=icon, text="").grid(row=0, column=1, padx=(0, 10))
        else:
            ctk.CTkLabel(frame, text="•", font=self._ui_font(self._theme.FONT_BASE),
                         text_color=self._theme.TEXT_MUTED).grid(row=0, column=1, padx=(0, 10))

        ctk.CTkLabel(frame, text=label, font=self._ui_font(self._theme.FONT_BASE),
                     text_color=self._theme.TEXT_MUTED, anchor="w").grid(
            row=0, column=2, sticky="w")
        badge = ctk.CTkLabel(frame, text="0", font=self._mono_font(self._theme.FONT_MONO_SMALL, "bold"),
                             text_color=self._theme.TEXT_MUTED, width=38,
                             fg_color=self._theme.ELEVATED, corner_radius=6,
                             height=26)
        badge.grid(row=0, column=3, padx=(6, 12))
        self._nav_badges[view] = badge
        frame._accent_bar = bar  # type: ignore[attr-defined]
        self._bind_recursive(frame, "<Button-1>", lambda _e, v=view: self._on_nav_click(v))
        self._bind_recursive(frame, "<Enter>", lambda _e, f=frame: self._nav_hover(f, True))
        self._bind_recursive(frame, "<Leave>", lambda _e, f=frame: self._nav_hover(f, False))
        return frame

    def _nav_hover(self, frame: ctk.CTkFrame, entering: bool) -> None:
        active = any(view for view, row in self._nav_rows.items() if row is frame and view == self._view[0])
        if entering:
            frame.configure(fg_color=self._theme.ELEVATED)
        elif not active:
            frame.configure(fg_color="transparent")

    # -- top navigation ---------------------------------------------------- #
    def _build_topnav(self, parent: tk.Misc) -> None:
        bar = self._card(parent)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, self._theme.GAP))
        bar.grid_columnconfigure(1, weight=1)

        nav = ctk.CTkFrame(bar, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="w", padx=(12, 6), pady=(12, 6))
        self._back_button = self._nav_arrow(nav, "<", self._nav_back)
        self._forward_button = self._nav_arrow(nav, ">", self._nav_forward)

        crumb = ctk.CTkFrame(bar, fg_color="transparent")
        crumb.grid(row=0, column=1, sticky="w", padx=6, pady=(12, 6))
        disk = self._icon("disk.png", 20)
        if disk is not None:
            ctk.CTkLabel(crumb, image=disk, text="").pack(side="left", padx=(0, 8))
        self._crumb_label = ctk.CTkLabel(
            crumb, text="> Home > Semester 3", font=self._mono_font(self._theme.FONT_MONO),
            text_color=self._theme.TEXT_MUTED, anchor="w",
        )
        self._crumb_label.pack(side="left")

        self._search = ctk.CTkEntry(
            bar, width=330, height=42, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.BG, border_color=self._theme.BORDER,
            text_color=self._theme.TEXT, placeholder_text="Search documents...",
            font=self._ui_font(self._theme.FONT_BASE),
        )
        self._search.grid(row=0, column=2, sticky="e", padx=(6, 14), pady=(12, 6))
        self._search.bind("<KeyRelease>", lambda _e: self._render_table())

        actions = ctk.CTkFrame(bar, fg_color="transparent")
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        self._scan_disk_button = self._action_button(actions, "Scan Disk", self.open_scan_dialog)
        self._scan_button = self._action_button(actions, "Scan Watch Dir", self.scan_watch_dir)
        self._auto_button = self._action_button(actions, "Auto-Route Confident", self.auto_route_confident)
        self._undo_button = self._action_button(actions, "Undo Last", self.undo_last, accent=False)
        self._settings_button = self._action_button(actions, "Settings", self.open_settings, accent=False)

        self._mode_label = ctk.CTkLabel(actions, text="", font=self._mono_font(self._theme.FONT_MONO_SMALL),
                                        text_color=self._theme.TEXT_FAINT)
        self._mode_label.pack(side="right", padx=(0, 4))

    def _nav_arrow(self, parent: tk.Misc, text: str, command: Callable[[], None]) -> ctk.CTkButton:
        button = ctk.CTkButton(
            parent, text=text, width=38, height=38, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.ELEVATED, hover_color=self._theme.HOVER, border_width=1,
            border_color=self._theme.BORDER, text_color=self._theme.TEXT_MUTED,
            font=self._ui_font(self._theme.FONT_BUTTON, "bold"), command=command,
        )
        button.pack(side="left", padx=(0, 6))
        return button

    def _action_button(
        self, parent: tk.Misc, text: str, command: Callable[[], None], *, accent: bool = True
    ) -> ctk.CTkButton:
        button = ctk.CTkButton(
            parent, text=text, width=178, height=42, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.ACCENT_DEEP if accent else self._theme.ELEVATED,
            hover_color=self._theme.ACCENT if accent else self._theme.HOVER,
            border_width=0 if accent else 1, border_color=self._theme.BORDER,
            text_color="#ffffff" if accent else self._theme.TEXT_MUTED,
            font=self._ui_font(self._theme.FONT_BUTTON, "bold" if accent else "normal"),
            command=command,
        )
        button.pack(side="left", padx=5)
        return button

    # -- folder shelf (Image 1) -------------------------------------------- #
    def _build_shelf(self, parent: tk.Misc) -> None:
        card = self._card(parent, height=SHELF_HEIGHT)
        card.grid(row=1, column=0, sticky="ew", pady=(0, self._theme.GAP))
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 2))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="SEMESTER 3", font=self._ui_font(self._theme.FONT_SUBHEADER, "bold"),
                     text_color=self._theme.TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Click a folder to filter · double-click the table to open",
                     font=self._ui_font(self._theme.FONT_HINT), text_color=self._theme.TEXT_FAINT, anchor="w").grid(
            row=0, column=1, sticky="w", padx=(12, 0))
        self._shelf_hint = ctk.CTkLabel(header, text="", font=self._mono_font(self._theme.FONT_MONO_SMALL),
                                        text_color=self._theme.TEXT_FAINT, anchor="e")
        self._shelf_hint.grid(row=0, column=2, sticky="e")

        strip = ctk.CTkFrame(card, fg_color="transparent")
        strip.grid(row=1, column=0, sticky="nsew", padx=12, pady=(2, 10))
        for column in range(len(SHELF_CARDS)):
            strip.grid_columnconfigure(column, weight=1, uniform="shelf")
        for column, (card_key, label, icon_name) in enumerate(SHELF_CARDS):
            self._shelf_cards[card_key] = self._shelf_card(strip, column, card_key, label, icon_name)

    def _shelf_card(self, parent: tk.Misc, column: int, card_key: str, label: str,
                    icon_name: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent, fg_color=self._theme.BG, corner_radius=self._theme.RADIUS,
            border_width=1, border_color=self._theme.BORDER,
        )
        frame.grid(row=0, column=column, sticky="nsew", padx=3, pady=2)
        frame.grid_columnconfigure(0, weight=1)

        icon = self._icon(icon_name, 56)
        if icon is not None:
            ctk.CTkLabel(frame, image=icon, text="").grid(row=0, column=0, pady=(10, 2))
        else:
            ctk.CTkLabel(frame, text="📁", font=self._ui_font(30)).grid(row=0, column=0, pady=(10, 2))

        ctk.CTkLabel(frame, text=label, font=self._ui_font(self._theme.FONT_TABLE, "bold"),
                     text_color=self._theme.TEXT, wraplength=124, justify="center").grid(
            row=1, column=0, pady=(0, 0))
        count = ctk.CTkLabel(frame, text="empty", font=self._mono_font(self._theme.FONT_MONO_SMALL),
                             text_color=self._theme.TEXT_FAINT)
        count.grid(row=2, column=0, pady=(0, 8))
        self._shelf_counts[card_key] = count

        self._bind_recursive(frame, "<Button-1>", lambda _e, key=card_key: self._on_card_click(key))
        self._bind_recursive(frame, "<Enter>", lambda _e, f=frame: self._shelf_hover(f, True))
        self._bind_recursive(frame, "<Leave>", lambda _e, f=frame: self._shelf_hover(f, False))
        return frame

    def _shelf_hover(self, frame: ctk.CTkFrame, entering: bool) -> None:
        if self._card_active(frame):
            return
        frame.configure(fg_color=self._theme.ELEVATED if entering else self._theme.BG)

    def _card_key_of(self, frame: ctk.CTkFrame) -> str | None:
        for key, widget in self._shelf_cards.items():
            if widget is frame:
                return key
        return None

    def _card_active(self, frame: ctk.CTkFrame) -> bool:
        key = self._card_key_of(frame)
        return bool(key) and self._view == ("card", key)

    # -- bulk action toolbar (BCUninstaller-style) ------------------------- #
    def _build_bulk_toolbar(self, parent: tk.Misc) -> None:
        bar = self._card(parent, height=BULK_HEIGHT)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, self._theme.GAP))
        bar.grid_propagate(False)
        bar.grid_columnconfigure(2, weight=1)
        self._bulk_bar = bar

        self._bulk_confident = ctk.CTkCheckBox(
            bar, text="Select All Confident",
            font=self._ui_font(self._theme.FONT_TABLE, "bold"),
            text_color=self._theme.TEXT, fg_color=self._theme.ACCENT,
            hover_color=self._theme.ACCENT_DEEP, border_color=self._theme.BORDER_STRONG,
            checkmark_color="#ffffff", corner_radius=6,
            command=self._toggle_all_confident, width=230, height=32,
        )
        self._bulk_confident.grid(row=0, column=0, padx=(18, 20), pady=11, sticky="w")

        self._bulk_summary = ctk.CTkLabel(
            bar, text="0 documents found",
            font=self._mono_font(self._theme.FONT_MONO_SMALL),
            text_color=self._theme.TEXT_MUTED, anchor="w",
        )
        self._bulk_summary.grid(row=0, column=1, sticky="w")

        self._batch_progress = ctk.CTkProgressBar(
            bar, width=240, height=8, corner_radius=4,
            fg_color=self._theme.ELEVATED, progress_color=self._theme.ACCENT,
        )
        self._batch_progress.set(0.0)
        self._batch_progress.grid(row=0, column=2, padx=18, sticky="e")

        self._batch_button = ctk.CTkButton(
            bar, text="Batch Route", width=178, height=42,
            corner_radius=self._theme.RADIUS_SMALL, fg_color=self._theme.ACCENT_DEEP,
            hover_color=self._theme.ACCENT, text_color="#ffffff",
            font=self._ui_font(self._theme.FONT_BUTTON, "bold"),
            command=self.batch_route_selected,
        )
        self._batch_button.grid(row=0, column=3, padx=(0, 10), pady=7, sticky="e")

        ctk.CTkButton(
            bar, text="Clear results", width=148, height=42,
            corner_radius=self._theme.RADIUS_SMALL, fg_color=self._theme.ELEVATED,
            hover_color=self._theme.HOVER, border_width=1, border_color=self._theme.BORDER,
            text_color=self._theme.TEXT_MUTED, font=self._ui_font(self._theme.FONT_BUTTON),
            command=self.clear_scan_results,
        ).grid(row=0, column=4, padx=(0, 18), pady=7, sticky="e")

        bar.grid_remove()

    def _show_bulk_bar(self, show: bool) -> None:
        try:
            if show:
                self._bulk_bar.grid()
            else:
                self._bulk_bar.grid_remove()
        except tk.TclError:  # pragma: no cover - window teardown
            pass

    # -- content: table + inspector ---------------------------------------- #
    def _build_content(self, parent: tk.Misc) -> None:
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.grid(row=3, column=0, sticky="nsew", pady=(0, self._theme.GAP))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=0, minsize=INSPECTOR_WIDTH)
        content.grid_rowconfigure(0, weight=1)

        self._build_table(content)
        self._build_inspector(content)

    def _build_table(self, parent: tk.Misc) -> None:
        card = self._card(parent)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, self._theme.GAP))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        for index, (name, minsize, weight) in enumerate(COLUMNS):
            header.grid_columnconfigure(index, minsize=minsize, weight=weight)
        captions = {
            0: "", 1: "", 2: "Name", 3: "Size", 4: "Calibrated Routing / Space", 5: "Status",
        }
        sticky_for = {2: "ew", 3: "w", 4: "w", 5: "w"}
        for index, text in captions.items():
            anchor = "w" if index in (2, 3, 4, 5) else "center"
            self._section_label(header, text, anchor=anchor, font=self._ui_font(self._theme.FONT_PILL, "bold")).grid(
                row=0, column=index, sticky=sticky_for.get(index, ""),
                padx=(0, 10) if index < 5 else (0, 0),
            )

        body = ctk.CTkScrollableFrame(
            card, fg_color=self._theme.BG, corner_radius=self._theme.RADIUS_SMALL,
            border_width=1, border_color=self._theme.BORDER,
            scrollbar_button_color=self._theme.BORDER_STRONG,
            scrollbar_button_hover_color=self._theme.HOVER,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        for index, (_name, minsize, weight) in enumerate(COLUMNS):
            body.grid_columnconfigure(index, minsize=minsize, weight=weight)
        self._table_body = body

    # -- inspector --------------------------------------------------------- #
    def _build_inspector(self, parent: tk.Misc) -> None:
        card = self._card(parent)
        card.grid(row=0, column=1, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        ctk.CTkLabel(head, text="DOCUMENT INSPECTOR", font=self._ui_font(self._theme.FONT_HEADER_SMALL, "bold"),
                     text_color=self._theme.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(head, text="selected document & in-flight renamer",
                     font=self._ui_font(self._theme.FONT_HINT), text_color=self._theme.TEXT_FAINT, anchor="w").pack(anchor="w")

        body = ctk.CTkScrollableFrame(
            card, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=self._theme.BORDER_STRONG,
            scrollbar_button_hover_color=self._theme.HOVER,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)

        self._doc_name = ctk.CTkLabel(
            body, text="No document selected", font=self._ui_font(self._theme.FONT_HEADER, "bold"),
            text_color=self._theme.TEXT, anchor="w", justify="left", wraplength=368,
        )
        self._doc_name.grid(row=0, column=0, sticky="ew", padx=(10, 12), pady=(6, 2))
        self._doc_path = ctk.CTkLabel(
            body, text="Pick a folder or a document in the table to inspect it.",
            font=self._mono_font(self._theme.FONT_MONO_SMALL), text_color=self._theme.TEXT_FAINT,
            anchor="w", justify="left", wraplength=368,
        )
        self._doc_path.grid(row=1, column=0, sticky="ew", padx=(10, 12), pady=(0, 8))

        tags = ctk.CTkFrame(body, fg_color="transparent")
        tags.grid(row=2, column=0, sticky="w", padx=(10, 12))
        self._pill_format = self._pill(tags, "—")
        self._pill_size = self._pill(tags, "—")
        self._pill_pages = self._pill(tags, "—")

        self._section_label(body, "SUBJECT MATCH").grid(
            row=3, column=0, sticky="w", padx=(10, 12), pady=(12, 4))
        badge = ctk.CTkFrame(body, fg_color=self._theme.ELEVATED, corner_radius=self._theme.RADIUS_SMALL,
                             border_width=1, border_color=self._theme.BORDER)
        badge.grid(row=4, column=0, sticky="ew", padx=(10, 12))
        badge.grid_columnconfigure(1, weight=1)
        self._badge_dot = ctk.CTkLabel(badge, text="●", font=self._ui_font(self._theme.FONT_MONO),
                                       text_color=self._theme.TEXT_FAINT)
        self._badge_dot.grid(row=0, column=0, padx=(12, 8), pady=10)
        self._badge_label = ctk.CTkLabel(badge, text="awaiting a selection",
                                         font=self._ui_font(self._theme.FONT_TABLE, "bold"),
                                         text_color=self._theme.TEXT_MUTED, anchor="w")
        self._badge_label.grid(row=0, column=1, sticky="w", pady=10)
        self._badge_state = ctk.CTkLabel(badge, text="", font=self._mono_font(self._theme.FONT_MONO_SMALL, "bold"),
                                         text_color=self._theme.TEXT_FAINT)
        self._badge_state.grid(row=0, column=2, sticky="e", padx=(0, 12), pady=10)

        override = ctk.CTkFrame(body, fg_color="transparent")
        override.grid(row=5, column=0, sticky="ew", padx=(10, 20), pady=(10, 0))
        override.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(override, text="Override", font=self._ui_font(self._theme.FONT_HINT),
                     text_color=self._theme.TEXT_FAINT, anchor="w").grid(row=0, column=0, sticky="w")
        self._subject_menu = ctk.CTkOptionMenu(
            override, values=self._subject_values, height=40,
            corner_radius=self._theme.RADIUS_SMALL, fg_color=self._theme.BG,
            button_color=self._theme.ELEVATED, button_hover_color=self._theme.HOVER,
            text_color=self._theme.TEXT, dropdown_fg_color=self._theme.ELEVATED,
            dropdown_hover_color=self._theme.HOVER, dropdown_text_color=self._theme.TEXT,
            font=self._ui_font(self._theme.FONT_BASE),
            dropdown_font=self._ui_font(self._theme.FONT_BASE), anchor="w",
            command=self._on_subject_override,
        )
        self._subject_menu.set(AUTO_SUBJECT)
        self._subject_menu.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        confidence_row = ctk.CTkFrame(body, fg_color="transparent")
        confidence_row.grid(row=6, column=0, sticky="ew", padx=(10, 12), pady=(12, 0))
        confidence_row.grid_columnconfigure(0, weight=1)
        self._section_label(confidence_row, "CONFIDENCE", anchor="w").grid(row=0, column=0, sticky="w")
        self._confidence_label = ctk.CTkLabel(confidence_row, text="—",
                                              font=self._mono_font(self._theme.FONT_MONO, "bold"),
                                              text_color=self._theme.TEXT, anchor="e")
        self._confidence_label.grid(row=0, column=1, sticky="e")
        self._confidence_bar = ctk.CTkProgressBar(
            body, height=8, corner_radius=4, fg_color=self._theme.BG,
            progress_color=self._theme.ACCENT,
        )
        self._confidence_bar.set(0.0)
        self._confidence_bar.grid(row=7, column=0, sticky="ew", padx=(10, 12), pady=(6, 8))

        metrics = ctk.CTkFrame(body, fg_color="transparent")
        metrics.grid(row=8, column=0, sticky="ew", padx=(10, 12))
        metrics.grid_columnconfigure(0, weight=1)
        self._entropy_label = ctk.CTkLabel(
            metrics, text="Shannon entropy  — bits", font=self._mono_font(self._theme.FONT_MONO_SMALL),
            text_color=self._theme.TEXT_MUTED, anchor="w",
        )
        self._entropy_label.grid(row=0, column=0, sticky="w")
        self._gate_label = ctk.CTkLabel(metrics, text="", font=self._mono_font(self._theme.FONT_MONO_SMALL),
                                        text_color=self._theme.TEXT_FAINT, anchor="e")
        self._gate_label.grid(row=0, column=1, sticky="e")
        self._ranking_label = ctk.CTkLabel(
            body, text="", font=self._mono_font(self._theme.FONT_MONO_SMALL), text_color=self._theme.TEXT_FAINT,
            anchor="w", justify="left", wraplength=368,
        )
        self._ranking_label.grid(row=9, column=0, sticky="ew", padx=(10, 12), pady=(6, 0))

        ctk.CTkFrame(body, height=1, fg_color=self._theme.BORDER).grid(
            row=10, column=0, sticky="ew", padx=(10, 12), pady=10)

        self._section_label(body, "IN-FLIGHT RENAME").grid(
            row=11, column=0, sticky="w", padx=(10, 12), pady=(0, 4))
        self._rename_entry = ctk.CTkEntry(
            body, height=44, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.BG, border_color=self._theme.BORDER,
            text_color=self._theme.TEXT, placeholder_text="filename stem",
            font=self._mono_font(self._theme.FONT_MONO),
        )
        self._rename_entry.grid(row=12, column=0, sticky="ew", padx=(10, 12))
        self._rename_entry.bind("<KeyRelease>", self._on_rename_typed)
        self._rename_hint = ctk.CTkLabel(
            body, text="The extension and safety sanitiser are applied on route.",
            font=self._ui_font(self._theme.FONT_HINT), text_color=self._theme.TEXT_FAINT,
            anchor="w", justify="left", wraplength=368,
        )
        self._rename_hint.grid(row=13, column=0, sticky="ew", padx=(10, 12), pady=(6, 0))

        self._route_button = ctk.CTkButton(
            body, text="Route Document", height=48, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.ACCENT_DEEP, hover_color=self._theme.ACCENT, text_color="#ffffff",
            font=self._ui_font(self._theme.FONT_BUTTON, "bold"), state="disabled", command=self.route_document,
        )
        self._route_button.grid(row=14, column=0, sticky="ew", padx=(10, 12), pady=(16, 6))

        self._inspector_note = ctk.CTkLabel(
            body, text="", font=self._ui_font(self._theme.FONT_HINT), text_color=self._theme.TEXT_FAINT,
            anchor="w", justify="left", wraplength=368,
        )
        self._inspector_note.grid(row=15, column=0, sticky="ew", padx=(10, 12), pady=(0, 14))

    def _pill(self, parent: tk.Misc, text: str) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(parent, fg_color=self._theme.ELEVATED, corner_radius=8,
                             border_width=1, border_color=self._theme.BORDER)
        frame.pack(side="left", padx=(0, 8))
        label = ctk.CTkLabel(frame, text=text, font=self._mono_font(self._theme.FONT_PILL, "bold"),
                             text_color=self._theme.TEXT_MUTED)
        label.pack(padx=12, pady=6)
        return label

    # -- activity ledger --------------------------------------------------- #
    def _build_ledger(self, parent: tk.Misc) -> None:
        card = self._card(parent, height=LEDGER_HEIGHT)
        card.grid(row=4, column=0, sticky="ew")
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        self._ledger_card = card

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="ACTIVITY LEDGER", font=self._ui_font(self._theme.FONT_HEADER_SMALL, "bold"),
                     text_color=self._theme.TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        self._ledger_count = ctk.CTkLabel(header, text="0 transfers", font=self._mono_font(self._theme.FONT_MONO_SMALL),
                                          text_color=self._theme.TEXT_FAINT, anchor="w")
        self._ledger_count.grid(row=0, column=1, sticky="w", padx=(12, 0))
        ctk.CTkButton(
            header, text="Clear", width=110, height=40, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.ELEVATED, hover_color=self._theme.HOVER, border_width=1,
            border_color=self._theme.BORDER, text_color=self._theme.TEXT_MUTED,
            font=self._ui_font(self._theme.FONT_BUTTON), command=self.clear_ledger,
        ).grid(row=0, column=2, sticky="e")

        self._ledger_frame = ctk.CTkScrollableFrame(
            card, fg_color=self._theme.BG, corner_radius=self._theme.RADIUS_SMALL,
            border_width=1, border_color=self._theme.BORDER,
            scrollbar_button_color=self._theme.BORDER_STRONG,
            scrollbar_button_hover_color=self._theme.HOVER,
        )
        self._ledger_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self._ledger_frame.grid_columnconfigure(0, weight=1)

    # -- view / navigation -------------------------------------------------- #
    def _on_nav_click(self, view: str) -> None:
        if view == "ledger":
            self._set_view(("all", None))
            self._flash_ledger()
            self._set_status("Activity ledger · every transfer is reversible", tone="idle")
            return
        self._set_view((view, None))

    def _on_card_click(self, key: str) -> None:
        if self._view == ("card", key):
            self._set_view(("all", None))
        else:
            self._set_view(("card", key))

    def _set_view(self, view: tuple[str, str | None], *, record: bool = True) -> None:
        self._view = view
        if record:
            self._history = self._history[: self._history_index + 1]
            if not self._history or self._history[-1] != view:
                self._history.append(view)
                self._history_index = len(self._history) - 1
        self._render_table()
        self._refresh_nav_state()
        self._refresh_shelf_state()
        self._update_crumbs()
        self._update_mode_label()
        self._show_bulk_bar(view[0] == SCAN_MODE and bool(self._scan_results))

    def _nav_back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._set_view(self._history[self._history_index], record=False)
        self._update_nav_arrows()

    def _nav_forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._set_view(self._history[self._history_index], record=False)
        self._update_nav_arrows()

    def _update_nav_arrows(self) -> None:
        self._back_button.configure(
            state="normal" if self._history_index > 0 else "disabled",
            text_color=self._theme.TEXT_MUTED if self._history_index > 0 else self._theme.TEXT_FAINT,
        )
        self._forward_button.configure(
            state="normal" if self._history_index < len(self._history) - 1 else "disabled",
            text_color=self._theme.TEXT_MUTED if self._history_index < len(self._history) - 1 else self._theme.TEXT_FAINT,
        )

    def _view_folder(self) -> DocItem | None:
        mode, key = self._view
        if mode == "card" and key:
            return self._top_by_card(key)
        if mode == "downloads":
            return self._top_by_card("downloads")
        return None

    def _top_by_card(self, key: str) -> DocItem | None:
        return next((item for item in self._tree if item.card == key), None)

    def _update_crumbs(self) -> None:
        parts = ["Home", "Semester 3"]
        mode, key = self._view
        if mode == "card" and key:
            node = self._top_by_card(key)
            if node is not None:
                parts.append(node.label)
        elif mode == "downloads":
            parts.append("Downloads")
        elif mode == "subjects":
            parts.append("Subjects")
        elif mode == "review":
            parts.append("Review Queue")
        elif mode == SCAN_MODE:
            parts.append("Scan Results")
        self._crumb_label.configure(text=" > ".join(parts))

    def _update_mode_label(self) -> None:
        mode, _key = self._view
        labels = {
            "all": "Showing: all documents",
            "downloads": "Showing: intake",
            "subjects": "Showing: subjects",
            "review": "Showing: review queue",
            SCAN_MODE: "Showing: disk scan results",
        }
        self._mode_label.configure(text=labels.get(mode, ""))

    def _refresh_nav_state(self) -> None:
        mode = self._view[0]
        for view, row in self._nav_rows.items():
            active = view == mode and mode != "card"
            row.configure(fg_color=self._theme.ELEVATED if active else "transparent")
            bar = getattr(row, "_accent_bar", None)
            if bar is not None:
                bar.configure(fg_color=self._theme.ACCENT if active else "transparent")
            for child in row.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    try:
                        if child.cget("text") in ("All Documents", "Downloads", "Subjects", "Review Queue", "Activity Ledger"):
                            child.configure(text_color=self._theme.TEXT if active else self._theme.TEXT_MUTED)
                    except tk.TclError:  # pragma: no cover
                        pass

    def _refresh_shelf_state(self) -> None:
        for key, frame in self._shelf_cards.items():
            active = self._view == ("card", key)
            frame.configure(
                border_color=self._theme.ACCENT if active else self._theme.BORDER,
                border_width=2 if active else 1,
                fg_color=self._theme.ELEVATED if active else self._theme.BG,
            )

    def _flash_ledger(self) -> None:
        try:
            self._ledger_card.configure(border_color=self._theme.ACCENT)
            self.after(900, lambda: self._ledger_card.configure(border_color=self._theme.BORDER))
        except tk.TclError:  # pragma: no cover
            pass

    # -- table rendering ---------------------------------------------------- #
    def _visible_rows(self) -> list[tuple[DocItem, int]]:
        query = self._search.get().strip().casefold()
        rows: list[tuple[DocItem, int]] = []

        mode, key = self._view
        if mode == SCAN_MODE:
            for item in self._scan_results:
                if query and query not in item.label.casefold() and query not in (item.subject or "").casefold():
                    continue
                rows.append((item, 0))
            return rows

        if query:
            for item in _iter_files(self._tree):
                if query in item.label.casefold() or query in (item.subject or "").casefold():
                    rows.append((item, 0))
            return rows

        if mode == "card" and key:
            node = self._top_by_card(key)
            if node is not None:
                rows.append((node, 0))
                rows.extend((child, 1) for child in node.children)
            return rows
        if mode == "downloads":
            node = self._top_by_card("downloads")
            if node is not None:
                rows.append((node, 0))
                rows.extend((child, 1) for child in node.children)
            return rows
        if mode == "review":
            for item in _iter_files(self._tree):
                if item.status == STATUS_AMBIGUOUS:
                    rows.append((item, 0))
            return rows
        if mode == "subjects":
            for node in self._tree:
                if node.card in SUBJECT_TO_CARD.values():
                    rows.append((node, 0))
                    if node.key in self._expanded:
                        rows.extend((child, 1) for child in node.children)
            return rows

        # "all"
        for node in self._tree:
            rows.append((node, 0))
            if node.key in self._expanded:
                rows.extend((child, 1) for child in node.children)
        return rows

    def _render_table(self) -> None:
        for row in self._table_rows:
            row.destroy()
        self._table_rows = []

        rows = self._visible_rows()
        if not rows:
            message = "Nothing to show here. Drop supported documents in the intake folder and press 'Scan Watch Dir'."
            if self._view[0] == SCAN_MODE:
                message = (
                    "No documents discovered yet. Press 'Scan Disk' to walk a folder or the whole home "
                    "folder for unorganised study documents."
                )
            hint = self._section_label(
                self._table_body,
                message,
                font=self._ui_font(self._theme.FONT_BASE),
                wraplength=560, justify="left",
            )
            hint.grid(row=0, column=0, columnspan=len(COLUMNS), sticky="w", padx=16, pady=28)
            self._table_rows.append(hint)
            return

        for index, (item, depth) in enumerate(rows):
            row = self._table_row(item, depth, index)
            self._table_rows.append(row)

    def _table_row(self, item: DocItem, depth: int, index: int) -> ctk.CTkFrame:
        selected = self._selected is not None and self._selected.key == item.key
        bg = self._theme.SURFACE if depth == 0 else self._theme.ELEVATED
        row = ctk.CTkFrame(
            self._table_body, fg_color=bg, corner_radius=8,
            border_width=1 if selected else 0,
            border_color=self._theme.ACCENT if selected else self._theme.BORDER,
        )
        row.grid(row=index, column=0, sticky="ew", padx=4, pady=2)
        for column, (_name, minsize, weight) in enumerate(COLUMNS):
            row.grid_columnconfigure(column, minsize=minsize, weight=weight)

        indent = 8 + depth * 22
        expandable = item.is_folder and bool(item.children)
        expanded = item.key in self._expanded or self._view[0] == "card"
        if item.scan:
            check = ctk.CTkCheckBox(
                row, text="", width=26, height=26,
                checkbox_width=24, checkbox_height=24, corner_radius=6,
                fg_color=self._theme.ACCENT, hover_color=self._theme.ACCENT_DEEP,
                border_color=self._theme.BORDER_STRONG, checkmark_color="#ffffff",
                command=lambda it=item: self._toggle_scan_item(it),
            )
            if item.selected:
                check.select()
            check.grid(row=0, column=0, padx=(indent, 0), pady=9)
            arrow: tk.Misc = check
        else:
            arrow_text = ""
            if item.is_folder:
                arrow_text = "v" if (expanded and item.children) else (">" if item.children else "")
            arrow = ctk.CTkLabel(row, text=arrow_text, width=26,
                                 font=self._ui_font(self._theme.FONT_TABLE, "bold"),
                                 text_color=self._theme.TEXT_MUTED, cursor="hand2")
            arrow.grid(row=0, column=0, padx=(indent, 0), pady=9)

        icon_name = self._item_icon(item)
        icon = self._icon(icon_name, 26)
        if icon is not None:
            ctk.CTkLabel(row, image=icon, text="").grid(row=0, column=1, padx=(2, 6))
        else:
            ctk.CTkLabel(row, text="•", font=self._ui_font(self._theme.FONT_TABLE),
                         text_color=self._theme.TEXT_MUTED).grid(row=0, column=1, padx=(2, 6))

        name = ctk.CTkLabel(row, text=item.label,
                            font=self._ui_font(self._theme.FONT_TABLE, "bold" if depth == 0 else "normal"),
                            text_color=self._theme.TEXT, anchor="w", justify="left")
        name.grid(row=0, column=2, sticky="ew", padx=(0, 8))

        size = ctk.CTkLabel(row, text=human_size(item.size), font=self._mono_font(self._theme.FONT_MONO_SMALL),
                            text_color=self._theme.TEXT_MUTED, anchor="w")
        size.grid(row=0, column=3, sticky="w", padx=(0, 10))

        pill = PillBar(row, theme=self._theme, width=176, height=26,
                       bg=bg, font=self._tk_font(self._theme.FONT_PILL, "bold"))
        pill.grid(row=0, column=4, sticky="w", padx=(0, 10))
        confidence = item.confidence if item.confidence is not None else 0.0
        if item.scan:
            colour = self._status_color(item.status)
            pill.set(confidence, f"{confidence * 100:.1f}%", colour)
        elif item.is_folder:
            total = getattr(self, "_tree_size", 0) or 1
            share = (item.size / total) if total else 0.0
            colour = self._subject_color(item.subject) if item.subject else self._theme.ACCENT
            count = len(item.children)
            pill.set(share, f"{count} item{'s' if count != 1 else ''}", colour)
        else:
            colour = self._subject_color(item.subject)
            pill.set(confidence, f"{confidence * 100:.1f}%", colour)

        status_text = "CONFIDENT" if item.status == STATUS_CONFIDENT else ("REVIEW" if item.status == STATUS_AMBIGUOUS else "—")
        status_colour = self._status_color(item.status)
        status = ctk.CTkLabel(
            row, text=status_text, font=self._mono_font(self._theme.FONT_MONO_SMALL, "bold"), text_color=status_colour,
            fg_color=mix(self._theme.BG, status_colour, 0.16), corner_radius=8,
            width=118, height=28,
        )
        status.grid(row=0, column=5, sticky="w", padx=(0, 4))

        def select(_event: tk.Event | None = None, target: DocItem = item) -> None:
            self._select_item(target)

        def toggle(_event: tk.Event | None = None, target: DocItem = item) -> None:
            self._toggle_expand(target)

        if item.is_folder and item.children:
            arrow.bind("<Button-1>", toggle)
        for widget in (row, name, size):
            widget.bind("<Button-1>", select)
        for widget in (row.winfo_children()):
            if isinstance(widget, ctk.CTkLabel) and widget is not arrow:
                widget.bind("<Button-1>", select)

        def hover(entering: bool, frame: ctk.CTkFrame = row, base: str = bg) -> None:
            if self._selected is not None and self._selected.key == item.key:
                return
            frame.configure(fg_color=self._theme.HOVER if entering else base)

        row.bind("<Enter>", lambda _e: hover(True))
        row.bind("<Leave>", lambda _e: hover(False))
        return row

    def _item_icon(self, item: DocItem) -> str:
        if item.is_file:
            return file_icon_name(item.file_type)
        if item.card:
            for card_key, _label, icon_name in SHELF_CARDS:
                if card_key == item.card:
                    return icon_name
        if item.subject and item.subject in SUBJECT_ICONS:
            return SUBJECT_ICONS[item.subject]
        return "folder-default.png"

    def _subject_color(self, subject: str) -> str:
        if not subject:
            return self._theme.TEXT_FAINT
        index = sum(ord(ch) for ch in subject) % len(self._theme.PILL_COLORS)
        return self._theme.PILL_COLORS[index]

    def _status_color(self, status: str) -> str:
        if status == STATUS_CONFIDENT:
            return self._theme.SUCCESS
        if status == STATUS_AMBIGUOUS:
            return self._theme.WARN
        return self._theme.TEXT_FAINT

    def _toggle_expand(self, item: DocItem) -> None:
        if not item.is_folder or not item.children:
            return
        if item.key in self._expanded:
            self._expanded.discard(item.key)
        else:
            self._expanded.add(item.key)
        if self._view[0] == "card":
            # Card views always show children; toggling there collapses the whole list.
            self._set_view(("all", None))
            return
        self._render_table()

    # -- data loading ------------------------------------------------------- #
    def load_document_tree(self) -> None:
        config = self._config_store.load()
        service = self._service
        entries = self._ledger.all()
        self._submit(
            lambda: build_document_tree(service, config, entries),
            on_done=self._apply_tree,
            on_error=lambda exc: self._set_status(f"Scan failed: {exc}", tone="error"),
            busy_text="Scanning folders…",
        )

    def open_scan_dialog(self) -> None:
        """Open the Mode A (folder) vs Mode B (deep disk/OS) chooser dialog."""
        config = self._config_store.load()
        ScanSetupDialog(
            self,
            theme=self._theme,
            on_start=self._on_start_scan,
            on_skip=None,
            home=Path.home(),
            default_folder=config.watch_folder,
        )

    def _on_start_scan(self, mode: str, roots: list[str], recursive: bool) -> None:
        self.start_disk_scan(roots=roots, recursive=recursive, mode=mode)

    def start_deep_scan(self) -> None:
        self.start_disk_scan(roots=[str(Path.home())], recursive=True, mode="deep")

    def start_disk_scan(
        self,
        roots: Sequence[str],
        recursive: bool = True,
        mode: str = "folder",
    ) -> None:
        if self._scan_running:
            self._set_status("Scan is already running", tone="warn")
            return
        self._scan_running = True
        self._scan_cancel = threading.Event()
        dialog = ScanProgressDialog(
            self,
            theme=self._theme,
            on_cancel=self._scan_cancel.set,
            roots=roots,
        )
        self._scan_dialog = dialog
        self._set_busy(True, "Scanning disk…")

        def worker() -> list[ScannedDocument]:
            scanner = DiskScanner(workers=default_workers(), progress_interval=0.08)

            def on_progress(snapshot: ScanProgress) -> None:
                self._events.put((dialog.update_progress, (snapshot,)))

            return scanner.scan(
                roots,
                recursive=recursive,
                on_progress=on_progress,
                cancel=self._scan_cancel,
            )

        def on_done(docs: list[ScannedDocument]) -> None:
            self._scan_running = False
            self._set_busy(False, "")
            try:
                dialog.destroy()
            except Exception:
                pass
            self._apply_scan_results(docs, roots)

        def on_error(exc: BaseException) -> None:
            self._scan_running = False
            self._set_busy(False, "")
            try:
                dialog.destroy()
            except Exception:
                pass
            self._show_error("Disk scan failed", exc)

        self._submit(worker, on_done=on_done, on_error=on_error, manage_busy=False)

    def _apply_scan_results(self, documents: list[ScannedDocument], roots: Sequence[str]) -> None:
        scan_items: list[DocItem] = []
        confident_count = 0
        for doc in documents:
            item = DocItem(
                key=f"file:{doc.path}",
                label=doc.name,
                kind="file",
                path=doc.path,
                size=doc.size,
                file_type=doc.file_type,
                subject=doc.subject,
                confidence=doc.confidence,
                status=doc.status,
                modified=doc.modified,
                pending=True,
                scan=True,
            )
            if item.status == STATUS_CONFIDENT:
                confident_count += 1
            scan_items.append(item)

        self._scan_results = scan_items
        self._bulk_selected.clear()
        intake_node = next((node for node in self._tree if node.card == "downloads"), None)
        if intake_node is not None:
            existing_paths = {child.path for child in intake_node.children if child.path}
            new_children = [item for item in scan_items if item.path not in existing_paths]
            intake_node.children.extend(new_children)
            intake_node.size = sum(child.size for child in intake_node.children)

        self._index_all_tree()
        self._refresh_badges()
        self._set_view(("downloads", None))
        self._show_bulk_bar(bool(scan_items))
        self._refresh_bulk_summary()
        self._set_status(
            f"Scan finished: {len(scan_items)} documents discovered ({confident_count} confident)",
            tone="ok",
        )
        self._calibrate_pending_async()

    def _index_all_tree(self) -> None:
        self._items_by_key = {}
        self._items_by_path = {}
        for item in self._tree:
            self._index_item(item)

    def _toggle_scan_item(self, item: DocItem) -> None:
        """Tick / untick one scan result from its row checkbox."""
        item.selected = not item.selected
        if item.selected:
            self._bulk_selected.add(item.key)
        else:
            self._bulk_selected.discard(item.key)
        self._refresh_bulk_summary()

    def _refresh_bulk_summary(self) -> None:
        if not hasattr(self, "_bulk_summary"):
            return
        total = len(self._scan_results)
        confident = sum(1 for item in self._scan_results if item.status == STATUS_CONFIDENT)
        selected = sum(1 for item in self._scan_results if item.selected)
        text = f"{total} document(s) discovered · {confident} confident"
        if selected:
            text += f" · {selected} selected"
        try:
            self._bulk_summary.configure(text=text)
        except tk.TclError:  # pragma: no cover
            pass

    def _toggle_all_confident(self) -> None:
        select = bool(self._bulk_confident.get())
        for item in self._scan_results:
            if item.status == STATUS_CONFIDENT:
                item.selected = select
                if select:
                    self._bulk_selected.add(item.key)
                else:
                    self._bulk_selected.discard(item.key)
        self._refresh_bulk_summary()
        self._render_table()

    def clear_scan_results(self) -> None:
        self._scan_results = []
        self._bulk_selected.clear()
        self._show_bulk_bar(False)
        self.load_document_tree()

    def batch_route_selected(self) -> None:
        selected_items = [
            item for item in self._scan_results
            if item.selected or (not self._bulk_selected and item.status == STATUS_CONFIDENT)
        ]
        if not selected_items:
            self._set_status("No documents selected to route", tone="warn")
            return

        config = self._config_store.load()
        service = self._service
        total = len(selected_items)
        self._set_busy(True, f"Routing {total} documents…")

        def worker() -> list[dict[str, Any]]:
            routed = []
            for index, item in enumerate(selected_items):
                if not item.path:
                    continue
                try:
                    res = service.route(
                        path=item.path,
                        config=config,
                        subject=item.subject or None,
                        move=True,
                    )
                    routed.append(res)
                except Exception:
                    continue
                progress = (index + 1) / total
                self._events.put((self._batch_progress.set, (progress,)))
            return routed

        def on_done(results: list[dict[str, Any]]) -> None:
            self._set_busy(False, "")
            routed_paths = {
                str(res.get("source", {}).get("path", "")) for res in results
            }
            if routed_paths:
                self._scan_results = [
                    item for item in self._scan_results if item.path not in routed_paths
                ]
            self._bulk_selected.clear()
            self._refresh_bulk_summary()
            self._show_bulk_bar(bool(self._scan_results))
            self._set_status(f"Batch routed {len(results)}/{total} documents", tone="ok")
            self._refresh_ledger()
            self.load_document_tree()

        self._submit(worker, on_done=on_done, manage_busy=False)

    # Kept for parity with the previous revision / external callers.
    def load_storage_map(self) -> None:
        self.load_document_tree()

    def scan_watch_dir(self) -> None:
        self.load_document_tree()

    def _apply_tree(self, payload: tuple[list[DocItem], dict[str, Any]]) -> None:
        tree, stats = payload
        self._tree = tree
        self._stats = stats
        self._tree_size = sum(item.size for item in tree) or 1
        self._items_by_key = {}
        self._items_by_path = {}
        for item in tree:
            self._index_item(item)
        if self._selected is not None:
            replacement = self._items_by_key.get(self._selected.key)
            if replacement is not None:
                self._selected = replacement
                self._show_item(replacement)
            else:
                self._clear_inspector()
        self._refresh_badges()
        self._render_table()
        self._refresh_shelf_state()
        self._update_nav_arrows()
        pending = stats.get("pending_count", 0)
        self._set_status(f"Map refreshed · {pending} document(s) waiting", tone="ok")
        self._calibrate_pending_async()

    def _index_item(self, item: DocItem) -> None:
        self._items_by_key[item.key] = item
        if item.path:
            self._items_by_path[item.path] = item
        for child in item.children:
            self._index_item(child)

    def _refresh_badges(self) -> None:
        stats = self._stats or {}
        counts = {
            "all": stats.get("total_count", 0),
            "downloads": stats.get("pending_count", 0),
            "subjects": len(subject_labels()),
            "review": stats.get("review_count", 0),
            "ledger": len(self._ledger.all()),
        }
        for view, label in self._nav_badges.items():
            label.configure(text=str(counts.get(view, 0)))
        self._storage_size.configure(text=human_size(stats.get("archived_size", 0)))
        hint = stats.get("folder_counts", {})
        for key, label in self._shelf_counts.items():
            count = hint.get(key, 0)
            if count:
                size = stats.get("folder_sizes", {}).get(key, 0)
                label.configure(text=f"{count} · {human_size(size)}")
            else:
                label.configure(text="empty")
        self._shelf_hint.configure(
            text=f"{stats.get('total_count', 0)} documents · {human_size(stats.get('archived_size', 0))}"
        )

    # -- background calibration -------------------------------------------- #
    def _calibrate_pending_async(self) -> None:
        pending = [item for item in _iter_files(self._tree) if item.pending and item.path]
        if not pending or self._classify_running:
            return
        config = self._config_store.load()
        service = self._service
        paths = [item.path for item in pending if item.path]

        def work() -> dict[str, tuple[str, float, float, str]]:
            classifier = service.classifier(config)
            results: dict[str, tuple[str, float, float, str]] = {}
            for path in paths:
                try:
                    document = extract_document(path)
                    decision = classifier.classify_document(document)
                except Exception:  # noqa: BLE001 - stay on the heuristic values
                    continue
                results[path] = (
                    decision.subject, float(decision.confidence),
                    float(decision.entropy), str(decision.status),
                )
            return results

        def done(results: dict[str, tuple[str, float, float, str]]) -> None:
            self._classify_running = False
            if not results:
                return
            for path, (subject, confidence, _entropy, status) in results.items():
                item = self._items_by_path.get(path)
                if item is not None:
                    item.subject = subject
                    item.confidence = confidence
                    item.status = status
            self._render_table()
            self._refresh_badges()
            if self._selected is not None and self._selected.is_file:
                self._show_item(self._selected)

        def failed(_exc: BaseException) -> None:
            self._classify_running = False

        self._classify_running = True
        self._submit(work, on_done=done, on_error=failed, manage_busy=False)

    # -- selection & inspector --------------------------------------------- #
    def _select_item(self, item: DocItem) -> None:
        self._selected = item
        self._render_table()
        self._show_item(item)

    def _clear_inspector(self) -> None:
        self._doc_info = None
        self._doc_name.configure(text="No document selected", text_color=self._theme.TEXT)
        self._doc_path.configure(text="Pick a folder or a document in the table to inspect it.")
        self._pill_format.configure(text="—")
        self._pill_size.configure(text="—")
        self._pill_pages.configure(text="—")
        self._badge_dot.configure(text_color=self._theme.TEXT_FAINT)
        self._badge_label.configure(text="awaiting a selection", text_color=self._theme.TEXT_MUTED)
        self._badge_state.configure(text="")
        self._confidence_bar.configure(progress_color=self._theme.ACCENT)
        self._confidence_bar.set(0.0)
        self._confidence_label.configure(text="—")
        self._entropy_label.configure(text="Shannon entropy  — bits")
        self._gate_label.configure(text="")
        self._ranking_label.configure(text="")
        self._rename_entry.delete(0, "end")
        self._rename_dirty = False
        self._subject_menu.set(AUTO_SUBJECT)
        self._inspector_note.configure(text="")
        self._refresh_route_button()

    def _show_item(self, item: DocItem) -> None:
        if item.is_file:
            self._show_file(item)
        else:
            self._show_folder(item)

    def _show_folder(self, item: DocItem) -> None:
        self._doc_info = None
        self._doc_name.configure(text=item.label, text_color=self._theme.TEXT)
        self._doc_path.configure(text=item.path or "")
        children = len(item.children)
        self._pill_format.configure(text="FOLDER")
        self._pill_size.configure(text=human_size(item.size))
        self._pill_pages.configure(text=f"{children} file{'s' if children != 1 else ''}")
        if item.subject:
            entry = get_subject_taxonomy().get(item.subject, {})
            self._badge_dot.configure(text_color=self._subject_color(item.subject))
            self._badge_label.configure(
                text=f"{entry.get('code', '')} - {entry.get('name', item.subject)}",
                text_color=self._theme.TEXT,
            )
            self._badge_state.configure(text="SUBJECT", text_color=self._theme.TEXT_FAINT)
            self._subject_menu.set(item.subject)
        else:
            self._badge_dot.configure(text_color=self._theme.TEXT_FAINT)
            self._badge_label.configure(text=item.label, text_color=self._theme.TEXT_MUTED)
            self._badge_state.configure(text="FOLDER", text_color=self._theme.TEXT_FAINT)
            self._subject_menu.set(AUTO_SUBJECT)
        self._confidence_bar.set(0.0)
        self._confidence_bar.configure(progress_color=self._theme.ACCENT)
        self._confidence_label.configure(text="—")
        self._entropy_label.configure(text="Shannon entropy  — bits")
        self._gate_label.configure(text="")
        preview = " · ".join(child.label for child in item.children[:4])
        self._ranking_label.configure(text=preview or "This folder is empty.")
        self._rename_entry.delete(0, "end")
        self._rename_dirty = False
        self._rename_hint.configure(text="Select a document inside to route and rename it.")
        self._inspector_note.configure(text=item.path or "")
        self._refresh_route_button()

    def _show_file(self, item: DocItem) -> None:
        info = inspect_document(item.path) if item.path else None
        self._doc_info = info
        title = (info or {}).get("title") or item.label
        self._doc_name.configure(text=title, text_color=self._theme.TEXT)
        self._doc_path.configure(text=item.path or item.label)
        self._pill_format.configure(text=(item.file_type or "?").upper())
        self._pill_size.configure(text=human_size(item.size))
        if info is not None:
            pages = info.get("pages")
            self._pill_pages.configure(
                text=f"{pages} {info.get('page_label', 'pages')}" if pages else "pages —"
            )
        else:
            self._pill_pages.configure(text="pages —")

        confidence = item.confidence if item.confidence is not None else 0.0
        state = "pending" if item.pending else "archived"
        if item.subject:
            entry = get_subject_taxonomy().get(item.subject, {})
            colour = self._subject_color(item.subject)
            self._badge_dot.configure(text_color=colour)
            self._badge_label.configure(
                text=f"{entry.get('code', '')} - {entry.get('name', item.subject)}",
                text_color=self._theme.TEXT,
            )
        else:
            colour = self._theme.WARN
            self._badge_dot.configure(text_color=self._theme.WARN)
            self._badge_label.configure(text="awaiting calibration", text_color=self._theme.TEXT_MUTED)
        self._badge_state.configure(
            text=(STATUS_CONFIDENT if item.status == STATUS_CONFIDENT else "REVIEW").upper()
            if item.status else state.upper(),
            text_color=self._status_color(item.status),
        )
        self._subject_menu.set(item.subject if item.subject in self._subject_values else AUTO_SUBJECT)
        self._confidence_bar.configure(progress_color=self._status_color(item.status))
        self._confidence_bar.set(max(0.0, min(1.0, confidence)))
        self._confidence_label.configure(text=f"{confidence * 100:5.1f}%")
        config = self._config_store.load()
        self._gate_label.configure(
            text=f"gate {config.confidence_threshold:.2f} / {config.entropy_threshold:.2f} bits"
        )
        self._entropy_label.configure(text="Shannon entropy  — bits")

        if not self._rename_dirty:
            suggestion = suggest_filename(title, item.subject or None, item.file_type or "pdf")
            self._rename_entry.delete(0, "end")
            self._rename_entry.insert(0, Path(suggestion).stem)
        self._rename_hint.configure(text="Suggested from the extracted title; edit freely before routing.")
        note = "Choose a destination and press Route Document."
        if info is not None and info.get("error"):
            note = f"Extraction warning: {info['error']}"
        if not item.pending:
            note = "This document already lives in the archive. Undo it from the ledger if needed."
        self._inspector_note.configure(text=note)
        self._refresh_route_button()

    def _refresh_route_button(self) -> None:
        item = self._selected
        eligible = bool(
            item is not None and item.is_file and item.path and item.pending and not self._busy
        )
        self._route_button.configure(
            state="normal" if eligible else "disabled",
            fg_color=self._theme.ACCENT_DEEP if eligible else self._theme.ELEVATED,
            text_color="#ffffff" if eligible else self._theme.TEXT_FAINT,
        )

    def _on_rename_typed(self, _event: tk.Event) -> None:
        self._rename_dirty = True

    def _on_subject_override(self, choice: str) -> None:
        if self._selected is None or not self._selected.is_file:
            return
        subject = None if choice == AUTO_SUBJECT else choice
        if not self._rename_dirty:
            title = (self._doc_info or {}).get("title") or self._selected.label
            suggestion = suggest_filename(title, subject, self._selected.file_type or "pdf")
            self._rename_entry.delete(0, "end")
            self._rename_entry.insert(0, Path(suggestion).stem)
        if subject is None:
            self._inspector_note.configure(text="Reverted to the calibrated prediction.")
            return
        entry = get_subject_taxonomy().get(subject, {})
        folder = self._service.destination_folder(subject, self._config_store.load())
        self._inspector_note.configure(
            text=f"Manual override: {entry.get('code', '')} - {entry.get('name', subject)}\n-> {folder}"
        )

    # -- routing ----------------------------------------------------------- #
    def route_document(self) -> None:
        item = self._selected
        if item is None or not item.is_file or not item.path:
            self._set_status("Select a document in the intake folder first", tone="warn")
            return
        if not item.pending:
            self._set_status("That document is already filed", tone="warn")
            return

        config = self._config_store.load()
        rename = self._rename_entry.get().strip() or None
        choice = self._subject_menu.get()
        subject = None if choice == AUTO_SUBJECT else choice
        service = self._service
        path = item.path

        def work() -> dict[str, Any]:
            return service.route(path=path, config=config, rename=rename, subject=subject, move=True)

        def done(result: dict[str, Any]) -> None:
            destination = result.get("destination", {})
            self._set_status(
                f"Routed to {destination.get('name', '?')} · {human_size(result.get('source', {}).get('size'))}",
                tone="ok",
            )
            source_path = str(result.get("source", {}).get("path", ""))
            if source_path and self._scan_results:
                self._scan_results = [
                    item for item in self._scan_results if item.path != source_path
                ]
                self._bulk_selected.discard(f"file:{source_path}")
                self._refresh_bulk_summary()
                self._show_bulk_bar(bool(self._scan_results))
            self._selected = None
            self._clear_inspector()
            self._refresh_ledger()
            self.load_document_tree()

        def failed(exc: BaseException) -> None:
            if isinstance(exc, SortwiseError):
                self._set_status(exc.message, tone="error")
                self._inspector_note.configure(text=exc.message)
            else:
                self._show_error("Routing failed", exc)

        self._submit(work, on_done=done, on_error=failed, busy_text="Routing…")

    def auto_route_confident(self) -> None:
        config = self._config_store.load()
        service = self._service

        def work() -> dict[str, Any]:
            scan = service.scan(config)
            routed: list[str] = []
            skipped = 0
            errors = 0
            for record in scan.get("files", []):
                path = str(record.get("path", ""))
                try:
                    preview = service.route(path=path, config=config, move=False)
                except SortwiseError:
                    errors += 1
                    continue
                if (
                    preview.get("status") == STATUS_CONFIDENT
                    and float(preview.get("confidence", 0.0)) >= config.confidence_threshold
                ):
                    try:
                        service.route(path=path, config=config, move=True)
                        routed.append(str(preview.get("destination", {}).get("name", "")))
                    except SortwiseError:
                        errors += 1
                else:
                    skipped += 1
            return {"routed": routed, "skipped": skipped, "errors": errors}

        def done(result: dict[str, Any]) -> None:
            count = len(result["routed"])
            self._set_status(
                f"Auto-routed {count} confident document(s) · {result['skipped']} held for review · "
                f"{result['errors']} error(s)",
                tone="ok" if count else "warn",
            )
            self._refresh_ledger()
            self.load_document_tree()

        self._submit(
            work, on_done=done,
            on_error=lambda exc: self._show_error("Auto-route failed", exc),
            busy_text="Auto-routing confident documents…",
        )

    def undo_last(self) -> None:
        target = next(
            (entry for entry in self._ledger.all()
             if entry.get("action") == "move" and not entry.get("undone")),
            None,
        )
        if target is None:
            self._set_status("Nothing to undo", tone="warn")
            return
        self.undo_entry(str(target.get("id")))

    def undo_entry(self, entry_id: str) -> None:
        service = self._service

        def done(result: dict[str, Any]) -> None:
            self._set_status(result.get("message", "Undone"), tone="ok")
            self._refresh_ledger()
            self.load_document_tree()

        self._submit(
            lambda: service.undo(entry_id), on_done=done,
            on_error=lambda exc: self._show_error("Undo failed", exc),
            busy_text="Restoring file…",
        )

    def clear_ledger(self) -> None:
        try:
            confirmed = messagebox.askyesno(
                APP_NAME,
                "Clear the transfer ledger?\n\nMoved files stay where they are; only the undo "
                "history is removed.",
                parent=self,
            )
        except tk.TclError:  # pragma: no cover
            confirmed = False
        if not confirmed:
            return
        cleared = self._ledger.clear()
        self._refresh_ledger()
        self._set_status(f"Cleared {cleared} ledger entr{'y' if cleared == 1 else 'ies'}", tone="ok")

    # -- settings ---------------------------------------------------------- #
    def open_settings(self) -> None:
        SettingsDialog(self, self._config_store.load(), self._apply_settings, theme=self._theme)

    def _apply_settings(self, changes: dict[str, Any]) -> None:
        config = self._config_store.update(changes)
        self._set_status(f"Settings saved · watch {config.watch_folder}", tone="ok")
        self.load_document_tree()

    # -- ledger ------------------------------------------------------------ #
    def _refresh_ledger(self) -> None:
        for row in self._ledger_rows:
            row.destroy()
        self._ledger_rows = []
        entries = self._ledger.all(60)
        self._ledger_count.configure(text=f"{len(entries)} transfer{'s' if len(entries) != 1 else ''}")
        if not entries:
            empty = self._section_label(
                self._ledger_frame,
                "No transfers yet. Routed documents appear here with a one-click undo.",
            )
            empty.grid(row=0, column=0, sticky="w", padx=14, pady=16)
            self._ledger_rows.append(empty)
            return
        for index, entry in enumerate(entries):
            row = self._ledger_row(entry)
            row.grid(row=index, column=0, sticky="ew", padx=6, pady=3)
            self._ledger_rows.append(row)

    def _ledger_row(self, entry: dict[str, Any]) -> ctk.CTkFrame:
        row = ctk.CTkFrame(
            self._ledger_frame, fg_color=self._theme.ELEVATED,
            corner_radius=self._theme.RADIUS_SMALL, border_width=1, border_color=self._theme.BORDER,
        )
        row.grid_columnconfigure(1, weight=2)
        row.grid_columnconfigure(2, weight=2)

        undone = bool(entry.get("undone"))
        action = str(entry.get("action", "move"))
        stamp = self._format_timestamp(str(entry.get("timestamp", "")))
        ctk.CTkLabel(row, text=stamp, font=self._mono_font(self._theme.FONT_MONO_SMALL), text_color=self._theme.TEXT_FAINT,
                     anchor="w", width=104).grid(row=0, column=0, padx=(14, 10), pady=10, sticky="w")

        names = ctk.CTkFrame(row, fg_color="transparent")
        names.grid(row=0, column=1, sticky="ew", pady=10)
        source = Path(str(entry.get("source", ""))).name or "—"
        target = str(entry.get("renamed_to") or Path(str(entry.get("destination") or "")).name or "—")
        ctk.CTkLabel(names, text=source, font=self._ui_font(self._theme.FONT_BASE),
                     text_color=self._theme.TEXT_MUTED if undone else self._theme.TEXT,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(names, text=f"-> {target}", font=self._mono_font(self._theme.FONT_MONO_SMALL),
                     text_color=self._theme.TEXT_FAINT, anchor="w").pack(anchor="w")

        destination = Path(str(entry.get("destination") or "")).parent
        meta = ctk.CTkFrame(row, fg_color="transparent")
        meta.grid(row=0, column=2, sticky="ew", pady=10)
        ctk.CTkLabel(meta, text=(str(entry.get("subject", "")).split(" - ")[0] or action.upper()),
                     font=self._mono_font(self._theme.FONT_MONO_SMALL, "bold"), text_color=self._theme.TEXT_MUTED,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(meta, text=str(destination) if str(destination) != "." else "—",
                     font=self._mono_font(self._theme.FONT_MONO_SMALL), text_color=self._theme.TEXT_FAINT,
                     anchor="w").pack(anchor="w")

        status_text = str(entry.get("status") or action.upper())
        status_colour = self._status_color(status_text)
        ctk.CTkLabel(
            row, text="UNDONE" if undone else status_text, font=self._mono_font(self._theme.FONT_MONO_SMALL, "bold"),
            text_color=self._theme.TEXT_FAINT if undone else status_colour,
        ).grid(row=0, column=3, padx=10, sticky="e")

        ctk.CTkButton(
            row, text="Undo", width=98, height=38, corner_radius=self._theme.RADIUS_SMALL,
            fg_color=self._theme.BG, hover_color=self._theme.HOVER, border_width=1,
            border_color=self._theme.BORDER, text_color=self._theme.TEXT_MUTED,
            font=self._ui_font(self._theme.FONT_BUTTON), state="disabled" if (undone or action != "move") else "normal",
            command=lambda entry_id=str(entry.get("id")): self.undo_entry(entry_id),
        ).grid(row=0, column=4, padx=(0, 12), pady=8, sticky="e")
        return row

    @staticmethod
    def _format_timestamp(raw: str) -> str:
        if not raw:
            return "—"
        try:
            stamp = datetime.fromisoformat(raw)
        except ValueError:
            return raw[:19]
        if stamp.date() == datetime.now(stamp.tzinfo).date():
            return stamp.strftime("%H:%M:%S")
        return stamp.strftime("%d %b %H:%M")

    # -- background work --------------------------------------------------- #
    def _submit(
        self,
        work: Callable[[], Any],
        *,
        on_done: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None = None,
        busy_text: str = "Working…",
        manage_busy: bool = True,
    ) -> bool:
        """Run ``work`` on a worker thread and marshal the result back to Tk."""
        if manage_busy:
            if self._busy:
                self._set_status("Busy - wait for the current task", tone="warn")
                return False
            self._set_busy(True, busy_text)

        def runner() -> None:
            try:
                result = work()
            except BaseException as exc:  # noqa: BLE001 - reported to the UI
                self._events.put((self._worker_failed, (on_error, exc, manage_busy)))
            else:
                self._events.put((self._worker_done, (on_done, result, manage_busy)))

        threading.Thread(target=runner, name="sortwise-worker", daemon=True).start()
        return True

    def _worker_done(self, callback: Callable[[Any], None], result: Any, manage_busy: bool) -> None:
        if manage_busy:
            self._set_busy(False, "")
        try:
            callback(result)
        except Exception as exc:  # noqa: BLE001
            self._show_error("Could not update the view", exc)

    def _worker_failed(
        self, handler: Callable[[BaseException], None] | None, exc: BaseException, manage_busy: bool
    ) -> None:
        if manage_busy:
            self._set_busy(False, "")
        if handler is not None:
            handler(exc)

    def _drain_events(self) -> None:
        if self._closed:
            return
        for _ in range(64):
            try:
                callback, args = self._events.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception:  # noqa: BLE001 - never let a callback kill the loop
                self._set_status("A background task reported an error", tone="error")
        try:
            self._poll_job = self.after(self.POLL_INTERVAL_MS, self._drain_events)
        except tk.TclError:  # pragma: no cover - window destroyed mid-poll
            self._poll_job = None

    # -- status + errors --------------------------------------------------- #
    def _set_status(self, text: str, tone: str = "idle") -> None:
        colours = {
            "idle": self._theme.TEXT_FAINT,
            "ok": self._theme.SUCCESS,
            "warn": self._theme.WARN,
            "error": self._theme.DANGER,
            "busy": self._theme.ACCENT,
        }
        self._status_label.configure(text=text)
        self._status_dot.configure(text_color=colours.get(tone, self._theme.TEXT_FAINT))

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in (
            self._scan_button,
            self._scan_disk_button,
            self._auto_button,
            self._undo_button,
            self._settings_button,
        ):
            try:
                button.configure(state=state)
            except (AttributeError, tk.TclError):
                pass
        if busy:
            self._set_status(text or "Working…", tone="busy")
        self._refresh_route_button()

    def _show_error(self, title: str, exc: BaseException) -> None:
        self._set_status(f"{title}: {exc}", tone="error")
        try:
            messagebox.showerror(APP_NAME, f"{title}\n\n{exc}", parent=self)
        except tk.TclError:  # pragma: no cover - no display during teardown
            pass


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sortwise",
        description="Sortwise - native desktop document router (CustomTkinter).",
    )
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--ledger", default=None, help="Path to history.json")
    parser.add_argument("--watch", default=None, help="Override the watch folder for this session")
    parser.add_argument("--target", default=None, help="Override the target root for this session")
    parser.add_argument(
        "--no-scan-wizard",
        "--no-scan-dialog",
        dest="no_scan_dialog",
        action="store_true",
        help="Do not show the scan target wizard on startup",
    )
    parser.add_argument("--version", action="store_true", help="Print the version and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Open the native window.  No browser, no webview, no HTTP server."""
    args = parse_args(argv)
    if args.version:
        from src.server import __version__

        print(f"{APP_NAME} {__version__} (native desktop)")
        return 0

    config_path = Path(args.config).expanduser() if args.config else None
    ledger_path = Path(args.ledger).expanduser() if args.ledger else None

    try:
        app = SortwiseApp(
            config_path=config_path,
            ledger_path=ledger_path,
            show_scan_dialog=not args.no_scan_dialog,
        )
    except tk.TclError as exc:  # pragma: no cover - no display available
        print(
            f"[sortwise] could not open a window ({exc}).\n"
            "[sortwise] this is a native desktop app and needs an X11/Wayland display.",
            file=sys.stderr,
        )
        return 1

    overrides: dict[str, Any] = {}
    if args.watch:
        overrides["watch_folder"] = args.watch
    if args.target:
        overrides["target_root"] = args.target
    if overrides:
        app._config_store.update(overrides)  # noqa: SLF001 - session override
        app.after(180, app.load_document_tree)

    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
