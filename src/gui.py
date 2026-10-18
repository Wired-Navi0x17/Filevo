#!/usr/bin/env python3
"""Sortwise desktop launcher.

Boots the local FastAPI router on loopback and opens it in a native desktop
window via :mod:`webview` (pywebview).  When no display backend or no pywebview
build is available it degrades gracefully to the user's default browser, so the
UI is always reachable.

Usage
-----
    python src/gui.py                 # native window (falls back to browser)
    python src/gui.py --browser       # force the browser
    python src/gui.py --port 8800
    python src/gui.py --config ~/.config/sortwise/config.json

The server binds ``127.0.0.1`` only; nothing is exposed to the network.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
WINDOW_TITLE = "Sortwise - Calibrated Document Router"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 840


# --------------------------------------------------------------------------- #
# Port helpers
# --------------------------------------------------------------------------- #
def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def pick_port(host: str, preferred: int, tries: int = 20) -> int:
    """Return ``preferred`` when free, otherwise the next available port."""
    for offset in range(tries):
        candidate = preferred + offset
        if port_is_free(host, candidate):
            return candidate
    raise SystemExit(
        f"Error: no free port in {preferred}-{preferred + tries - 1} on {host}."
    )


def has_display() -> bool:
    if sys.platform in ("darwin", "win32"):
        return True
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def wait_for_server(url: str, timeout: float = 45.0) -> bool:
    """Poll ``url`` until the server answers or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    return False


# --------------------------------------------------------------------------- #
# Server thread
# --------------------------------------------------------------------------- #
class LocalServer:
    """Runs uvicorn in a daemon thread and stops it cleanly."""

    def __init__(self, host: str, port: int, config_path: str | None, ledger_path: str | None) -> None:
        import uvicorn

        from src.server import create_app

        app = create_app(config_path=config_path, ledger_path=ledger_path)
        self._config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(self._config)
        self._thread = threading.Thread(target=self._server.run, name="sortwise-uvicorn", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread.is_alive():
            self._thread.join(timeout=6)


# --------------------------------------------------------------------------- #
# Front ends
# --------------------------------------------------------------------------- #
def open_native_window(url: str) -> bool:
    """Open a pywebview window. Returns False when the backend is unusable."""
    try:
        import webview  # pywebview
    except Exception as exc:  # noqa: BLE001 - any import failure means fall back
        print(f"[sortwise] pywebview unavailable ({exc}); using the browser.", file=sys.stderr)
        return False

    if not has_display():
        print("[sortwise] no DISPLAY/WAYLAND_DISPLAY; using the browser.", file=sys.stderr)
        return False

    try:
        webview.create_window(
            WINDOW_TITLE,
            url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(900, 640),
            background_color="#121316",
        )
        webview.start()
        return True
    except Exception as exc:  # noqa: BLE001 - missing GTK/Qt bindings land here
        print(f"[sortwise] could not open a native window ({exc}); using the browser.", file=sys.stderr)
        return False


def open_browser_window(url: str) -> None:
    """Fall back to a browser, preferring a chromeless app window.

    ``pywebview`` needs a native backend (PyGObject + WebKitGTK, or Qt) that is
    not always present in a virtualenv. When it is missing we still want the UI
    to feel like an application, so we look for a Chromium-family browser and
    open it in ``--app`` mode (no tabs, no URL bar). Otherwise the default
    browser is used.
    """
    import shutil
    import subprocess

    browser_candidates = (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "brave-browser",
        "brave",
        "microsoft-edge",
        "microsoft-edge-stable",
        "vivaldi",
    )
    # Try Chromium family first with --app
    for name in browser_candidates:
        binary = shutil.which(name)
        if not binary:
            continue
        try:
            process = subprocess.Popen(
                [binary, f"--app={url}", "--new-window", "--class=Sortwise"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[sortwise] opened {name} in dedicated app window: {url}", file=sys.stderr)
            try:
                process.wait()
            except KeyboardInterrupt:
                pass
            return
        except OSError as exc:
            print(f"[sortwise] could not launch {name}: {exc}", file=sys.stderr)

    # Dedicated Firefox local app window with hidden chrome
    ff_bin = shutil.which("firefox")
    if ff_bin:
        profile_dir = Path.home() / ".cache" / "sortwise" / "firefox_profile"
        chrome_dir = profile_dir / "chrome"
        chrome_dir.mkdir(parents=True, exist_ok=True)
        css_file = chrome_dir / "userChrome.css"
        css_file.write_text(
            "#TabsToolbar { visibility: collapse !important; }\n"
            "#nav-bar { visibility: collapse !important; }\n"
            "#PersonalToolbar { visibility: collapse !important; }\n",
            encoding="utf-8"
        )
        prefs_file = profile_dir / "user.js"
        prefs_file.write_text(
            'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);\n'
            'user_pref("browser.shell.checkDefaultBrowser", false);\n'
            'user_pref("browser.tabs.warnOnClose", false);\n',
            encoding="utf-8"
        )
        try:
            cmd = [
                ff_bin,
                "--profile", str(profile_dir),
                "--new-instance",
                "--class", "Sortwise",
                "--name", "Sortwise",
                url
            ]
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[sortwise] opened dedicated desktop window: {url}", file=sys.stderr)
            try:
                process.wait()
            except KeyboardInterrupt:
                pass
            return
        except OSError as exc:
            print(f"[sortwise] could not launch firefox app window: {exc}", file=sys.stderr)

    print(f"[sortwise] UI available at {url}", file=sys.stderr)
    webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[sortwise] shutting down.", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sortwise",
        description="Sortwise - calibrated document router desktop UI.",
    )
    parser.add_argument("--host", default=os.environ.get("SORTWISE_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SORTWISE_PORT", DEFAULT_PORT)),
    )
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--ledger", default=None, help="Path to history.json")
    parser.add_argument("--browser", action="store_true", help="Force the browser instead of a native window")
    parser.add_argument("--no-window", action="store_true", help="Alias for --browser")
    parser.add_argument("--print-url", action="store_true", help="Print the URL and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not (args.browser or args.no_window or args.print_url):
        from src.native_app import main as native_main

        return native_main(argv)

    host = args.host
    port = pick_port(host, args.port)
    url = f"http://{host}:{port}"

    if args.print_url:
        print(url)
        return 0

    if args.config:
        os.environ.setdefault("SORTWISE_CONFIG_PATH", str(Path(args.config).expanduser()))
    if args.ledger:
        os.environ.setdefault("SORTWISE_LEDGER_PATH", str(Path(args.ledger).expanduser()))

    server = LocalServer(host, port, args.config, args.ledger)
    server.start()

    if not wait_for_server(f"{url}/api/health"):
        print(f"[sortwise] server did not come up on {url}", file=sys.stderr)
        server.stop()
        return 1

    print(f"[sortwise] serving {url}", file=sys.stderr)

    try:
        if args.browser or args.no_window:
            open_browser_window(url)
        elif not open_native_window(url):
            open_browser_window(url)
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
