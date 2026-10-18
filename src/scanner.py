"""BCUninstaller-inspired multi-threaded disk scanner for Sortwise.

`Bulk Crap Uninstaller <https://github.com/BCUninstaller/Bulk-Crap-Uninstaller>`_
scans an entire Windows installation in seconds by (a) fanning the walk out
across a pool of worker threads, (b) hard-skipping directories that can only
produce permission errors or junk (``Windows\\WinSxS``, ``$Recycle.Bin``, ...),
and (c) streaming a live status line back to the UI while remaining cancellable.

This module ports those three ideas to POSIX and to the Sortwise problem of
finding *unorganised study documents*:

* **Multi-threaded** -- one bounded work queue of directories drained by a pool
  of worker threads (``os.scandir`` per directory), so the scan is I/O bound and
  finishes in a fraction of the time a single-threaded walk would take.
* **Smart exclusions** -- ``/proc``, ``/sys``, ``/dev``, ``/nix/store``,
  ``.git``, ``node_modules``, ``.cache`` and friends are skipped before they are
  ever opened, which keeps the walk fast and free of ``PermissionError`` noise.
* **Streaming progress + cancel** -- :class:`ScanProgress` snapshots are pushed
  to a caller-supplied callback (the UI marshals them onto the Tk thread) and a
  :class:`threading.Event` can stop the walk mid-flight.
* **Confidence rating** -- every discovered file is scored against the subject
  taxonomy and rated ``CONFIDENT`` (``>= 0.70`` and low entropy) or
  ``AMBIGUOUS`` for the review queue, mirroring the calibrated router.

The module is deliberately free of Tk / FastAPI imports so it can be unit
tested in isolation and reused by the CLI.
"""

from __future__ import annotations

import os
import queue as _queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .calibrator import (
    CONFIDENCE_THRESHOLD,
    ENTROPY_THRESHOLD,
    STATUS_AMBIGUOUS,
    STATUS_CONFIDENT,
    shannon_entropy,
    tempered_softmax,
)
from .taxonomy import get_subject_taxonomy

__all__ = [
    "DEFAULT_EXCLUDED_NAMES",
    "DEFAULT_EXCLUDED_PATHS",
    "DEFAULT_EXTENSIONS",
    "SCANNER_VERSION",
    "ConfidenceRating",
    "DiskScanner",
    "ScanProgress",
    "ScannedDocument",
    "default_workers",
    "human_size",
    "is_excluded_name",
    "is_excluded_path",
    "keyword_scores",
    "normalise_token",
    "preset_targets",
    "rate_document",
    "rate_scores",
]

SCANNER_VERSION = "1.0"

# The document formats the router understands (kept in sync with the server).
DEFAULT_EXTENSIONS: tuple[str, ...] = ("pdf", "docx", "pptx")

#: Directory *names* that never hold a user's study documents.  Matching is
#: case-sensitive on POSIX but the set stores the conventional spellings.
DEFAULT_EXCLUDED_NAMES: frozenset[str] = frozenset(
    {
        # VCS / build / dependency trees
        ".git", ".hg", ".svn", ".bzr",
        "node_modules", "bower_components", "vendor",
        "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
        ".venv", "venv", "env", ".eggs", "site-packages", "dist-packages",
        "build", "dist", ".gradle", ".m2", ".cargo", ".rustup", ".npm", ".pnpm-store",
        # OS / session junk
        ".cache", ".local", ".config", "lost+found", ".Trash", ".Trash-1000",
        "Trash", ".snap", ".steam", ".var", ".flatpak", ".dbus", ".gnupg",
        ".ssh", ".thunderbird", ".mozilla", ".wine", ".ICEauthority",
        # virtual filesystems (also covered by absolute prefixes below)
        "proc", "sys", "dev", "run", "boot", "tmp",
        # container / system trees
        "nix", "pkgs", "overlay", "usr", "lib", "lib32", "lib64", "bin", "sbin",
    }
)

#: Absolute path prefixes excluded regardless of the directory name.  These are
#: the pseudo- and system filesystems BCUninstaller also refuses to walk.
DEFAULT_EXCLUDED_PATHS: tuple[str, ...] = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/nix/store",
    "/nix/var",
    "/snap",
    "/lost+found",
    "/var/lib",
    "/var/cache",
    "/boot",
    "/media",
    "/mnt",
    "/usr",
    "/lib",
    "/lib64",
    "/bin",
    "/sbin",
    "/opt",
    "/etc",
    "/root",
)

# Keyword -> weight mapping for the transparent, model-free confidence rating.
_W_CODE = 4.0
_W_NAME_TOKEN = 2.0
_W_KEYWORD = 1.0

# Softmax temperature used to turn raw keyword scores into probabilities.  A
# value below 1 sharpens the distribution so a decisive match clears the gate.
_RATING_TEMPERATURE = 0.5


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def normalise_token(text: str) -> str:
    """Lower-case ``text`` and turn every separator into a single space."""
    cleaned = []
    for char in str(text or "").casefold():
        cleaned.append(char if char.isalnum() else " ")
    return " ".join("".join(cleaned).split())


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


def default_workers() -> int:
    """A sensible thread-pool size for an I/O-bound directory walk."""
    cpu = os.cpu_count() or 4
    return max(2, min(8, cpu * 2))


def is_excluded_name(name: str) -> bool:
    return (name or "") in DEFAULT_EXCLUDED_NAMES


def is_excluded_path(path: str | os.PathLike[str]) -> bool:
    """True when ``path`` is, or lives inside, an excluded system location."""
    candidate = os.path.normpath(str(path))
    for prefix in DEFAULT_EXCLUDED_PATHS:
        if candidate == prefix or candidate.startswith(prefix + os.sep):
            return True
    return False


def preset_targets(home: str | os.PathLike[str] | None = None) -> list[tuple[str, str]]:
    """Common scan roots that actually exist, as ``(label, path)`` pairs."""
    base = Path(os.path.expanduser(str(home))) if home else Path.home()
    candidates: tuple[tuple[str, Path], ...] = (
        ("Downloads", base / "Downloads"),
        ("Documents", base / "Documents"),
        ("Desktop", base / "Desktop"),
        ("Pictures", base / "Pictures"),
        ("Home folder", base),
    )
    found: list[tuple[str, str]] = []
    for label, path in candidates:
        try:
            if path.is_dir():
                found.append((label, str(path)))
        except OSError:
            continue
    return found


# --------------------------------------------------------------------------- #
# Confidence rating (BCUninstaller-style, but calibrated on entropy too)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ConfidenceRating:
    """The outcome of scoring one filename against the subject taxonomy."""

    subject: str
    score: float
    confidence: float
    entropy: float
    status: str
    ranking: tuple[tuple[str, float], ...] = ()
    agreement: float = 1.0
    disagreement: float = 0.0

    @property
    def confident(self) -> bool:
        return self.status == STATUS_CONFIDENT


_COMPILED_PROFILES: dict[int, list[tuple[str, str, set[str], tuple[str, ...]]]] = {}


def _get_compiled_taxonomy(taxonomy: dict[str, dict]) -> list[tuple[str, str, set[str], tuple[str, ...]]]:
    tax_id = id(taxonomy)
    compiled = _COMPILED_PROFILES.get(tax_id)
    if compiled is None:
        compiled = []
        for label, entry in taxonomy.items():
            code = normalise_token(str(entry.get("code", "")))
            code_pad = f" {code} " if code else ""
            name_tokens = {
                t for t in normalise_token(str(entry.get("name", ""))).split() if len(t) > 3
            }
            kw_pads = tuple(
                f" {normalise_token(str(k))} "
                for k in entry.get("keywords", [])
                if k and normalise_token(str(k))
            )
            compiled.append((label, code_pad, name_tokens, kw_pads))
        _COMPILED_PROFILES[tax_id] = compiled
    return compiled


def keyword_scores(name: str, taxonomy: dict[str, dict]) -> dict[str, float]:
    """Transparent keyword match score for ``name`` against every subject.

    A subject's course *code* (``CS2227``) is the strongest signal, a word from
    the subject *name* is next, and a syllabus *keyword* is the weakest.  All
    matching is whole-word, so ``SQL`` never matches inside ``NoSQL``.
    """
    haystack = normalise_token(name)
    padded = f" {haystack} " if haystack else " "
    tokens = {token for token in haystack.split() if len(token) > 3}

    compiled = _get_compiled_taxonomy(taxonomy)
    scores: dict[str, float] = {}
    for label, code_pad, name_tokens, kw_pads in compiled:
        score = 0.0
        if code_pad and code_pad in padded:
            score += _W_CODE
        for token in name_tokens:
            if token in tokens:
                score += _W_NAME_TOKEN
        for kw_pad in kw_pads:
            if kw_pad in padded:
                score += _W_KEYWORD
        scores[label] = score
    return scores


def rate_scores(
    scores: dict[str, float],
    *,
    threshold: float = CONFIDENCE_THRESHOLD,
    entropy_threshold: float = ENTROPY_THRESHOLD,
    temperature: float = _RATING_TEMPERATURE,
    agreement: float = 1.0,
    disagreement: float = 0.0,
) -> ConfidenceRating:
    """Turn raw keyword scores into a calibrated :class:`ConfidenceRating`."""
    labels = list(scores)
    if not labels:
        return ConfidenceRating("", 0.0, 0.0, 0.0, STATUS_AMBIGUOUS, (), agreement=0.0, disagreement=1.0)

    values = [float(scores[label]) for label in labels]
    probs = tempered_softmax(values, temperature)
    order = sorted(range(len(values)), key=lambda i: probs[i], reverse=True)
    best = order[0]
    confidence = float(probs[best])
    entropy = shannon_entropy(probs)
    confident = confidence >= threshold and entropy < entropy_threshold and disagreement <= 0.25
    ranking = tuple((labels[i], float(probs[i])) for i in order)
    return ConfidenceRating(
        subject=labels[best],
        score=float(values[best]),
        confidence=confidence,
        entropy=entropy,
        status=STATUS_CONFIDENT if confident else STATUS_AMBIGUOUS,
        ranking=ranking,
        agreement=agreement,
        disagreement=disagreement,
    )


def rate_document(
    name: str,
    taxonomy: dict[str, dict] | None = None,
    *,
    path: str | None = None,
    sample_text: str | None = None,
    threshold: float = CONFIDENCE_THRESHOLD,
    entropy_threshold: float = ENTROPY_THRESHOLD,
    temperature: float = _RATING_TEMPERATURE,
) -> ConfidenceRating:
    """Score a document (from content if available, falling back to filename) and rate it."""
    taxonomy = taxonomy if taxonomy is not None else get_subject_taxonomy()
    text = sample_text or ""
    if not text and path:
        try:
            from .rlcd import quick_extract_sample
            text = quick_extract_sample(path, 1500)
        except Exception:
            text = ""

    eval_text = f"{name} {text}".strip()
    scores = keyword_scores(eval_text, taxonomy)
    try:
        from .rlcd import get_default_policy_store
        ps = get_default_policy_store()
        for label in scores:
            scores[label] += ps.get_bias(label)
    except Exception:
        pass
    return rate_scores(
        scores,
        threshold=threshold,
        entropy_threshold=entropy_threshold,
        temperature=temperature,
    )


# --------------------------------------------------------------------------- #
# Progress + result records
# --------------------------------------------------------------------------- #
@dataclass
class ScanProgress:
    """A live snapshot of an in-flight scan (safe to hand to the UI)."""

    current: str = ""
    directories: int = 0
    files_seen: int = 0
    documents: int = 0
    bytes_seen: int = 0
    elapsed: float = 0.0
    cancelled: bool = False
    done: bool = False

    def summary(self) -> str:
        return (
            f"{self.directories} folders · {self.files_seen} files · "
            f"{self.documents} documents · {self.elapsed:.1f}s"
        )


@dataclass
class ScannedDocument:
    """One supported document discovered by :class:`DiskScanner`."""

    path: str
    name: str
    file_type: str
    size: int
    size_human: str
    modified: str
    subject: str
    confidence: float
    entropy: float
    status: str
    score: float = 0.0
    ranking: tuple[tuple[str, float], ...] = ()
    agreement: float = 1.0
    disagreement: float = 0.0

    @property
    def confident(self) -> bool:
        return self.status == STATUS_CONFIDENT

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "file_type": self.file_type,
            "size": self.size,
            "size_human": self.size_human,
            "modified": self.modified,
            "subject": self.subject,
            "confidence": self.confidence,
            "entropy": self.entropy,
            "status": self.status,
            "score": self.score,
        }


# --------------------------------------------------------------------------- #
# The scanner
# --------------------------------------------------------------------------- #
class DiskScanner:
    """Walk one or more roots on a worker-thread pool and rate every document."""

    def __init__(
        self,
        extensions: Iterable[str] | None = None,
        *,
        workers: int | None = None,
        excluded_names: Iterable[str] | None = None,
        excluded_paths: Iterable[str] | None = None,
        cross_devices: bool = False,
        progress_interval: float = 0.1,
    ) -> None:
        self.extensions = frozenset(
            str(ext).strip().lstrip(".").casefold()
            for ext in (extensions or DEFAULT_EXTENSIONS)
            if str(ext).strip()
        )
        self.workers = max(1, int(workers)) if workers else default_workers()
        self.excluded_names = frozenset(excluded_names or DEFAULT_EXCLUDED_NAMES)
        self.excluded_paths = tuple(excluded_paths or DEFAULT_EXCLUDED_PATHS)
        self.cross_devices = bool(cross_devices)
        self.progress_interval = max(0.0, float(progress_interval))

    # -- exclusion rules --------------------------------------------------- #
    def excluded(
        self, name: str, path: str, prefixes: Sequence[str] | None = None
    ) -> bool:
        if name in self.excluded_names:
            return True
        for prefix in prefixes if prefixes is not None else self.excluded_paths:
            if path == prefix or path.startswith(prefix + os.sep):
                return True
        return False

    def _active_prefixes(self, roots: Sequence[str]) -> tuple[str, ...]:
        """Excluded path prefixes that still apply for this set of roots.

        A prefix is dropped when one of the *chosen* roots lives inside it, so
        explicitly scanning ``/tmp/work`` (or any other otherwise-excluded tree)
        does not silently return nothing.  System prefixes such as ``/proc`` are
        always kept because they can never be an ancestor of a user root.
        """
        active: list[str] = []
        for prefix in self.excluded_paths:
            shadowed = any(
                root == prefix or root.startswith(prefix + os.sep) for root in roots
            )
            if not shadowed:
                active.append(prefix)
        return tuple(active)

    def _eligible(self, entry: os.DirEntry[str], prefixes: Sequence[str]) -> bool:
        return not self.excluded(entry.name, entry.path, prefixes)

    # -- public API -------------------------------------------------------- #
    def scan(
        self,
        roots: Sequence[str | os.PathLike[str]],
        *,
        recursive: bool = True,
        max_depth: int | None = None,
        on_progress: Callable[[ScanProgress], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> list[ScannedDocument]:
        """Scan ``roots`` and return every supported, rated document.

        ``on_progress`` is invoked (throttled) from the worker threads with a
        :class:`ScanProgress` snapshot.  Setting ``cancel`` stops the walk as
        soon as the workers notice it; the documents found so far are returned.
        """
        cancel = cancel if cancel is not None else threading.Event()
        taxonomy = get_subject_taxonomy()

        root_items: list[tuple[str, int]] = []
        for root in roots:
            path = Path(os.path.expanduser(os.path.expandvars(str(root))))
            try:
                if not path.is_dir():
                    continue
                device = path.stat().st_dev
            except OSError:
                continue
            root_items.append((str(path), device))

        if not root_items:
            if on_progress is not None:
                on_progress(ScanProgress(done=True, cancelled=cancel.is_set()))
            return []

        active_prefixes = self._active_prefixes([path for path, _ in root_items])

        work: "_queue.Queue[tuple[str, int, int]]" = _queue.Queue()
        lock = threading.Lock()
        stop = threading.Event()
        results: list[ScannedDocument] = []
        counters = {
            "directories": 0,
            "files_seen": 0,
            "documents": 0,
            "bytes_seen": 0,
            "current": root_items[0][0],
        }
        started = time.monotonic()
        last_emit = [0.0]

        def emit(force: bool = False, done: bool = False) -> None:
            if on_progress is None:
                return
            now = time.monotonic()
            if not force and now - last_emit[0] < self.progress_interval:
                return
            last_emit[0] = now
            with lock:
                snapshot = ScanProgress(
                    current=counters["current"],
                    directories=counters["directories"],
                    files_seen=counters["files_seen"],
                    documents=counters["documents"],
                    bytes_seen=counters["bytes_seen"],
                    elapsed=now - started,
                    cancelled=cancel.is_set(),
                    done=done,
                )
            try:
                on_progress(snapshot)
            except Exception:  # noqa: BLE001 - a bad callback must not kill the walk
                pass

        def worker() -> None:
            while not stop.is_set():
                try:
                    directory, depth, device = work.get(timeout=0.1)
                except _queue.Empty:
                    continue
                try:
                    if not cancel.is_set():
                        self._walk_directory(
                            directory,
                            depth,
                            device,
                            recursive,
                            max_depth,
                            taxonomy,
                            work,
                            results,
                            counters,
                            lock,
                            cancel,
                            active_prefixes,
                        )
                except Exception:
                    pass
                finally:
                    work.task_done()
                    try:
                        emit()
                    except Exception:
                        pass

        for path, device in root_items:
            work.put((path, 0, device))

        threads = [
            threading.Thread(target=worker, name=f"sortwise-scan-{i}", daemon=True)
            for i in range(self.workers)
        ]
        for thread in threads:
            thread.start()

        # Safely wait for workers: if cancelled, drain remaining tasks to exit immediately
        while not work.empty() and not cancel.is_set():
            time.sleep(0.02)
        if cancel.is_set():
            while True:
                try:
                    work.get_nowait()
                    work.task_done()
                except _queue.Empty:
                    break
        else:
            work.join()
        stop.set()
        for thread in threads:
            thread.join(timeout=1.0)
        try:
            emit(force=True, done=True)
        except Exception:
            pass

        results.sort(key=lambda doc: (-doc.confidence, -doc.size, doc.name.casefold()))
        return results

    # -- internals --------------------------------------------------------- #
    def _walk_directory(
        self,
        directory: str,
        depth: int,
        device: int,
        recursive: bool,
        max_depth: int | None,
        taxonomy: dict[str, dict],
        work: "_queue.Queue[tuple[str, int, int]]",
        results: list[ScannedDocument],
        counters: dict[str, object],
        lock: threading.Lock,
        cancel: threading.Event,
        prefixes: Sequence[str],
    ) -> None:
        try:
            entries: list[os.DirEntry[str]] = list(os.scandir(directory))
        except Exception:
            return

        with lock:
            counters["directories"] = int(counters["directories"]) + 1
            counters["current"] = directory

        for entry in entries:
            if cancel.is_set():
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.startswith("."):
                        continue
                    if not recursive:
                        continue
                    if max_depth is not None and depth >= max_depth:
                        continue
                    if not self._eligible(entry, prefixes):
                        continue
                    try:
                        child_device = entry.stat(follow_symlinks=False).st_dev
                    except Exception:
                        continue
                    if not self.cross_devices and child_device != device:
                        continue
                    work.put((entry.path, depth + 1, child_device))
                elif entry.is_file(follow_symlinks=False):
                    if entry.name.startswith("."):
                        continue
                    extension = _extension_of(entry.name)
                    with lock:
                        counters["files_seen"] = int(counters["files_seen"]) + 1
                    if extension not in self.extensions:
                        continue
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except Exception:
                        continue
                    try:
                        rating = rate_document(entry.name, taxonomy)
                        document = ScannedDocument(
                            path=entry.path,
                            name=entry.name,
                            file_type=extension,
                            size=int(stat.st_size),
                            size_human=human_size(stat.st_size),
                            modified=datetime.fromtimestamp(stat.st_mtime).isoformat(
                                timespec="seconds"
                            ),
                            subject=rating.subject,
                            confidence=rating.confidence,
                            entropy=rating.entropy,
                            status=rating.status,
                            score=rating.score,
                            ranking=rating.ranking,
                        )
                        with lock:
                            results.append(document)
                            counters["documents"] = int(counters["documents"]) + 1
                            counters["bytes_seen"] = int(counters["bytes_seen"]) + int(
                                stat.st_size
                            )
                    except Exception:
                        continue
            except Exception:
                continue


def _extension_of(name: str) -> str:
    stem, dot, suffix = name.rpartition(".")
    if not dot or not stem:
        return ""
    return suffix.casefold()
