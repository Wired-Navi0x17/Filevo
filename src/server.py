"""Sortwise -- Calibrated Document Router (Step 2 backend).

A FastAPI service that exposes the Step 1 RLCD pipeline (:mod:`src.extractors`,
:mod:`src.taxonomy`, :mod:`src.calibrator`) to the desktop UI, so the whole
system can be driven from a window instead of a script.

What it does
------------
* **Config** -- read/update the watch folder, target root, confidence and
  entropy gates, auto-move toggle, model and rename templates.  Persisted as
  JSON so the settings survive restarts.
* **Taxonomy** -- expose the eight subject profiles and the folder each one
  resolves to under the target root.
* **Scan** -- list the routable documents sitting in the watch folder.
* **Route** -- extract, calibrate, rename and (optionally) move one file or a
  batch.  Every real move is appended to an undo ledger.
* **History / undo** -- a 1-click ledger of every transfer that can be replayed
  backwards with :func:`shutil.move`.

Design notes
------------
Endpoints are plain ``def`` (not ``async def``) so the CPU / disk-bound work --
PDF parsing, embedding inference, file moves -- runs on Starlette's worker
threadpool and never blocks the event loop.

The classifier is injected, so tests (and the GUI's browser fallback) can run
without loading the Sentence-Transformer.  Otherwise it is built lazily on the
first route and cached.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .calibrator import (
    CONFIDENCE_THRESHOLD,
    ENTROPY_THRESHOLD,
    STATUS_AMBIGUOUS,
    STATUS_CONFIDENT,
    CalibratedClassifier,
    CalibratedDecision,
)
from .extractors import DocumentExtractionError, ExtractedDoc, extract_document
from .taxonomy import discover_target_taxonomy, get_subject_taxonomy, subject_labels

__all__ = [
    "APP_NAME",
    "DEFAULT_PORT",
    "SUPPORTED_EXTENSIONS",
    "ConfigStore",
    "Ledger",
    "SortwiseConfig",
    "SortwiseError",
    "SortwiseService",
    "create_app",
    "sanitize_filename",
    "unique_path",
]

APP_NAME = "Sortwise"
DEFAULT_PORT = 8765
__version__ = "0.2.0"

SUPPORTED_EXTENSIONS: tuple[str, ...] = ("pdf", "docx", "pptx")
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Characters that are unsafe in a filename on at least one common filesystem.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_MAX_FILENAME_STEM = 120


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class SortwiseError(Exception):
    """Expected, user-facing failure that maps to an HTTP status code."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Filesystem helpers
# --------------------------------------------------------------------------- #
def expand_path(value: str | os.PathLike[str]) -> Path:
    """Expand ``~`` / environment variables and return an absolute path."""
    return Path(os.path.expandvars(str(value))).expanduser()


def sanitize_filename(name: str, fallback: str = "document") -> str:
    """Make ``name`` safe for every filesystem we care about.

    Slashes, control characters and the Windows reserved set are replaced with
    a dash; runs of whitespace collapse to single spaces; leading/trailing dots
    and spaces are trimmed (trailing dots are illegal on Windows).
    """
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("-", str(name or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip(". ")
    return cleaned or fallback


def unique_path(directory: Path, filename: str) -> Path:
    """Return a collision-free path for ``filename`` inside ``directory``.

    ``notes.pdf`` becomes ``notes (1).pdf``, ``notes (2).pdf`` ... when the
    earlier candidates already exist.
    """
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for index in range(1, 10_000):
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise SortwiseError(f"could not find a free filename for '{filename}'", 500)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _xdg_config_home() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    return expand_path(root) if root else Path.home() / ".config"


def _xdg_data_home() -> Path:
    root = os.environ.get("XDG_DATA_HOME")
    return expand_path(root) if root else Path.home() / ".local" / "share"


def default_config_path() -> Path:
    override = os.environ.get("SORTWISE_CONFIG_PATH")
    if override:
        return expand_path(override)
    return _xdg_config_home() / "sortwise" / "config.json"


def default_ledger_path() -> Path:
    override = os.environ.get("SORTWISE_LEDGER_PATH")
    if override:
        return expand_path(override)
    return _xdg_data_home() / "sortwise" / "history.json"


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclass
class SortwiseConfig:
    """User-tunable settings for the router."""

    watch_folder: str = "~/Downloads"
    target_root: str = "~/Documents/Sortwise"
    confidence_threshold: float = CONFIDENCE_THRESHOLD
    entropy_threshold: float = ENTROPY_THRESHOLD
    auto_move: bool = False
    operation_mode: str = "move"  # "move" or "copy"
    recursive: bool = False
    extensions: list[str] = field(default_factory=lambda: list(SUPPORTED_EXTENSIONS))
    model_name: str = "all-MiniLM-L6-v2"
    temperature: float = 0.15
    rename_template: str = "{title}"
    subject_folder_template: str = "{label}"

    # -- (de)serialisation ------------------------------------------------- #
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SortwiseConfig":
        data = data or {}
        defaults = cls()
        kwargs: dict[str, Any] = {}
        for key in (
            "watch_folder",
            "target_root",
            "confidence_threshold",
            "entropy_threshold",
            "auto_move",
            "operation_mode",
            "recursive",
            "extensions",
            "model_name",
            "temperature",
            "rename_template",
            "subject_folder_template",
        ):
            if key in data and data[key] is not None:
                kwargs[key] = data[key]
            else:
                kwargs[key] = getattr(defaults, key)
        config = cls(**kwargs)
        config.normalise()
        return config

    def normalise(self) -> "SortwiseConfig":
        """Coerce values into a sane, in-range state (mutates ``self``)."""
        self.watch_folder = str(expand_path(self.watch_folder))
        self.target_root = str(expand_path(self.target_root))

        self.confidence_threshold = _clamp_float(self.confidence_threshold, 0.0, 1.0, 0.70)
        self.entropy_threshold = _clamp_float(self.entropy_threshold, 0.0, 10.0, 1.5)
        self.temperature = _clamp_float(self.temperature, 0.001, 10.0, 0.15)

        extensions = [
            str(ext).strip().lstrip(".").casefold()
            for ext in (self.extensions or [])
            if str(ext).strip()
        ]
        self.extensions = sorted({ext for ext in extensions if ext}) or list(
            SUPPORTED_EXTENSIONS
        )

        self.auto_move = bool(self.auto_move)
        mode = str(self.operation_mode or "move").casefold()
        self.operation_mode = "copy" if mode == "copy" else "move"
        self.recursive = bool(self.recursive)
        self.model_name = str(self.model_name or "all-MiniLM-L6-v2")
        self.rename_template = str(self.rename_template or "{title}")
        self.subject_folder_template = str(
            self.subject_folder_template or "{label}"
        )
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "watch_folder": self.watch_folder,
            "target_root": self.target_root,
            "confidence_threshold": self.confidence_threshold,
            "entropy_threshold": self.entropy_threshold,
            "auto_move": self.auto_move,
            "operation_mode": self.operation_mode,
            "recursive": self.recursive,
            "extensions": list(self.extensions),
            "model_name": self.model_name,
            "temperature": self.temperature,
            "rename_template": self.rename_template,
            "subject_folder_template": self.subject_folder_template,
        }


def _clamp_float(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


class ConfigStore:
    """JSON-backed, atomically-written configuration store."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def load(self) -> SortwiseConfig:
        data: dict[str, Any] = {}
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return SortwiseConfig.from_dict(data)

    def save(self, config: SortwiseConfig) -> SortwiseConfig:
        config.normalise()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8"
            )
            os.replace(tmp, self.path)
        return config

    def update(self, changes: dict[str, Any]) -> SortwiseConfig:
        """Merge ``changes`` (ignoring ``None`` values) into the stored config."""
        current = self.load().to_dict()
        for key, value in (changes or {}).items():
            if key in current and value is not None:
                current[key] = value
        return self.save(SortwiseConfig.from_dict(current))


# --------------------------------------------------------------------------- #
# Undo ledger
# --------------------------------------------------------------------------- #
class Ledger:
    """Append-only JSON log of file transfers, with a 1-click undo."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._entries: list[dict[str, Any]] = self._read()

    def _read(self) -> list[dict[str, Any]]:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except (OSError, ValueError):
            pass
        return []

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._entries, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(tmp, self.path)

    def reload(self) -> None:
        with self._lock:
            self._entries = self._read()

    def add(self, entry: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = {"id": uuid.uuid4().hex[:12], **_entry_defaults(), **entry}
            record["timestamp"] = record.get("timestamp") or _now_iso()
            self._entries.append(record)
            self._write()
            return record

    def all(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._entries)
        items.reverse()  # newest first
        if limit is not None and limit >= 0:
            return items[:limit]
        return items

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            for entry in self._entries:
                if entry.get("id") == entry_id:
                    return dict(entry)
        return None

    def update(self, entry_id: str, **changes: Any) -> dict[str, Any] | None:
        with self._lock:
            for entry in self._entries:
                if entry.get("id") == entry_id:
                    entry.update(changes)
                    self._write()
                    return dict(entry)
        return None

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries = []
            self._write()
        return count


def _entry_defaults() -> dict[str, Any]:
    return {
        "timestamp": "",
        "action": "move",
        "source": "",
        "destination": None,
        "subject": "",
        "confidence": 0.0,
        "entropy": 0.0,
        "status": STATUS_AMBIGUOUS,
        "renamed_to": None,
        "manual": False,
        "undone": False,
        "undo_of": None,
        "message": "",
    }


# --------------------------------------------------------------------------- #
# Service layer (all real work lives here; endpoints stay thin)
# --------------------------------------------------------------------------- #
class SortwiseService:
    """Extraction + calibration + safe move, with an undo ledger."""

    def __init__(
        self,
        config_store: ConfigStore,
        ledger: Ledger,
        classifier: Any | None = None,
        classifier_factory: Callable[[SortwiseConfig], Any] | None = None,
    ) -> None:
        self.config_store = config_store
        self.ledger = ledger
        self._classifier = classifier
        self._classifier_signature: tuple[str, float] | None = (
            None if classifier is None else ("<injected>", 0.0)
        )
        self._classifier_factory = classifier_factory or self._default_factory
        self._model_lock = threading.Lock()
        self.started_at = time.time()

    def _default_factory(self, config: SortwiseConfig) -> CalibratedClassifier:
        taxonomy = self.current_taxonomy(config)
        return CalibratedClassifier(
            model_name=config.model_name,
            temperature=config.temperature,
            taxonomy=taxonomy,
        )

    @property
    def model_loaded(self) -> bool:
        if self._classifier is None:
            return False
        # A real classifier only counts as "loaded" once its model exists.
        return getattr(self._classifier, "_model", True) is not None

    def classifier(self, config: SortwiseConfig) -> Any:
        """Return the classifier, building / rebuilding it when settings change."""
        taxonomy = self.current_taxonomy(config)
        tax_keys = tuple(sorted(taxonomy.keys()))
        signature = (config.model_name, float(config.temperature), tax_keys)
        with self._model_lock:
            if self._classifier is None or (
                self._classifier_signature is not None
                and self._classifier_signature != signature
                and self._classifier_signature != ("<injected>", 0.0)
            ):
                self._classifier = self._classifier_factory(config)
                self._classifier_signature = signature
            return self._classifier

    # -- taxonomy ---------------------------------------------------------- #
    def current_taxonomy(self, config: SortwiseConfig) -> dict[str, dict]:
        return discover_target_taxonomy(config.target_root)

    def subject_folder_name(self, label: str, config: SortwiseConfig) -> str:
        taxonomy = self.current_taxonomy(config)
        entry = taxonomy.get(label, {})
        mapping = {
            "label": label,
            "code": str(entry.get("code", "") or ""),
            "name": str(entry.get("name", "") or label),
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        rendered = _PLACEHOLDER.sub(
            lambda m: mapping.get(m.group(1), m.group(0)),
            config.subject_folder_template,
        )
        return sanitize_filename(rendered, fallback=sanitize_filename(label, "subject"))

    def destination_folder(self, label: str, config: SortwiseConfig) -> Path:
        return expand_path(config.target_root) / self.subject_folder_name(label, config)

    def subjects(self, config: SortwiseConfig) -> list[dict[str, Any]]:
        taxonomy = self.current_taxonomy(config)
        subjects: list[dict[str, Any]] = []
        for label, entry in taxonomy.items():
            folder = self.destination_folder(label, config)
            subjects.append(
                {
                    "label": label,
                    "code": entry.get("code", ""),
                    "name": entry.get("name", ""),
                    "keywords": list(entry.get("keywords", [])),
                    "keyword_count": len(entry.get("keywords", [])),
                    "syllabus": entry.get("syllabus", ""),
                    "folder": str(folder),
                    "folder_exists": folder.is_dir(),
                }
            )
        return subjects

    # -- scanning ---------------------------------------------------------- #
    def scan(
        self, config: SortwiseConfig, path: str | None = None
    ) -> dict[str, Any]:
        root = expand_path(path) if path else expand_path(config.watch_folder)
        if not root.exists():
            raise SortwiseError(f"watch folder does not exist: {root}", 404)
        if not root.is_dir():
            raise SortwiseError(f"not a folder: {root}", 400)

        allowed = set(config.extensions)
        iterator: Iterable[Path] = (
            root.rglob("*") if config.recursive else root.glob("*")
        )

        files: list[dict[str, Any]] = []
        for candidate in iterator:
            try:
                if not candidate.is_file():
                    continue
            except OSError:
                continue
            if candidate.name.startswith("."):
                continue
            file_type = candidate.suffix.lstrip(".").casefold()
            if file_type not in allowed:
                continue
            try:
                stat = candidate.stat()
            except OSError:
                continue
            files.append(
                {
                    "name": candidate.name,
                    "path": str(candidate),
                    "relative": str(candidate.relative_to(root)),
                    "file_type": file_type,
                    "size": stat.st_size,
                    "size_human": human_size(stat.st_size),
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(timespec="seconds"),
                    "modified_ts": stat.st_mtime,
                }
            )

        files.sort(key=lambda item: item["modified_ts"], reverse=True)
        return {
            "folder": str(root),
            "recursive": config.recursive,
            "extensions": sorted(allowed),
            "count": len(files),
            "files": files,
        }

    # -- rename ------------------------------------------------------------ #
    @staticmethod
    def suggest_rename(
        doc: ExtractedDoc, config: SortwiseConfig, subject: str | None = None
    ) -> str:
        """Render ``config.rename_template`` into a smart filename suggestion.

        ``{title}`` is the document title the extractor recovered (metadata
        title, first heading, or the original stem); the remaining placeholders
        come from the routed subject when one is known.
        """
        entry = discover_target_taxonomy(config.target_root).get(subject or "", {})
        mapping = {
            "title": doc.title or Path(doc.path).stem,
            "stem": Path(doc.path).stem,
            "file_type": doc.file_type,
            "code": str(entry.get("code", "") or ""),
            "name": str(entry.get("name", "") or ""),
            "subject": subject or "",
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        rendered = _PLACEHOLDER.sub(
            lambda m: mapping.get(m.group(1), m.group(0)), config.rename_template
        )
        stem = sanitize_filename(rendered, fallback="document")[:_MAX_FILENAME_STEM]
        return f"{stem}.{doc.file_type}"

    @staticmethod
    def normalise_rename(rename: str | None, file_type: str) -> str | None:
        """Sanitise a user-supplied filename and guarantee the right extension."""
        if rename is None:
            return None
        name = sanitize_filename(rename, fallback="document")
        suffix = Path(name).suffix.lstrip(".").casefold()
        if suffix != file_type.casefold():
            stem = sanitize_filename(Path(name).stem, fallback="document")
            name = f"{stem}.{file_type}"
        stem = Path(name).stem[:_MAX_FILENAME_STEM] or "document"
        return f"{stem}{Path(name).suffix}"

    # -- routing ----------------------------------------------------------- #
    def _decision(self, doc: ExtractedDoc, config: SortwiseConfig) -> CalibratedDecision:
        classifier = self.classifier(config)
        return classifier.classify_document(doc)

    def _status(self, confidence: float, entropy: float, config: SortwiseConfig) -> str:
        confident = (
            confidence >= config.confidence_threshold
            and entropy < config.entropy_threshold
        )
        return STATUS_CONFIDENT if confident else STATUS_AMBIGUOUS

    def route(
        self,
        *,
        path: str,
        config: SortwiseConfig,
        rename: str | None = None,
        subject: str | None = None,
        move: bool | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        source = expand_path(path)
        if not source.exists():
            raise SortwiseError(f"file does not exist: {source}", 404)
        if not source.is_file():
            raise SortwiseError(f"not a file: {source}", 400)

        file_type = source.suffix.lstrip(".").casefold()
        if file_type not in config.extensions:
            raise SortwiseError(
                f"unsupported file type '.{file_type}' "
                f"(allowed: {', '.join(config.extensions)})",
                415,
            )

        try:
            doc = extract_document(str(source))
        except DocumentExtractionError as exc:
            raise SortwiseError(str(exc), 422) from exc

        manual = bool(subject)
        telemetry_error: str | None = None
        try:
            decision = self._decision(doc, config)
            ranking = [
                {"subject": label, "score": float(score)}
                for label, score in decision.ranking
            ]
            confidence = float(decision.confidence)
            entropy = float(decision.entropy)
            chosen = subject or decision.subject
        except SortwiseError:
            raise
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            if not subject:
                raise SortwiseError(
                    f"calibration unavailable: {type(exc).__name__}: {exc}", 503
                ) from exc
            telemetry_error = f"{type(exc).__name__}: {exc}"
            ranking = []
            confidence = 0.0
            entropy = 0.0
            chosen = subject

        tax = self.current_taxonomy(config)
        if chosen not in tax:
            raise SortwiseError(f"unknown subject: {chosen}", 400)

        status = self._status(confidence, entropy, config)
        dest_dir = self.destination_folder(chosen, config)

        original_name = source.name
        requested = self.normalise_rename(rename, file_type)
        renamed = requested or self.normalise_rename(
            original_name, file_type
        ) or original_name
        suggested = self.suggest_rename(doc, config, chosen)

        requested_path = dest_dir / renamed
        collision = (
            requested_path.exists() and requested_path.resolve() != source.resolve()
        )
        target = unique_path(dest_dir, renamed)

        should_move = bool(move) if move is not None else (config.operation_mode != "copy" and bool(config.auto_move))
        operation = "copy" if (not should_move and config.operation_mode == "copy") else "move"
        # If caller explicitly requested operation or move
        if move is False and config.operation_mode == "copy":
            operation = "copy"
        perform = not dry_run and (should_move or config.auto_move)

        transferred = False
        message = ""
        if perform:
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                if operation == "copy":
                    shutil.copy2(str(source), str(target))
                    transferred = True
                    message = f"Copied to {target.name}"
                else:
                    shutil.move(str(source), str(target))
                    transferred = True
                    message = f"Moved to {target.name}"
                try:
                    from .rlcd import get_default_policy_store
                    ps = get_default_policy_store()
                    ps.record_feedback(
                        chosen_category=chosen,
                        predicted_category=decision.subject if not telemetry_error else chosen,
                        agreement=getattr(decision, "agreement", 1.0),
                        is_override=manual and (chosen != getattr(decision, "subject", chosen)),
                    )
                except Exception:
                    pass
            except OSError as exc:
                raise SortwiseError(f"could not transfer file: {exc}", 500) from exc
        else:
            message = "Preview only - nothing was transferred" if dry_run else "Left in place"

        result: dict[str, Any] = {
            "source": {
                "path": str(source),
                "name": original_name,
                "file_type": file_type,
                "size": source.stat().st_size if source.exists() else None,
            },
            "destination": {
                "folder": str(dest_dir),
                "path": str(target),
                "name": target.name,
                "planned_path": str(target),
                "requested_path": str(requested_path),
                "renamed": renamed != original_name,
                "collision": collision,
                "exists": target.exists(),
            },
            "subject": chosen,
            "predicted_subject": decision.subject if not telemetry_error else chosen,
            "manual": manual,
            "confidence": confidence,
            "entropy": entropy,
            "status": status,
            "ranking": ranking,
            "title": doc.title,
            "word_count": doc.word_count,
            "headings": doc.headings[:8],
            "rename": renamed,
            "renamed_from": original_name if renamed != original_name else None,
            "suggested_rename": suggested,
            "collision": collision,
            "moved": transferred,
            "transferred": transferred,
            "operation": operation,
            "dry_run": dry_run,
            "auto_move": bool(config.auto_move),
            "message": message,
            "telemetry_error": telemetry_error,
        }

        if transferred:
            entry = self.ledger.add(
                {
                    "action": operation,
                    "source": str(source),
                    "destination": str(target),
                    "subject": chosen,
                    "confidence": confidence,
                    "entropy": entropy,
                    "status": status,
                    "renamed_to": target.name,
                    "renamed_from": original_name,
                    "manual": manual,
                    "message": message,
                }
            )
            result["entry_id"] = entry["id"]
            result["timestamp"] = entry["timestamp"]

        return result

    def route_batch(
        self,
        *,
        paths: list[str],
        config: SortwiseConfig,
        move: bool | None = None,
        dry_run: bool = False,
        subject: str | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for path in paths:
            try:
                results.append(
                    self.route(
                        path=path,
                        config=config,
                        subject=subject,
                        move=move,
                        dry_run=dry_run,
                    )
                )
            except SortwiseError as exc:
                results.append(
                    {
                        "source": {"path": str(expand_path(path)), "name": Path(path).name},
                        "error": exc.message,
                        "status_code": exc.status_code,
                        "moved": False,
                    }
                )
        moved = sum(1 for item in results if item.get("moved"))
        return {
            "count": len(results),
            "moved": moved,
            "results": results,
        }

    # -- undo -------------------------------------------------------------- #
    def undo(self, entry_id: str) -> dict[str, Any]:
        entry = self.ledger.get(entry_id)
        if entry is None:
            raise SortwiseError(f"no ledger entry with id '{entry_id}'", 404)
        action = entry.get("action")
        if action not in ("move", "copy"):
            raise SortwiseError("only move or copy entries can be undone", 400)
        if entry.get("undone"):
            raise SortwiseError("this transfer was already undone", 409)

        destination = expand_path(entry.get("destination") or "")
        if not destination.exists():
            raise SortwiseError(
                f"the transferred file is gone: {destination}", 409
            )

        if action == "copy":
            try:
                destination.unlink()
            except OSError as exc:
                raise SortwiseError(f"could not remove copied file: {exc}", 500) from exc
            self.ledger.update(entry_id, undone=True, undo_of=entry_id)
            undo_entry = self.ledger.add(
                {
                    "action": "undo",
                    "source": str(destination),
                    "destination": None,
                    "subject": entry.get("subject", ""),
                    "confidence": entry.get("confidence", 0.0),
                    "entropy": entry.get("entropy", 0.0),
                    "status": entry.get("status", STATUS_AMBIGUOUS),
                    "undo_of": entry_id,
                    "message": f"Removed copy {destination.name}",
                }
            )
            return {
                "entry_id": entry_id,
                "removed_copy": str(destination),
                "undo_entry_id": undo_entry["id"],
                "message": f"Removed copy {destination.name}",
            }

        source = expand_path(entry.get("source", ""))
        source.parent.mkdir(parents=True, exist_ok=True)
        restore = source if not source.exists() else unique_path(source.parent, source.name)
        try:
            shutil.move(str(destination), str(restore))
        except OSError as exc:
            raise SortwiseError(f"could not undo transfer: {exc}", 500) from exc

        self.ledger.update(entry_id, undone=True, undo_of=entry_id)
        undo_entry = self.ledger.add(
            {
                "action": "undo",
                "source": str(destination),
                "destination": str(restore),
                "subject": entry.get("subject", ""),
                "confidence": entry.get("confidence", 0.0),
                "entropy": entry.get("entropy", 0.0),
                "status": entry.get("status", STATUS_AMBIGUOUS),
                "renamed_to": restore.name,
                "undo_of": entry_id,
                "message": f"Restored to {restore}",
            }
        )
        return {
            "entry_id": entry_id,
            "restored_to": str(restore),
            "undo_entry_id": undo_entry["id"],
            "message": f"Restored {destination.name} to {restore}",
        }

    # -- telemetry --------------------------------------------------------- #
    def health(self, config: SortwiseConfig) -> dict[str, Any]:
        watch = expand_path(config.watch_folder)
        try:
            scanned = self.scan(config)["count"] if watch.is_dir() else 0
        except SortwiseError:
            scanned = 0
        return {
            "app": APP_NAME,
            "version": __version__,
            "status": "online",
            "model_loaded": self.model_loaded,
            "model_name": config.model_name,
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "watch_folder": str(watch),
            "watch_folder_exists": watch.is_dir(),
            "queue_count": scanned,
            "history_count": len(self.ledger.all()),
            "auto_move": config.auto_move,
            "confidence_threshold": config.confidence_threshold,
            "entropy_threshold": config.entropy_threshold,
            "timestamp": _now_iso(),
        }


def human_size(num_bytes: int | float | None) -> str:
    """Render a byte count the way a file manager would."""
    if num_bytes is None:
        return "-"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class ConfigUpdate(BaseModel):
    watch_folder: str | None = None
    target_root: str | None = None
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    entropy_threshold: float | None = Field(default=None, ge=0.0)
    auto_move: bool | None = None
    operation_mode: str | None = None
    recursive: bool | None = None
    extensions: list[str] | None = None
    model_name: str | None = None
    temperature: float | None = Field(default=None, gt=0.0)
    rename_template: str | None = None
    subject_folder_template: str | None = None

    def changes(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ScanRequest(BaseModel):
    path: str | None = None


class RouteRequest(BaseModel):
    path: str | None = None
    paths: list[str] | None = None
    rename: str | None = None
    subject: str | None = None
    move: bool | None = None
    operation: str | None = None  # "copy" | "move"
    dry_run: bool = False


class BatchRouteRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    move: bool | None = None
    operation: str | None = None
    dry_run: bool = False
    subject: str | None = None


class RenameSuggestRequest(BaseModel):
    path: str
    subject: str | None = None


# --------------------------------------------------------------------------- #
# Application factory
# --------------------------------------------------------------------------- #
def create_app(
    config_path: str | os.PathLike[str] | None = None,
    ledger_path: str | os.PathLike[str] | None = None,
    classifier: Any | None = None,
    classifier_factory: Callable[[SortwiseConfig], Any] | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    Parameters are injectable so tests can point the config / ledger at a temp
    directory and swap in a lightweight classifier instead of loading
    ``all-MiniLM-L6-v2``.
    """
    config_store = ConfigStore(Path(config_path) if config_path else default_config_path())
    ledger = Ledger(Path(ledger_path) if ledger_path else default_ledger_path())
    service = SortwiseService(
        config_store,
        ledger,
        classifier=classifier,
        classifier_factory=classifier_factory,
    )

    app = FastAPI(title=f"{APP_NAME} - Calibrated Document Router", version=__version__)
    app.state.service = service
    app.state.config_store = config_store
    app.state.ledger = ledger

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def run(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a service call, translating :class:`SortwiseError` to HTTP."""
        try:
            return func(*args, **kwargs)
        except SortwiseError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # -- pages ------------------------------------------------------------- #
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        target = STATIC_DIR / "index.html"
        if not target.exists():
            raise HTTPException(status_code=500, detail="UI assets are missing")
        return FileResponse(str(target))

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        target = STATIC_DIR / "sortwise.svg"
        if not target.exists():
            raise HTTPException(status_code=404, detail="no icon")
        return FileResponse(str(target), media_type="image/svg+xml")

    # -- health ------------------------------------------------------------ #
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return service.health(config_store.load())

    # -- config ------------------------------------------------------------ #
    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return config_store.load().to_dict()

    @app.post("/api/config")
    @app.put("/api/config")
    def update_config(update: ConfigUpdate = Body(default_factory=ConfigUpdate)) -> dict[str, Any]:
        return config_store.update(update.changes()).to_dict()

    @app.post("/api/config/reset")
    def reset_config() -> dict[str, Any]:
        return config_store.save(SortwiseConfig()).to_dict()

    # -- taxonomy ---------------------------------------------------------- #
    @app.get("/api/subjects")
    def subjects() -> dict[str, Any]:
        config = config_store.load()
        items = service.subjects(config)
        return {
            "target_root": config.target_root,
            "subject_folder_template": config.subject_folder_template,
            "count": len(items),
            "subjects": items,
        }

    # -- scanning ---------------------------------------------------------- #
    @app.get("/api/scan")
    def scan_get(path: str | None = Query(default=None)) -> dict[str, Any]:
        return run(service.scan, config_store.load(), path)

    @app.post("/api/scan")
    def scan_post(request: ScanRequest = Body(default_factory=ScanRequest)) -> dict[str, Any]:
        return run(service.scan, config_store.load(), request.path)

    @app.post("/api/inspect")
    def inspect_file(request: ScanRequest) -> dict[str, Any]:
        """Directly inspect one or multiple individual files without walking a folder."""
        config = config_store.load()
        if not request.path:
            raise HTTPException(status_code=400, detail="'path' is required")
        source = expand_path(request.path)
        if not source.exists():
            raise HTTPException(status_code=404, detail=f"file not found: {source}")
        if source.is_dir():
            return run(service.scan, config, str(source))
        stat = source.stat()
        file_info = {
            "path": str(source),
            "name": source.name,
            "file_type": source.suffix.lstrip(".").casefold(),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            "modified_ts": stat.st_mtime,
        }
        return {
            "folder": str(source.parent),
            "count": 1,
            "files": [file_info],
        }

    # -- rename ------------------------------------------------------------ #
    @app.post("/api/rename/suggest")
    def rename_suggest(request: RenameSuggestRequest) -> dict[str, Any]:
        config = config_store.load()
        source = expand_path(request.path)
        if not source.is_file():
            raise HTTPException(status_code=404, detail=f"file does not exist: {source}")
        try:
            doc = extract_document(str(source))
        except DocumentExtractionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "path": str(source),
            "title": doc.title,
            "file_type": doc.file_type,
            "suggested": service.suggest_rename(doc, config, request.subject),
            "word_count": doc.word_count,
        }

    # -- routing ----------------------------------------------------------- #
    @app.post("/api/route")
    def route(request: RouteRequest) -> Any:
        config = config_store.load()
        move_param = request.move
        if request.operation == "copy":
            move_param = False
        elif request.operation == "move":
            move_param = True

        if request.paths:
            return service.route_batch(
                paths=request.paths,
                config=config,
                move=move_param,
                dry_run=request.dry_run,
                subject=request.subject,
            )
        if not request.path:
            raise HTTPException(status_code=400, detail="'path' or 'paths' is required")
        return run(
            service.route,
            path=request.path,
            config=config,
            rename=request.rename,
            subject=request.subject,
            move=move_param,
            dry_run=request.dry_run,
        )

    @app.post("/api/route/batch")
    def route_batch(request: BatchRouteRequest) -> dict[str, Any]:
        if not request.paths:
            raise HTTPException(status_code=400, detail="'paths' must not be empty")
        move_param = request.move
        if request.operation == "copy":
            move_param = False
        elif request.operation == "move":
            move_param = True
        return service.route_batch(
            paths=request.paths,
            config=config_store.load(),
            move=move_param,
            dry_run=request.dry_run,
            subject=request.subject,
        )

    # -- history ----------------------------------------------------------- #
    @app.get("/api/history")
    def history(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        entries = ledger.all(limit)
        return {"count": len(entries), "entries": entries}

    @app.post("/api/history/{entry_id}/undo")
    def undo(entry_id: str) -> dict[str, Any]:
        return run(service.undo, entry_id)

    @app.delete("/api/history")
    def clear_history() -> dict[str, Any]:
        return {"cleared": ledger.clear()}

    # -- live telemetry (WebSocket) --------------------------------------- #
    @app.websocket("/ws")
    async def live_telemetry(websocket: WebSocket) -> None:
        """Push a telemetry frame every couple of seconds.

        The desktop UI prefers this channel for liveness and falls back to
        polling ``/api/health`` when the socket cannot be established.
        """
        await websocket.accept()
        try:
            while True:
                config = config_store.load()
                await websocket.send_json(
                    {
                        "type": "telemetry",
                        "health": service.health(config),
                        "timestamp": _now_iso(),
                    }
                )
                await asyncio.sleep(2.0)
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            return
        except Exception:  # noqa: BLE001 - a broken socket must never crash the app
            return

    return app


# Convenience ASGI target: ``uvicorn src.server:app``
app = create_app()


def main() -> None:  # pragma: no cover - manual launcher
    """Run the server with uvicorn (development convenience)."""
    import uvicorn

    uvicorn.run(
        "src.server:app",
        host="127.0.0.1",
        port=DEFAULT_PORT,
        log_level="info",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
