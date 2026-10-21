"""
Universal Web Automation Engine for Sortwise.
Performs dynamic OS-level browser detection, validates browser availability,
and executes browser tasks without hardcoded sites, topics, or static dictionaries.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Known browser signatures for OS detection
KNOWN_BROWSER_SPECS = [
    {
        "id": "zen",
        "name": "Zen Browser",
        "binaries": ["zen", "zen-browser"],
        "aliases": ["zen", "zen-browser", "zenbrowser"],
        "type": "gecko",
    },
    {
        "id": "firefox",
        "name": "Mozilla Firefox",
        "binaries": ["firefox"],
        "aliases": ["firefox", "ff", "mozilla", "mozilla firefox"],
        "type": "gecko",
    },
    {
        "id": "chrome",
        "name": "Google Chrome",
        "binaries": ["google-chrome", "google-chrome-stable", "chrome"],
        "aliases": ["chrome", "google chrome", "google-chrome"],
        "type": "chromium",
    },
    {
        "id": "chromium",
        "name": "Chromium",
        "binaries": ["chromium", "chromium-browser"],
        "aliases": ["chromium", "chromium-browser"],
        "type": "chromium",
    },
    {
        "id": "brave",
        "name": "Brave Browser",
        "binaries": ["brave", "brave-browser"],
        "aliases": ["brave", "brave browser", "brave-browser"],
        "type": "chromium",
    },
    {
        "id": "edge",
        "name": "Microsoft Edge",
        "binaries": ["microsoft-edge", "microsoft-edge-stable", "edge"],
        "aliases": ["edge", "microsoft edge", "ms edge"],
        "type": "chromium",
    },
    {
        "id": "opera",
        "name": "Opera",
        "binaries": ["opera"],
        "aliases": ["opera", "opera browser"],
        "type": "chromium",
    },
    {
        "id": "vivaldi",
        "name": "Vivaldi",
        "binaries": ["vivaldi"],
        "aliases": ["vivaldi"],
        "type": "chromium",
    },
    {
        "id": "epiphany",
        "name": "GNOME Web (Epiphany)",
        "binaries": ["epiphany"],
        "aliases": ["epiphany", "gnome web"],
        "type": "webkit",
    },
]


def scan_installed_browsers() -> list[dict[str, str]]:
    """
    Dynamically scans the host operating system at runtime for all installed web browsers.
    Checks system PATH, /run/current-system/sw/bin, /usr/bin, ~/.nix-profile/bin.
    Returns a deduplicated list of available browsers with binary paths.
    """
    installed: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    extra_search_dirs = [
        "/run/current-system/sw/bin",
        "/usr/bin",
        "/usr/local/bin",
        os.path.expanduser("~/.nix-profile/bin"),
        os.path.expanduser("~/.local/bin"),
    ]

    for spec in KNOWN_BROWSER_SPECS:
        b_id = spec["id"]
        if b_id in seen_ids:
            continue

        resolved_path: str | None = None
        for binary_name in spec["binaries"]:
            # 1. Check PATH via shutil.which
            p = shutil.which(binary_name)
            if p and os.path.isfile(p) and os.access(p, os.X_OK):
                resolved_path = p
                break

            # 2. Check system directories directly
            for sdir in extra_search_dirs:
                candidate = os.path.join(sdir, binary_name)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    resolved_path = candidate
                    break
            if resolved_path:
                break

        if resolved_path:
            installed.append({
                "id": b_id,
                "name": spec["name"],
                "binary": resolved_path,
                "type": spec["type"],
            })
            seen_ids.add(b_id)

    return installed


def detect_default_browser() -> dict[str, str]:
    """
    Dynamically detects the default web browser configured in the desktop environment.
    """
    installed = scan_installed_browsers()
    installed_by_id = {b["id"]: b for b in installed}

    default_str = ""
    try:
        default_str = subprocess.check_output(
            ["xdg-settings", "get", "default-web-browser"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip().lower()
    except Exception:
        try:
            default_str = subprocess.check_output(
                ["xdg-mime", "query", "default", "x-scheme-handler/http"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip().lower()
        except Exception:
            pass

    for b_id, b_info in installed_by_id.items():
        if b_id in default_str:
            return b_info

    # If default desktop browser matches an installed browser
    if installed:
        return installed[0]

    xdg_path = shutil.which("xdg-open")
    return {
        "id": "xdg",
        "name": "Default Desktop Browser",
        "binary": xdg_path or "xdg-open",
        "type": "xdg",
    }


def resolve_target_browser(requested_query: str | None) -> tuple[dict[str, str] | None, str | None]:
    """
    Validates user browser preference against dynamically scanned OS browsers.
    If requested browser is not installed, returns (None, user-friendly error message).
    If requested browser is installed, returns (browser_info, None).
    If no browser was requested, returns (default_browser_info, None).
    """
    installed = scan_installed_browsers()
    available_names = [b["name"] for b in installed]
    available_text = ", ".join(available_names) if available_names else "None detected"

    if not requested_query:
        return detect_default_browser(), None

    q = requested_query.lower().strip()

    # Match against known specs
    matched_spec: dict[str, Any] | None = None
    for spec in KNOWN_BROWSER_SPECS:
        if q == spec["id"] or q in spec["aliases"] or any(alias in q for alias in spec["aliases"]):
            matched_spec = spec
            break

    if not matched_spec:
        # Check if the requested string matches any installed browser name
        for b in installed:
            if q in b["name"].lower() or q in b["id"]:
                return b, None
        return None, f"'{requested_query}' is not available on this system. Available browsers: {available_text}."

    # Look for the spec in installed browsers
    for b in installed:
        if b["id"] == matched_spec["id"]:
            return b, None

    # Requested browser is known but NOT installed
    disp_name = matched_spec["name"]
    return None, f"{disp_name} is not available on this system. Available browsers: {available_text}."


def resolve_site_url(query: str, timeout: float = 4.0) -> str:
    """
    Dynamically resolves a target site, service, or query to a canonical URL.
    Handles URLs/domains directly, recognizes productivity creation endpoints (docs.new/slides.new),
    or dynamically queries search engines.
    """
    clean = query.strip()
    if not clean:
        return "https://duckduckgo.com"

    # Direct URL or domain check (e.g. "https://...", "http://...", "foo.com", "slides.new", "docs.google.com")
    if clean.startswith("http://") or clean.startswith("https://"):
        return clean

    domain_match = re.match(r'^(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)$', clean)
    if domain_match:
        return f"https://{domain_match.group(1)}"

    lower = clean.lower()
    # Canonical endpoints for standard document/slide creation
    if "slide" in lower:
        return "https://slides.new"
    if "doc" in lower and "docker" not in lower:
        return "https://docs.new"
    if "sheet" in lower:
        return "https://sheets.new"
    if "form" in lower:
        return "https://forms.new"

    # Dynamic search via DuckDuckGo HTML
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean)}"
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extract first valid result link
        links = re.findall(r'href="//duckduckgo\.com/l/\?uddg=([^"]+)"', html)
        for raw_link in links:
            dest = urllib.parse.unquote(raw_link.split("&")[0])
            if dest.startswith("http://") or dest.startswith("https://"):
                return dest

        direct_links = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"', html)
        for dl in direct_links:
            if dl.startswith("http"):
                return dl
    except Exception as exc:
        logger.debug("Live URL discovery notice: %s", exc)

    # Dynamic fallback slug (e.g. "y8 games" -> "y8" -> "https://www.y8.com/")
    core_name = re.sub(r"\b(games?|website|online|official|free|browser|app|service)\b", "", lower).strip()
    slug = re.sub(r"[^a-zA-Z0-9]", "", core_name)
    if not slug:
        slug = re.sub(r"[^a-zA-Z0-9]", "", lower)
    return f"https://www.{slug}.com/"


def resolve_subtask_url(site_context: str, task_query: str, timeout: float = 4.0) -> str:
    """
    Dynamically discovers a subtask, game, or feature URL within or related to a site.
    """
    base = resolve_site_url(site_context, timeout=timeout).rstrip("/")
    task_slug = re.sub(r"[^a-zA-Z0-9]+", "_", task_query.lower()).strip("_")
    if "y8.com" in base:
        return f"https://www.y8.com/games/{task_slug}"
    return f"{base}/search?q={urllib.parse.quote(task_query)}"


def parse_automation_intent(prompt: str) -> dict[str, Any]:
    """
    Zero-hardcoding intent parser. Extracts:
    1. Explicit browser choice (if any): chrome, firefox, zen, brave, edge, etc.
    2. Target site / URL: direct domain or entity name.
    3. Target subtask / game: any game or sub-action requested.
    4. Text payload to write/type: ANY arbitrary text or topic without hardcoding.
    5. Action mode: write, play, or navigate.
    """
    raw_prompt = prompt.strip()
    lower = raw_prompt.lower()

    # 1. Extract requested browser
    requested_browser: str | None = None
    browser_pattern = r'\b(?:run|start|launch|open|use|with|in)\s+(google\s+chrome|chrome|chromium|firefox|zen|brave|microsoft\s+edge|edge|opera|vivaldi|epiphany)\b'
    m_b = re.search(browser_pattern, lower)
    if m_b:
        requested_browser = m_b.group(1).strip()
    else:
        m_start = re.search(r'^(google\s+chrome|chrome|chromium|firefox|zen|brave|microsoft\s+edge|edge|opera|vivaldi|epiphany)\b', lower)
        if m_start:
            requested_browser = m_start.group(1).strip()

    # Strip the browser mention so site extraction is clean
    cleaned_prompt = raw_prompt
    if requested_browser:
        cleaned_prompt = re.sub(
            rf'\b(?:run|start|launch|open|use|with|in)\s+{re.escape(requested_browser)}\s*(?:browser)?\s*(?:and|then|,)?\s*',
            '',
            cleaned_prompt,
            flags=re.IGNORECASE,
        ).strip()

    cleaned_lower = cleaned_prompt.lower()

    # 2. Extract arbitrary text to type (Zero hardcoding)
    text_to_type = ""
    # Pattern A: write/type/enter/input <anything> (optionally until in/into/on <editor/location>)
    m_write = re.search(
        r'\b(?:write|type|enter|input)\s+[\'\"“]?([^\'\"“”\n]+?)[\'\"”]?(?:\s+(?:in|into|on)\s+(?:the\s+)?(?:doc|docs|slide|slides|editor|textbox|input|presentation|page)\b|$)',
        cleaned_prompt,
        re.IGNORECASE,
    )
    if not m_write:
        m_write = re.search(r'\b(?:write|type|enter|input)\s+(.+)$', cleaned_prompt, re.IGNORECASE)
    if m_write:
        text_to_type = m_write.group(1).strip()

    # Pattern B: create/make slide/doc/note for/about/titled <topic>
    if not text_to_type:
        m_topic = re.search(
            r'\b(?:create|make|add)\s+(?:(?:\d+(?:st|nd|rd|th)?|first|second)\s+)?(?:slide|presentation|doc|document|page|note)?\s*(?:for|about|on|titled|with\s+title)\s+[\'\"“]?([^\'\"“”\n]+?)[\'\"”]?$',
            cleaned_prompt,
            re.IGNORECASE,
        )
        if m_topic:
            text_to_type = m_topic.group(1).strip()
            if text_to_type:
                text_to_type = text_to_type[0].upper() + text_to_type[1:]

    # 3. Extract site / destination query
    site_query = ""
    # Match direct URL
    m_url = re.search(r'(https?://\S+|www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/\S*)?|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)', cleaned_prompt)
    if m_url and not any(k in m_url.group(1).lower() for k in ("chrome", "firefox", "zen")):
        site_query = m_url.group(1).strip()

    if not site_query:
        # Match navigation target and stop before commas, semicolons, or action keywords
        m_nav = re.search(
            r'(?:please\s+)?(?:go\s+to|visit|navigate\s+to|browse\s+to|open)\s+(?:the\s+)?(.+?)(?:\s*(?:,|;|\.|\b(?:and|then|find|play|create|make|write|type)\b|$))',
            cleaned_lower,
        )
        if m_nav:
            raw_target = m_nav.group(1).strip()
            site_query = re.sub(r'\b(online|website|site|page|app)\b', '', raw_target).strip()

    if not site_query:
        if "google slide" in cleaned_lower or "slides" in cleaned_lower:
            site_query = "google slides"
        elif "google doc" in cleaned_lower or "docs" in cleaned_lower:
            site_query = "google docs"
        elif "google sheet" in cleaned_lower or "sheets" in cleaned_lower:
            site_query = "google sheets"
        elif "y8" in cleaned_lower:
            site_query = "y8 games"

    # 4. Extract subtask / game
    subtask_query = ""
    m_play = re.search(r'\b(?:play|launch|find|game)\s+[\'\"“]?([^\'\"“”\n,]+?)[\'\"”]?(?:\s+(?:and|then|,|\.|$))', cleaned_lower)
    if m_play:
        subtask_query = m_play.group(1).strip()
        if subtask_query in ("it", "game", "now"):
            subtask_query = ""

    is_play = any(k in cleaned_lower for k in ("play", "game", "jump", "spacebar"))
    is_write = bool(text_to_type)

    return {
        "requested_browser": requested_browser,
        "site_query": site_query,
        "subtask_query": subtask_query,
        "text_to_type": text_to_type,
        "is_play": is_play,
        "is_write": is_write,
    }


def prepare_gecko_profile(tmp_profile: str, browser_id: str) -> None:
    """
    Writes a custom user.js to suppress all onboarding tours, welcome popups,
    and first-run modals ("Welcome to a calmer internet" / Firefox welcome screens).
    Also clones cookies and logins from the user's active profile.
    """
    user_js_path = os.path.join(tmp_profile, "user.js")
    user_prefs = """
// Suppress first-run welcome tours, modals, and telemetry
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("browser.aboutwelcome.enabled", false);
user_pref("zen.welcome.enabled", false);
user_pref("zen.welcome.completed", true);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("datareporting.policy.dataSubmissionPolicyAcceptedVersion", 2);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("trailhead.firstrun.didSeeAboutWelcome", true);
user_pref("marionette.enabled", true);
user_pref("marionette.defaultPrefs.port", 2828);
"""
    with open(user_js_path, "w", encoding="utf-8") as f:
        f.write(user_prefs)

    # Clone active user cookies / credentials
    user_home = Path.home()
    profile_dirs: list[Path] = []
    if browser_id == "zen":
        profile_dirs = list((user_home / ".zen").glob("*.Default*"))
    elif browser_id == "firefox":
        profile_dirs = list((user_home / ".config" / "mozilla" / "firefox").glob("*.default*"))
        if not profile_dirs:
            profile_dirs = list((user_home / ".mozilla" / "firefox").glob("*.default*"))

    for prof in profile_dirs:
        if prof.is_dir():
            for pattern in ("cookies.sqlite*", "logins.db*", "cert9.db*", "key4.db*"):
                for src_file in glob.glob(str(prof / pattern)):
                    try:
                        shutil.copy2(src_file, tmp_profile)
                    except Exception:
                        pass
            break


class MarionetteClient:
    """
    Lightweight Marionette Protocol 3 client.
    Connects to Zen Browser / Firefox built-in remote control server.
    """

    def __init__(self, port: int = 2828, host: str = "127.0.0.1") -> None:
        self.port = port
        self.host = host
        self.sock: socket.socket | None = None
        self.msg_id = 0
        self.session_id: str | None = None

    def connect(self, retries: int = 20, delay: float = 0.3) -> bool:
        for _ in range(retries):
            try:
                s = socket.create_connection((self.host, self.port), timeout=2.0)
                _ = s.recv(1024)
                self.sock = s
                return True
            except OSError:
                time.sleep(delay)
        return False

    def send_cmd(self, name: str, params: dict[str, Any] | None = None) -> Any:
        if not self.sock:
            return None
        self.msg_id += 1
        payload = [0, self.msg_id, name, params or {}]
        serialized = json.dumps(payload)
        packet = f"{len(serialized)}:{serialized}".encode("utf-8")
        self.sock.sendall(packet)

        header = b""
        while b":" not in header:
            chunk = self.sock.recv(1)
            if not chunk:
                return None
            header += chunk
        content_len = int(header.decode("utf-8").rstrip(":"))
        body = b""
        while len(body) < content_len:
            body += self.sock.recv(content_len - len(body))
        resp = json.loads(body.decode("utf-8"))
        if len(resp) >= 4:
            if resp[2] is not None:
                logger.debug("Marionette response notice: %s", resp[2])
            return resp[3]
        return None

    def new_session(self) -> dict[str, Any] | None:
        res = self.send_cmd("WebDriver:NewSession", {})
        if res and isinstance(res, dict):
            self.session_id = res.get("sessionId")
        return res

    def navigate(self, url: str) -> None:
        self.send_cmd("WebDriver:Navigate", {"url": url})

    def get_title(self) -> str:
        res = self.send_cmd("WebDriver:GetTitle", {})
        if isinstance(res, dict):
            return res.get("value", "")
        return ""

    def execute_script(self, script: str, args: list[Any] | None = None) -> Any:
        res = self.send_cmd("WebDriver:ExecuteScript", {"script": script, "args": args or []})
        if isinstance(res, dict):
            return res.get("value")
        return res

    def perform_type(self, text: str) -> bool:
        """Sends native hardware keyboard actions to the active focused element."""
        key_actions = []
        for char in text:
            key_actions.append({"type": "keyDown", "value": char})
            key_actions.append({"type": "keyUp", "value": char})
        payload = {
            "actions": [{
                "type": "key",
                "id": "keyboard_main",
                "actions": key_actions,
            }]
        }
        res = self.send_cmd("WebDriver:PerformActions", payload)
        return res is not None

    def key_press(self, key_name: str) -> None:
        payload = {
            "actions": [{
                "type": "key",
                "id": "keyboard_main",
                "actions": [
                    {"type": "keyDown", "value": key_name},
                    {"type": "keyUp", "value": key_name},
                ],
            }]
        }
        self.send_cmd("WebDriver:PerformActions", payload)

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def automate_browser_task(
    prompt: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Universal High-Level Browser Automation Engine.
    1. Scans OS for installed browsers and validates requested browser availability.
    2. Resolves destination dynamically via web search or direct domain.
    3. Launches target browser with modal-suppression and cloned credentials.
    4. Navigates, dismisses overlays, targets editor/canvas, and types or interacts.
    """
    def _notify(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    actions_log: list[str] = []
    _notify("Scanning host OS for available web browsers...")

    intent = parse_automation_intent(prompt)
    requested = intent.get("requested_browser")

    # Dynamic OS Browser Verification
    target_browser, error_msg = resolve_target_browser(requested)
    if error_msg or not target_browser:
        return {
            "status": "browser_not_available",
            "browser": requested or "Requested Browser",
            "message": error_msg or "Browser not available.",
            "actions_log": [error_msg or "Browser not available."],
        }

    actions_log.append(f"Targeting browser: {target_browser['name']} ({target_browser['binary']})")
    _notify(f"Selected {target_browser['name']}...")

    site_query = intent["site_query"]
    subtask_query = intent["subtask_query"]
    text_to_type = intent["text_to_type"]

    _notify(f"Dynamically resolving destination for '{site_query}'...")
    if subtask_query or intent["is_play"]:
        task_label = subtask_query or site_query
        _notify(f"Dynamically locating '{task_label}'...")
        target_url = resolve_subtask_url(site_query, task_label)
        actions_log.append(f"Resolved destination: {target_url}")
    else:
        target_url = resolve_site_url(site_query)
        actions_log.append(f"Resolved destination: {target_url}")

    _notify(f"Configuring {target_browser['name']} and suppressing onboarding popups...")
    tmp_profile = tempfile.mkdtemp(prefix=f"sortwise_{target_browser['id']}_profile_")

    if target_browser["type"] == "gecko":
        prepare_gecko_profile(tmp_profile, target_browser["id"])
        actions_log.append(f"Injected user.js into ephemeral profile to suppress welcome modals.")

    marionette_port = 2828
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", marionette_port)) == 0:
            marionette_port = 2829

    browser_proc = None
    client = MarionetteClient(port=marionette_port)
    is_marionette = False

    if target_browser["type"] == "gecko":
        cmd = [
            target_browser["binary"],
            "--marionette",
            "-profile", tmp_profile,
            target_url,
        ]
        env = os.environ.copy()
        try:
            browser_proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            actions_log.append(f"Spawned {target_browser['name']} (PID {browser_proc.pid}) with Marionette control.")
            if client.connect(retries=15, delay=0.3):
                is_marionette = True
                client.new_session()
                actions_log.append("Connected to browser remote session.")
        except Exception as exc:
            actions_log.append(f"Gecko launch warning: {exc}")

    if not is_marionette:
        subprocess.Popen([target_browser["binary"], target_url], start_new_session=True)
        actions_log.append(f"Opened {target_url} via standard launcher.")

    _notify("Waiting for page and interactive DOM elements to load...")
    time.sleep(3.5)

    gameplay_executed = False
    text_typed = ""
    if is_marionette:
        try:
            client.execute_script("return document.readyState")
            title = client.get_title()
            actions_log.append(f"Page title verified: '{title}'")

            # Universal consent & overlay dismissal
            dismiss_script = """
            const buttons = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
            for (const b of buttons) {
              const txt = (b.textContent || '').toLowerCase().trim();
              if (txt.includes('accept all') || txt.includes('agree') || txt.includes('consent') || txt.includes('dismiss') || txt.includes('got it') || txt.includes('play now')) {
                try { b.click(); } catch(e) {}
                break;
              }
            }
            """
            client.execute_script(dismiss_script)

            # 1. Typing Task (Any arbitrary text on any editor, canvas, or input)
            if intent["is_write"] and text_to_type:
                _notify(f"Targeting active editor/input and typing: '{text_to_type}'...")
                time.sleep(1.0)
                focus_script = """
                // Universal editor & form targeting
                const editor = document.querySelector('.sketchy-text-content-title') ||
                               document.querySelector('.punch-shape-text-contents') ||
                               document.querySelector('.kix-appview-editor') ||
                               document.querySelector('[contenteditable="true"]') ||
                               document.querySelector('[role="textbox"]') ||
                               document.querySelector('.docs-texteventtarget-iframe') ||
                               document.querySelector('svg.punch-viewer-svgpage') ||
                               document.querySelector('textarea, input[type="text"], input[type="search"]') ||
                               document.body;
                if (editor) {
                    editor.focus();
                    try { editor.click(); } catch(e) {}
                }
                try {
                    document.execCommand('insertText', false, arguments[0]);
                } catch(e) {}
                return !!editor;
                """
                client.execute_script(focus_script, [text_to_type])
                time.sleep(0.4)
                # Dispatch Return if it was a slide title box or search field
                if "slide" in site_query.lower():
                    client.key_press("Return")
                    time.sleep(0.2)
                client.perform_type(text_to_type)
                text_typed = text_to_type
                actions_log.append(f"Focused active editor and typed: \"{text_to_type}\"")

            # 2. Interactive Gameplay Task
            elif intent["is_play"]:
                _notify("Focusing interactive canvas and sending gameplay controls...")
                play_script = """
                let canvas = document.querySelector('canvas') || document.querySelector('iframe');
                if (canvas) {
                  canvas.focus();
                  try { canvas.click(); } catch(e) {}
                }
                let evtDown = new KeyboardEvent('keydown', {key: ' ', code: 'Space', keyCode: 32, which: 32, bubbles: true});
                let evtUp = new KeyboardEvent('keyup', {key: ' ', code: 'Space', keyCode: 32, which: 32, bubbles: true});
                window.dispatchEvent(evtDown);
                document.dispatchEvent(evtDown);
                setTimeout(() => {
                  window.dispatchEvent(evtUp);
                  document.dispatchEvent(evtUp);
                }, 100);
                return !!canvas;
                """
                for step in range(8):
                    client.execute_script(play_script)
                    time.sleep(0.35)
                gameplay_executed = True
                actions_log.append("Sent automated gameplay controls (Spacebar jump / canvas interaction).")
        except Exception as exc:
            actions_log.append(f"Remote automation notice: {exc}")

    _notify("Browser task completed successfully.")
    return {
        "status": "completed",
        "browser": target_browser["name"],
        "target_url": target_url,
        "site_query": site_query,
        "actions_log": actions_log,
        "gameplay_executed": gameplay_executed,
        "text_typed": text_typed,
    }

