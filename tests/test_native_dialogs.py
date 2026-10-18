"""Tests for native KDE/portal file and folder pickers."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from unittest.mock import MagicMock, patch

import pytest

from src.native_app import (
    _find_kdialog_binary,
    _find_zenity_binary,
    native_choose_file,
    native_choose_folder,
)


def test_zenity_binary_finder() -> None:
    """Verify zenity or None is returned cleanly."""
    res = _find_zenity_binary()
    if res is not None:
        assert os.path.isfile(res)
        assert os.access(res, os.X_OK)


def test_native_choose_folder_cancel() -> None:
    """Verify that when the user cancels in the dialog, native_choose_folder returns None."""
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stdout = ""

    with patch("subprocess.run", return_value=mock_res):
        with patch("src.native_app._find_kdialog_binary", return_value="/bin/kdialog"):
            res = native_choose_folder(title="Test Choose", initial_dir=str(Path.home()))
            assert res is None


def test_native_choose_folder_success(tmp_path: Path) -> None:
    """Verify that when the user confirms a folder, the valid path is returned."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = f"{tmp_path}\n"

    with patch("subprocess.run", return_value=mock_res):
        with patch("src.native_app._find_zenity_binary", return_value="/bin/zenity"):
            with patch("src.native_app._find_kdialog_binary", return_value=None):
                res = native_choose_folder(title="Test Choose", initial_dir=str(Path.home()))
                assert res == str(tmp_path)


def test_native_choose_file_cancel() -> None:
    """Verify that when the user cancels file selection, native_choose_file returns None."""
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stdout = ""

    with patch("subprocess.run", return_value=mock_res):
        with patch("src.native_app._find_zenity_binary", return_value="/bin/zenity"):
            res = native_choose_file(title="Test Choose File", initial_dir=str(Path.home()))
            assert res is None


def test_native_choose_file_success(tmp_path: Path) -> None:
    """Verify that when the user selects a file, the path is returned."""
    test_file = tmp_path / "sample.pdf"
    test_file.write_text("dummy")

    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = f"{test_file}\n"

    with patch("subprocess.run", return_value=mock_res):
        with patch("src.native_app._find_zenity_binary", return_value="/bin/zenity"):
            with patch("src.native_app._find_kdialog_binary", return_value=None):
                res = native_choose_file(title="Test Choose File", initial_dir=str(tmp_path))
                assert res == str(test_file)
