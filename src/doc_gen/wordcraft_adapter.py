"""WordCraft Model Context Protocol (MCP) Adapter for Filevo.

Provides an official, typed MCP client interface for controlling ArtCraft's WordCraft
over stdio JSON-RPC 2.0. Supports both live desktop composition via `--connect 127.0.0.1:7981`
and headless automated rendering via `wordcraft-cli mcp`.

Features:
- Full JSON-RPC 2.0 handshake (`initialize`, `notifications/initialized`)
- Dynamic tool discovery (`tools/list`) and schema inspection
- Robust tool execution (`tools/call`) with typed result parsing
- Desktop reachability probe with clear user startup guidance
- Graceful process management, timeouts, and cancellation
- Adherence to ~/.config/filevo/wordcraft.toml configuration
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

from src.doc_gen.antislop_policy import AntiSlopDials, AntiSlopPolicy, get_antislop_policy

logger = logging.getLogger("filevo.wordcraft.adapter")

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "filevo" / "wordcraft.toml"
FALLBACK_CONFIG_PATH = Path.home() / ".filevo" / "wordcraft.toml"


class WordCraftMCPError(Exception):
    """Raised when an MCP operation fails or returns an error."""
    pass


class WordCraftUnreachableError(WordCraftMCPError):
    """Raised when WordCraft desktop application is not running or unreachable."""
    pass


@dataclass
class WordCraftConfig:
    """Configuration options for WordCraft MCP integration."""

    enabled: bool = True
    control_address: str = "127.0.0.1:7981"
    mcp_executable: str = "wordcraft-cli"
    timeout_seconds: float = 30.0
    mode: str = "desktop"  # "desktop" | "headless"
    output_dir: Path = field(default_factory=lambda: Path.home() / ".filevo" / "output")
    auto_inspect: bool = True
    fallback_policy: str = "openxml"  # "openxml" | "fail"
    antislop: AntiSlopPolicy = field(default_factory=get_antislop_policy)

    @classmethod
    def load(cls, config_path: Path | None = None) -> WordCraftConfig:
        """Loads configuration from ~/.config/filevo/wordcraft.toml with defaults."""
        path = config_path or DEFAULT_CONFIG_PATH
        if not path.exists() and FALLBACK_CONFIG_PATH.exists():
            path = FALLBACK_CONFIG_PATH

        if not path.exists():
            # Return default config and write template
            cfg = cls()
            cfg.save(path)
            return cfg

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)

            wc_data = data.get("wordcraft", {})
            as_data = data.get("antislop", {})

            dials = AntiSlopDials(
                formality=int(as_data.get("formality", 6)),
                density=int(as_data.get("density", 5)),
                ornament=int(as_data.get("ornament", 2)),
            )

            antislop = AntiSlopPolicy(
                enabled=bool(as_data.get("enabled", True)),
                dials=dials,
                font_display=str(as_data.get("font_display", "Times New Roman")),
                font_body=str(as_data.get("font_body", "Times New Roman")),
                font_mono=str(as_data.get("font_mono", "Cascadia Code")),
                ban_cliches=bool(as_data.get("ban_cliches", True)),
                prose_default=bool(as_data.get("prose_default", True)),
                bluf_required=bool(as_data.get("bluf_required", True)),
                signature_element_required=bool(as_data.get("signature_element", True)),
            )

            out_dir_str = wc_data.get("output_dir", "~/.filevo/output")
            out_dir = Path(os.path.expanduser(out_dir_str))

            return cls(
                enabled=bool(wc_data.get("enabled", True)),
                control_address=str(wc_data.get("control_address", "127.0.0.1:7981")),
                mcp_executable=str(wc_data.get("mcp_executable", "wordcraft-cli")),
                timeout_seconds=float(wc_data.get("timeout_seconds", 30.0)),
                mode=str(wc_data.get("mode", "desktop")).lower(),
                output_dir=out_dir,
                auto_inspect=bool(wc_data.get("auto_inspect", True)),
                fallback_policy=str(wc_data.get("fallback_policy", "openxml")),
                antislop=antislop,
            )
        except Exception as e:
            logger.warning("Error parsing wordcraft.toml: %s; using defaults.", e)
            return cls()

    def save(self, config_path: Path | None = None) -> None:
        """Persists current configuration to file."""
        path = config_path or DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"""# ~/.config/filevo/wordcraft.toml
# Filevo WordCraft MCP Configuration

[wordcraft]
enabled = {str(self.enabled).lower()}
control_address = "{self.control_address}"
mcp_executable = "{self.mcp_executable}"
timeout_seconds = {self.timeout_seconds}
mode = "{self.mode}" # "desktop" (visible live word processor) or "headless" (background)
output_dir = "{self.output_dir}"
auto_inspect = {str(self.auto_inspect).lower()}
fallback_policy = "{self.fallback_policy}" # "openxml" (fallback to DocxRenderer) or "fail"

[antislop]
enabled = {str(self.antislop.enabled).lower()}
formality = {self.antislop.dials.formality}
density = {self.antislop.dials.density}
ornament = {self.antislop.dials.ornament}
ban_cliches = {str(self.antislop.ban_cliches).lower()}
prose_default = {str(self.antislop.prose_default).lower()}
bluf_required = {str(self.antislop.bluf_required).lower()}
signature_element = {str(self.antislop.signature_element_required).lower()}
font_display = "{self.antislop.font_display}"
font_body = "{self.antislop.font_body}"
font_mono = "{self.antislop.font_mono}"
"""
        path.write_text(content, encoding="utf-8")


@dataclass
class MCPImageContent:
    """Raster or vector image returned from an MCP tool."""

    mime_type: str
    data_base64: str

    @property
    def data_bytes(self) -> bytes:
        return base64.b64decode(self.data_base64)


@dataclass
class MCPToolResult:
    """Structured response from an MCP tool invocation."""

    text: str = ""
    json_data: Any = None
    images: list[MCPImageContent] = field(default_factory=list)
    is_error: bool = False
    raw_content: list[dict[str, Any]] = field(default_factory=list)


class WordCraftClient:
    """Official Model Context Protocol client for ArtCraft WordCraft."""

    def __init__(self, config: WordCraftConfig | None = None):
        self.config = config or WordCraftConfig.load()
        self._proc: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = threading.Lock()
        self.tools: dict[str, dict[str, Any]] = {}
        self.server_info: dict[str, Any] = {}
        self._is_connected = False

    @staticmethod
    def is_desktop_reachable(control_address: str = "127.0.0.1:7981", timeout: float = 0.5) -> bool:
        """Probes whether WordCraft desktop application is actively listening on control address."""
        try:
            parts = control_address.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 7981
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (socket.error, OSError, ValueError):
            return False

    def _resolve_executable(self) -> list[str]:
        """Resolves the wordcraft-cli command and any NixOS wrapper needed."""
        cli = self.config.mcp_executable

        # Search candidates
        candidates = [
            cli,
            "wordcraft-cli",
            str(Path.home() / ".local" / "bin" / "wordcraft-cli"),
            str(Path.home() / ".local" / "opt" / "wordcraft" / "usr" / "bin" / "wordcraft-cli"),
        ]

        resolved = None
        for c in candidates:
            if "/" in c:
                p = Path(c)
                if p.exists() and os.access(p, os.X_OK):
                    resolved = str(p)
                    break
            else:
                found = shutil.which(c)
                if found:
                    resolved = found
                    break

        if not resolved:
            raise FileNotFoundError(
                f"WordCraft CLI executable '{cli}' was not found in PATH or ~/.local/bin. "
                "Please verify WordCraft installation."
            )

        # Check if steam-run is required (unwrapped binary on NixOS)
        if "/nix/store" in os.environ.get("PATH", "") and not resolved.endswith(".sh"):
            sr = Path("/run/current-system/sw/bin/steam-run")
            if sr.exists() and "opt/wordcraft" in resolved:
                return [str(sr), resolved]

        return [resolved]

    def start(self, force_desktop: bool | None = None) -> None:
        """Starts the MCP bridge subprocess and performs JSON-RPC handshake."""
        with self._lock:
            if self._is_connected and self._proc and self._proc.poll() is None:
                return

            exec_cmd = self._resolve_executable()
            use_desktop = self.config.mode == "desktop" if force_desktop is None else force_desktop

            cmd = list(exec_cmd)
            cmd.append("mcp")

            if use_desktop:
                addr = self.config.control_address
                if not self.is_desktop_reachable(addr):
                    port = addr.split(":")[-1] if ":" in addr else "7981"
                    raise WordCraftUnreachableError(
                        f"WordCraft desktop application is not running or unreachable on {addr}.\n"
                        f"To observe live visual composition, please start WordCraft via:\n"
                        f"    wordcraft --control {port}\n"
                        f"or switch to headless mode via: /settings mode headless"
                    )
                cmd.extend(["--connect", addr])
            else:
                # Headless mode requires automation roots
                cmd.extend(["--automation-read-root", "/", "--automation-write-root", "/"])

            # Setup environment ensuring UTF-8
            env = dict(os.environ)
            env["LC_ALL"] = "C.UTF-8"

            logger.info("Spawning WordCraft MCP bridge: %s", " ".join(cmd))
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=env,
                )
            except Exception as e:
                raise WordCraftMCPError(f"Failed to spawn WordCraft MCP process: {e}") from e

            # Perform MCP Handshake
            self._handshake()
            self._is_connected = True
            self.discover_tools()

    def _handshake(self) -> None:
        """Performs official MCP initialize and notifications/initialized handshake."""
        init_req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "Filevo",
                    "version": "1.0",
                },
            },
        }

        resp = self._send_and_recv(init_req, timeout=self.config.timeout_seconds)
        if "error" in resp:
            err = resp["error"]
            raise WordCraftMCPError(f"MCP initialize rejected: {err.get('message', err)}")

        result = resp.get("result", {})
        self.server_info = result.get("serverInfo", {})

        # Send notifications/initialized
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        self._send_raw(init_notif)

    def discover_tools(self) -> dict[str, dict[str, Any]]:
        """Queries available tools from the WordCraft MCP server."""
        if not self._is_connected or not self._proc or self._proc.poll() is not None:
            self.start()
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        resp = self._send_and_recv(req, timeout=self.config.timeout_seconds)
        if "error" in resp:
            err = resp["error"]
            raise WordCraftMCPError(f"tools/list failed: {err.get('message', err)}")

        tools_list = resp.get("result", {}).get("tools", [])
        self.tools = {t["name"]: t for t in tools_list}
        return self.tools

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Returns the inputSchema for a discovered tool."""
        if tool_name not in self.tools:
            self.discover_tools()
        tool = self.tools.get(tool_name)
        return tool.get("inputSchema") if tool else None

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> MCPToolResult:
        """Invokes an MCP tool with arguments and returns a structured MCPToolResult."""
        if not self._is_connected or not self._proc or self._proc.poll() is not None:
            self.start()

        args = arguments or {}
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args,
            },
        }

        call_timeout = timeout or self.config.timeout_seconds
        resp = self._send_and_recv(req, timeout=call_timeout)

        if "error" in resp:
            err = resp["error"]
            raise WordCraftMCPError(f"Tool '{tool_name}' failed: {err.get('message', err)}")

        res = resp.get("result", {})
        is_error = bool(res.get("isError", False))
        content_items = res.get("content", [])

        parsed_text = ""
        parsed_json = None
        images: list[MCPImageContent] = []

        for item in content_items:
            i_type = item.get("type")
            if i_type == "text":
                txt = item.get("text", "")
                parsed_text += txt
                if not parsed_json:
                    try:
                        parsed_json = json.loads(txt)
                    except Exception:
                        pass
            elif i_type == "image":
                mime = item.get("mimeType", "image/png")
                data_b64 = item.get("data", "")
                images.append(MCPImageContent(mime_type=mime, data_base64=data_b64))

        if is_error:
            raise WordCraftMCPError(f"Tool '{tool_name}' returned error: {parsed_text}")

        return MCPToolResult(
            text=parsed_text,
            json_data=parsed_json,
            images=images,
            is_error=is_error,
            raw_content=content_items,
        )

    # ------------------------------------------------------------------ #
    # High-level Semantic Command Shortcuts
    # ------------------------------------------------------------------ #

    def new_document(self, template: str = "blank") -> int | None:
        """Opens a new document and returns its document ID."""
        res = self.call_tool("new_document", {"template": template})
        if res.json_data and isinstance(res.json_data, dict):
            return res.json_data.get("id")
        return None

    def execute(self, command: str, params: dict[str, Any] | None = None, doc: int | None = None) -> MCPToolResult:
        """Executes a single WordCraft command by ID."""
        args: dict[str, Any] = {"command": command}
        if params is not None:
            args["params"] = params
        if doc is not None:
            args["doc"] = doc
        return self.call_tool("execute", args)

    def batch(
        self,
        commands: list[dict[str, Any]],
        keep_going: bool = False,
        doc: int | None = None,
    ) -> MCPToolResult:
        """Executes a sequence of commands atomically in order."""
        args: dict[str, Any] = {"commands": commands, "keepGoing": keep_going}
        if doc is not None:
            args["doc"] = doc
        return self.call_tool("batch", args)

    def type_text(self, text: str, paragraphs: bool = False, doc: int | None = None) -> MCPToolResult:
        """Types text at current caret position."""
        args: dict[str, Any] = {"text": text, "paragraphs": paragraphs}
        if doc is not None:
            args["doc"] = doc
        return self.call_tool("type_text", args)

    def save_document(self, path: Path | str, doc: int | None = None) -> Path:
        """Saves active document to disk (.docx, .pdf, .png, etc.)."""
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        args: dict[str, Any] = {"path": str(target)}
        if doc is not None:
            args["doc"] = doc
        self.call_tool("save_document", args)
        if not target.exists() or target.stat().st_size == 0:
            raise WordCraftMCPError(f"WordCraft failed to save document to {target}")
        return target

    def inspect_document(self, doc: int | None = None) -> dict[str, Any]:
        """Returns complete AST structure of document (blocks, styles, sections)."""
        args: dict[str, Any] = {}
        if doc is not None:
            args["doc"] = doc
        res = self.call_tool("inspect_document", args)
        return res.json_data if isinstance(res.json_data, dict) else {}

    def render_page(self, page: int = 1, scale: float = 1.0, doc: int | None = None) -> bytes:
        """Renders specified page as a PNG image byte string."""
        args: dict[str, Any] = {"page": page, "scale": scale}
        if doc is not None:
            args["doc"] = doc
        res = self.call_tool("render_page", args)
        if res.images:
            return res.images[0].data_bytes
        raise WordCraftMCPError(f"render_page did not return an image for page {page}")

    def list_documents(self) -> list[dict[str, Any]]:
        """Returns open documents and their IDs."""
        res = self.call_tool("list_documents")
        return res.json_data if isinstance(res.json_data, list) else []

    # ------------------------------------------------------------------ #
    # JSON-RPC Low-Level Transport
    # ------------------------------------------------------------------ #

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _send_raw(self, msg: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise WordCraftMCPError("Process stdin is not open")
        data = json.dumps(msg) + "\n"
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def _send_and_recv(self, msg: dict[str, Any], timeout: float) -> dict[str, Any]:
        self._send_raw(msg)
        req_id = msg.get("id")

        start = time.time()
        while time.time() - start < timeout:
            if self._proc.poll() is not None:
                stderr_output = self._proc.stderr.read() if self._proc.stderr else ""
                raise WordCraftMCPError(
                    f"WordCraft MCP process terminated prematurely (exit code {self._proc.returncode}): {stderr_output}"
                )

            line = self._proc.stdout.readline() if self._proc.stdout else ""
            if not line:
                time.sleep(0.01)
                continue

            line = line.strip()
            if not line:
                continue

            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue

            if resp.get("id") == req_id:
                return resp

        raise TimeoutError(f"Timed out waiting for WordCraft MCP response to request ID {req_id}")

    def close(self) -> None:
        """Gracefully closes connection and shuts down MCP bridge process."""
        with self._lock:
            if self._proc:
                try:
                    if self._proc.stdin and not self._proc.stdin.closed:
                        self._proc.stdin.close()
                except Exception:
                    pass

                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=2.0)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
            self._is_connected = False

    def __enter__(self) -> WordCraftClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
