"""Single switch for every outbound network request Filevo makes.

Webfetch is OFF by default. When it is off, Filevo works only from the local
database (``~/.filevo/corpus/corpus.db``) and never opens a socket to the
internet. Every code path that can reach the network calls
``require_webfetch()`` first, so there is exactly one place to reason about.

Resolution order:
1. ``FILEVO_WEBFETCH`` environment variable (``1/on/true`` or ``0/off/false``)
2. ``"webfetch"`` key in ``~/.filevo/config.json``
3. ``False``

The config file is re-read on every call, so a toggle made from the CLI or the
TUI is seen immediately by a running daemon.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ENV_VAR = "FILEVO_WEBFETCH"
CONFIG_KEY = "webfetch"

_TRUE = {"1", "on", "true", "yes", "enable", "enabled"}
_FALSE = {"0", "off", "false", "no", "disable", "disabled"}


class WebfetchDisabled(RuntimeError):
    """Raised when a network action is attempted while webfetch is off."""

    def __init__(self, action: str = "network access"):
        super().__init__(
            f"{action} needs the network, but webfetch is off. "
            f"Turn it on with: /settings webfetch on"
        )
        self.action = action


def _config_path() -> Path:
    return Path.home() / ".filevo" / "config.json"


def _read_config() -> dict:
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def parse_switch(value: str) -> bool | None:
    """Parse an on/off word. Returns None when the word is not a switch."""
    v = str(value).strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None


def webfetch_source() -> str:
    """Where the current value comes from: 'env', 'config' or 'default'."""
    if parse_switch(os.environ.get(ENV_VAR, "")) is not None:
        return "env"
    if CONFIG_KEY in _read_config():
        return "config"
    return "default"


def is_webfetch_enabled() -> bool:
    env = parse_switch(os.environ.get(ENV_VAR, ""))
    if env is not None:
        return env
    return bool(_read_config().get(CONFIG_KEY, False))


def set_webfetch(enabled: bool) -> bool:
    """Persist the toggle in config.json (other keys are preserved)."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = _read_config()
    cfg[CONFIG_KEY] = bool(enabled)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, path)
    return bool(enabled)


def require_webfetch(action: str = "network access") -> None:
    """Raise WebfetchDisabled unless webfetch is on."""
    if not is_webfetch_enabled():
        raise WebfetchDisabled(action)
