"""Tests for SingleInstanceLock and fast empty folder handling."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.native_app import SingleInstanceLock
from src.scanner import DiskScanner


def test_single_instance_lock_lifecycle(tmp_path: Path) -> None:
    """Test primary lock acquisition, second instance blocking, and focus notification."""
    app_name = f"sortwise_test_{int(time.time())}"
    lock1 = SingleInstanceLock(app_name=app_name)
    lock2 = SingleInstanceLock(app_name=app_name)

    focused = threading.Event()

    def on_focus() -> None:
        focused.set()

    try:
        # First instance acquires successfully
        assert lock1.acquire(on_focus=on_focus) is True

        # Second instance should fail and notify first instance
        assert lock2.acquire() is False

        # First instance should have received the focus signal
        assert focused.wait(timeout=2.0) is True

    finally:
        lock1.release()
        lock2.release()


def test_disk_scanner_empty_folder(tmp_path: Path) -> None:
    """Verify that DiskScanner on an empty directory returns immediately."""
    empty_dir = tmp_path / "empty_folder"
    empty_dir.mkdir()

    scanner = DiskScanner()
    t0 = time.monotonic()
    docs = scanner.scan([str(empty_dir)])
    elapsed = time.monotonic() - t0

    assert docs == []
    # Must complete virtually instantaneously (under 0.5s)
    assert elapsed < 0.5


def test_disk_scanner_cancellation(tmp_path: Path) -> None:
    """Verify that cancel event stops DiskScanner immediately without deadlock."""
    test_dir = tmp_path / "cancel_test"
    test_dir.mkdir()
    for i in range(10):
        (test_dir / f"sub_{i}").mkdir()

    cancel = threading.Event()
    cancel.set()  # Cancelled before or immediately at start

    scanner = DiskScanner()
    t0 = time.monotonic()
    docs = scanner.scan([str(test_dir)], cancel=cancel)
    elapsed = time.monotonic() - t0

    assert docs == []
    assert elapsed < 0.5
