"""Step 3 acceptance tests -- the BCUninstaller-inspired disk scanner.

The scanner is the engine behind the native app's "Scan Folder" / "Deep System
Scan" startup choice and its confidence-rated bulk routing.  These tests drive
it against temporary directory trees (no real disk traversal) and check:

* multi-threaded discovery of supported documents,
* smart exclusion of ``.git`` / ``node_modules`` / ``.cache`` style directories,
* confidence rating and the ``CONFIDENT`` / ``AMBIGUOUS`` tiers,
* live streaming progress and cooperative cancellation,
* the collision-safe keyword scoring helpers.
"""

from __future__ import annotations

import threading
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.calibrator import (
    CONFIDENCE_THRESHOLD,
    STATUS_AMBIGUOUS,
    STATUS_CONFIDENT,
)
from src.scanner import (
    DEFAULT_EXCLUDED_NAMES,
    DiskScanner,
    ScanProgress,
    default_workers,
    is_excluded_name,
    is_excluded_path,
    keyword_scores,
    normalise_token,
    preset_targets,
    rate_document,
    rate_scores,
)
from src.taxonomy import get_subject_taxonomy, subject_labels

AI_LABEL = "CS2227 - AI and ML"
ALGORITHMS_LABEL = "CS2000 - Design and Analysis of Algorithms"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    (root / "Downloads").mkdir(parents=True)
    (root / "Documents" / "Semester 3").mkdir(parents=True)
    (root / ".git" / "objects").mkdir(parents=True)
    (root / "project" / "node_modules" / "left-pad").mkdir(parents=True)
    (root / ".cache" / "pip").mkdir(parents=True)

    (root / "Downloads" / "CS2227 - AI and ML notes.pdf").write_bytes(b"%PDF-1.4")
    (root / "Downloads" / "algorithms lecture.docx").write_bytes(b"PK")
    (root / "Documents" / "Semester 3" / "random_photo_2043.pdf").write_bytes(b"%PDF-1.4")
    (root / "Documents" / "Semester 3" / "readme.txt").write_text("skip me", encoding="utf-8")
    (root / "Downloads" / ".hidden.pdf").write_bytes(b"%PDF-1.4")

    # These must never be discovered.
    (root / ".git" / "objects" / "pack-1.pptx").write_bytes(b"PK")
    (root / "project" / "node_modules" / "left-pad" / "doc.pdf").write_bytes(b"%PDF")
    (root / ".cache" / "pip" / "cached.pptx").write_bytes(b"PK")
    return root


# --------------------------------------------------------------------------- #
# Exclusion rules
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name",
    [".git", "node_modules", ".cache", "__pycache__", ".venv", "nix"],
)
def test_excluded_names(name: str) -> None:
    assert is_excluded_name(name)
    assert name in DEFAULT_EXCLUDED_NAMES
    assert not is_excluded_name("Downloads")


@pytest.mark.parametrize(
    "path",
    ["/proc/1", "/sys/class", "/dev/null", "/nix/store/abc", "/run/user"],
)
def test_excluded_paths(path: str) -> None:
    assert is_excluded_path(path)
    assert not is_excluded_path("/home/user/Documents")


def test_scanner_skips_system_and_vcs_directories(tree: Path) -> None:
    scanner = DiskScanner(workers=4)
    found = scanner.scan([tree])
    names = {doc.name for doc in found}

    assert "CS2227 - AI and ML notes.pdf" in names
    assert "algorithms lecture.docx" in names
    assert "random_photo_2043.pdf" in names
    # Unsupported, hidden and excluded files must not surface.
    assert "readme.txt" not in names
    assert ".hidden.pdf" not in names
    assert "pack-1.pptx" not in names
    assert "doc.pdf" not in names
    assert "cached.pptx" not in names
    assert len(found) == 3


def test_scan_is_non_recursive_when_asked(tree: Path) -> None:
    scanner = DiskScanner(workers=2)
    found = scanner.scan([tree], recursive=False)
    # Only the immediate children of ``tree`` are documents; there are none.
    assert found == []


def test_max_depth_limits_the_walk(tree: Path) -> None:
    scanner = DiskScanner(workers=2)
    found = scanner.scan([tree], max_depth=1)
    names = {doc.name for doc in found}
    assert "CS2227 - AI and ML notes.pdf" in names
    assert "algorithms lecture.docx" in names
    # ``Documents/Semester 3`` is two levels down, so it is out of reach.
    assert "random_photo_2043.pdf" not in names


# --------------------------------------------------------------------------- #
# Confidence rating
# --------------------------------------------------------------------------- #
def test_rate_document_confident_on_explicit_code() -> None:
    rating = rate_document("CS2227 - AI and ML - Week 4.pdf")
    assert rating.subject == AI_LABEL
    assert rating.status == STATUS_CONFIDENT
    assert rating.confidence >= CONFIDENCE_THRESHOLD
    assert rating.confident is True


def test_rate_document_ambiguous_on_junk_name() -> None:
    rating = rate_document("random_photo_2043.pdf")
    assert rating.status == STATUS_AMBIGUOUS
    assert rating.confidence < CONFIDENCE_THRESHOLD


def test_keyword_scores_are_whole_word() -> None:
    taxonomy = get_subject_taxonomy()
    scores = keyword_scores("company handbook.pdf", taxonomy)
    # ``SQL`` must not match inside a longer word; no subject should score.
    assert max(scores.values()) == 0.0

    hit = keyword_scores("CS2227 machine learning notes.pdf", taxonomy)
    assert hit[AI_LABEL] > 0.0
    assert hit[AI_LABEL] == max(hit.values())


def test_rate_scores_empty_taxonomy_is_ambiguous() -> None:
    rating = rate_scores({})
    assert rating.status == STATUS_AMBIGUOUS
    assert rating.subject == ""


def test_rate_scores_respects_thresholds() -> None:
    scores = {label: 0.0 for label in subject_labels()}
    scores[AI_LABEL] = 2.0
    strict = rate_scores(scores, threshold=0.95)
    assert strict.status == STATUS_AMBIGUOUS
    relaxed = rate_scores(scores, threshold=0.50)
    assert relaxed.status == STATUS_CONFIDENT


def test_normalise_token_collapses_separators() -> None:
    assert normalise_token("CS2227_-_AI/ML.pdf") == "cs2227 ai ml pdf"


# --------------------------------------------------------------------------- #
# Progress + cancellation
# --------------------------------------------------------------------------- #
def test_scan_reports_progress_and_completion(tree: Path) -> None:
    updates: list[ScanProgress] = []
    scanner = DiskScanner(workers=3, progress_interval=0.0)
    found = scanner.scan([tree], on_progress=updates.append)

    assert found, "the scan should have returned documents"
    assert updates, "progress should have been streamed"
    final = updates[-1]
    assert final.done is True
    assert final.cancelled is False
    assert final.documents == len(found)
    assert final.directories >= 1
    assert final.files_seen >= final.documents
    assert final.elapsed >= 0.0


def test_scan_can_be_cancelled(tmp_path: Path) -> None:
    root = tmp_path / "big"
    for index in range(160):
        folder = root / f"dir{index:03d}"
        folder.mkdir(parents=True)
        (folder / f"CS2227 notes {index}.pdf").write_bytes(b"%PDF-1.4")

    cancel = threading.Event()
    scanner = DiskScanner(workers=2, progress_interval=0.0)

    def cancel_soon() -> None:
        time.sleep(0.02)
        cancel.set()

    killer = threading.Thread(target=cancel_soon, daemon=True)
    killer.start()
    started = time.monotonic()
    found = scanner.scan([root], cancel=cancel, on_progress=lambda _p: None)
    killer.join(timeout=1.0)

    assert cancel.is_set()
    assert time.monotonic() - started < 10.0
    assert len(found) < 160


def test_scan_missing_root_returns_empty(tmp_path: Path) -> None:
    updates: list[ScanProgress] = []
    scanner = DiskScanner()
    assert scanner.scan([tmp_path / "ghost"], on_progress=updates.append) == []
    assert updates and updates[-1].done is True


def test_default_workers_is_multi_threaded() -> None:
    assert default_workers() >= 2


def test_workers_are_actually_used(tree: Path) -> None:
    """A scanner configured with several workers still produces a correct set."""
    scanner = DiskScanner(workers=4)
    assert scanner.workers == 4
    found = scanner.scan([tree])
    assert {doc.file_type for doc in found} == {"pdf", "docx"}


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #
def test_preset_targets_only_returns_existing_folders(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Documents").mkdir(parents=True)
    targets = preset_targets(home)
    labels = {label for label, _ in targets}
    assert "Downloads" in labels
    assert "Documents" in labels
    assert "Desktop" not in labels
    assert all(Path(path).is_dir() for _, path in targets)


def test_scanned_document_to_dict(tree: Path) -> None:
    found = DiskScanner(workers=2).scan([tree])
    payload = found[0].to_dict()
    for key in (
        "path", "name", "file_type", "size", "size_human",
        "modified", "subject", "confidence", "entropy", "status",
    ):
        assert key in payload
