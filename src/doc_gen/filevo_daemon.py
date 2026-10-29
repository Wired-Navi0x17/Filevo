"""Filevo Persistent IPC Daemon.

Runs a long-lived background server over a UNIX domain socket (~/.filevo/filevo.sock).
Preserves PyTorch CUDA model state, GPU memory, conversation memory, and
knowledge base singletons across commands, eliminating cold-start latency.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

# Ensure NixOS LD_LIBRARY_PATH is set
_nixos_gcc = "/nix/store/z0n70pxyzi87why1bcq81zgd7b924nfj-gcc-15.2.0-lib/lib"
_nixos_cuda = "/nix/store/ss98wc4qpvf7f3p0xkv9f4hyhli5i1g5-nvidia-x11-595.71.05/lib"
_nixos_ld = "/nix/store/1y0c7mfa4ak2js3mlxwwxz5j74gbhnld-ld-library-path/share/nix-ld/lib"
_full_ld = f"{_nixos_gcc}:{_nixos_cuda}:{_nixos_ld}"
if _full_ld not in os.environ.get("LD_LIBRARY_PATH", ""):
    os.environ["LD_LIBRARY_PATH"] = f"{_full_ld}:{os.environ.get('LD_LIBRARY_PATH', '')}"

# Add root directory to sys.path
_FILE_ABS = os.path.abspath(__file__)
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_FILE_ABS)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from src.doc_gen import filevo_cli

SOCKET_PATH = Path.home() / ".filevo" / "filevo.sock"
PID_PATH = Path.home() / ".filevo" / "daemon.pid"


class FilevoDaemon:
    """Long-lived daemon managing persistent inference, memory, and policy state."""

    def __init__(self, socket_path: Path | None = None):
        self.socket_path = socket_path or SOCKET_PATH
        self.running = False
        self.server_sock: socket.socket | None = None

    def start(self):
        """Start listening on UNIX domain socket."""
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            # Check if an existing daemon is actually alive
            try:
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.connect(str(self.socket_path))
                test_sock.sendall(json.dumps({"action": "ping"}).encode("utf-8") + b"\n")
                resp = test_sock.recv(4096)
                test_sock.close()
                if resp:
                    print(f"[Filevo Daemon] Daemon is already running on {self.socket_path}.")
                    return
            except (socket.error, ConnectionRefusedError):
                # Stale socket file
                self.socket_path.unlink(missing_ok=True)

        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(str(self.socket_path))
        self.server_sock.listen(8)
        self.running = True

        PID_PATH.write_text(str(os.getpid()))
        print(f"[Filevo Daemon] Persistent engine listening on {self.socket_path} (PID: {os.getpid()})")

        # Handle termination signals
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        while self.running:
            try:
                conn, _ = self.server_sock.accept()
                thread = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                thread.start()
            except socket.error:
                break

    def _handle_signal(self, signum, frame):
        """Graceful shutdown handler."""
        print(f"\n[Filevo Daemon] Received signal {signum}, stopping...")
        self.stop()
        sys.exit(0)

    def stop(self):
        """Clean up socket and exit server loop."""
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
        self.socket_path.unlink(missing_ok=True)
        PID_PATH.unlink(missing_ok=True)

    def _handle_client(self, conn: socket.socket):
        """Process incoming client commands from persistent connection."""
        file_obj = conn.makefile("r", encoding="utf-8")
        try:
            for line in file_obj:
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                except Exception as e:
                    err_resp = {"status": "error", "message": f"Malformed JSON: {e}"}
                    conn.sendall(json.dumps(err_resp).encode("utf-8") + b"\n")
                    continue

                action = req.get("action", "")
                resp = self._dispatch_action(action, req)
                conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
        except Exception as e:
            pass
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Dashboard telemetry (read-only snapshot of live engine state)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _reference_from_url(url: str) -> dict[str, str]:
        """Describe a source using only facts present in its URL.

        The retrieval pipeline currently stores source URLs rather than page
        titles.  We derive a readable label from the final path segment and
        always keep the original URL + domain; nothing is invented.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.removeprefix("www.")
        segment = unquote(parsed.path.rstrip("/").split("/")[-1])
        segment = segment.rsplit(".", 1)[0] if "." in segment else segment
        label = segment.replace("-", " ").replace("_", " ").strip()
        if not label:
            label = domain or url
        return {"url": url, "title": label, "domain": domain or "unknown"}

    def _dashboard_payload(self) -> dict[str, Any]:
        """Return one coherent snapshot for the Rust TUI.

        Every field is optional and independently guarded: a missing GPU,
        psutil install, or model checkpoint must not take down the dashboard.
        """
        memory = filevo_cli.get_memory()
        llm = filevo_cli.get_llm()
        rlcd = filevo_cli.get_rlcd()
        kb = filevo_cli.get_kb()
        output_dir = Path.home() / ".filevo" / "output"
        errors: list[str] = []

        # ---------------------------------------------------------- model
        context_tokens: int | None = None
        try:
            if getattr(llm, "_is_loaded", False) and getattr(llm, "model", None) is not None:
                candidate = getattr(getattr(llm.model, "config", None), "max_position_embeddings", None)
                if isinstance(candidate, int) and 0 < candidate < 1_000_000:
                    context_tokens = candidate
            if context_tokens is None and getattr(llm, "_is_loaded", False) and getattr(llm, "tokenizer", None) is not None:
                candidate = getattr(llm.tokenizer, "model_max_length", None)
                if isinstance(candidate, int) and 0 < candidate < 1_000_000:
                    context_tokens = candidate
        except Exception as exc:
            errors.append(f"context: {exc}")

        model = {
            "id": getattr(llm, "model_id", "Unknown"),
            "short": Path(getattr(llm, "model_id", "Unknown")).name,
            "device": getattr(llm, "device", "unknown"),
            "loaded": bool(getattr(llm, "_is_loaded", False)),
            "load_error": getattr(llm, "_load_error", None),
            "context_tokens": context_tokens,
        }

        # ------------------------------------------------------- session
        files_indexed = 0
        try:
            files_indexed = int(kb.get_status_summary().get("total_documents", 0))
        except Exception as exc:
            errors.append(f"knowledge: {exc}")

        documents: list[dict[str, Any]] = []
        try:
            if output_dir.is_dir():
                found = sorted(
                    output_dir.glob("*.docx"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for path in found:
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    documents.append({
                        "name": path.name,
                        "path": str(path),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
        except Exception as exc:
            errors.append(f"documents: {exc}")

        session = {
            "files_indexed": files_indexed,
            "docs_created": len(documents),
            "policy_status": "Trained" if getattr(rlcd, "episodes", 0) > 0 else "Untrained",
            "policy_episodes": int(getattr(rlcd, "episodes", 0)),
            "policy_baseline": float(getattr(rlcd, "baseline", 0.0)),
            "memory_used": len(memory.turns),
            "memory_limit": int(getattr(memory, "max_turns", 0)),
        }

        # ------------------------------------------------------ decision
        raw_decision = dict(getattr(rlcd, "last_decision_intent", {}) or {})
        decision = {
            "available": bool(getattr(rlcd, "intent_evaluated", False)),
            "intent": raw_decision.get("intent"),
            "probabilities": raw_decision.get("probabilities") or {},
            "confidence": raw_decision.get("confidence"),
            "entropy": raw_decision.get("entropy"),
            # RLCDDecisionEngine.normalized_entropy divides base-2 Shannon
            # entropy by log2(k); it is dimensionless in [0, 1].
            "entropy_unit": "normalized_shannon_base2",
            "risk": raw_decision.get("risk"),
            "source": "last_intent_evaluation" if getattr(rlcd, "intent_evaluated", False) else "backend_default_prior",
        }

        # ---------------------------------------------------- references
        references: list[dict[str, str]] = []
        try:
            for item in list(getattr(filevo_cli, "_latest_references", []) or []):
                if isinstance(item, dict):
                    url = str(item.get("url", ""))
                    title = str(item.get("title", "") or "")
                    domain = str(item.get("domain", "") or "")
                    if url and not title:
                        derived = self._reference_from_url(url)
                        title = derived["title"]
                        domain = domain or derived["domain"]
                    if title or url:
                        references.append({
                            "url": url,
                            "title": title or domain or url,
                            "domain": domain or (urlparse(url).netloc.removeprefix("www.") if url else "unknown"),
                        })
                elif item:
                    references.append(self._reference_from_url(str(item)))
        except Exception as exc:
            errors.append(f"references: {exc}")

        # ------------------------------------------------------- turns
        turns: list[dict[str, Any]] = []
        try:
            for turn in memory.turns:
                turns.append({
                    "role": turn.role,
                    "content": turn.content,
                    "timestamp": float(turn.timestamp),
                    "metadata": turn.metadata or {},
                })
        except Exception as exc:
            errors.append(f"turns: {exc}")

        # --------------------------------------------------- telemetry
        gpu: dict[str, Any] | None = None
        try:
            probe = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            line = next((ln for ln in probe.stdout.splitlines() if ln.strip()), "")
            if probe.returncode == 0 and line:
                parts = [part.strip() for part in line.split(",")]
                if len(parts) >= 4:
                    gpu = {
                        "name": parts[0],
                        "utilization": float(parts[1]),
                        "memory_used_mb": float(parts[2]),
                        "memory_total_mb": float(parts[3]),
                    }
        except Exception:
            gpu = None

        disk: dict[str, Any] | None = None
        try:
            usage = shutil.disk_usage(str(Path.home()))
            disk = {
                "path": str(Path.home()),
                "used": usage.used,
                "total": usage.total,
                "free": usage.free,
            }
        except Exception as exc:
            errors.append(f"disk: {exc}")

        system_memory: dict[str, Any] | None = None
        try:
            import psutil  # optional dependency; already declared in pyproject

            vm = psutil.virtual_memory()
            system_memory = {"used": int(vm.used), "total": int(vm.total)}
        except Exception:
            try:
                meminfo: dict[str, int] = {}
                with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                    for line in handle:
                        key, _, rest = line.partition(":")
                        bits = rest.strip().split()
                        if bits:
                            meminfo[key] = int(bits[0]) * 1024
                total = meminfo.get("MemTotal", 0)
                available = meminfo.get("MemAvailable", 0)
                if total:
                    system_memory = {"used": max(0, total - available), "total": total}
            except Exception as exc:
                errors.append(f"system_memory: {exc}")

        web_enabled = os.environ.get("FILEVO_WEB_DISABLED") != "1"
        web = {
            "enabled": web_enabled,
            "live_references": len(references),
            "last_result": "live" if (web_enabled and references) else ("idle" if web_enabled else "disabled"),
        }

        policy: dict[str, Any] = {}
        try:
            telemetry = rlcd.get_telemetry()
            policy = {
                "episodes": int(telemetry.get("episodes", 0)),
                "baseline": float(telemetry.get("baseline", 0.0)),
                "temperature": float(telemetry.get("temperature", 1.0)),
                "archetype_distribution": dict(telemetry.get("archetype_distribution", {})),
                "font_distribution": dict(telemetry.get("font_distribution", {})),
            }
        except Exception as exc:
            errors.append(f"policy: {exc}")

        return {
            "status": "ok",
            "protocol": 2,
            "generated_at": time.time(),
            "model": model,
            "session": session,
            "decision": decision,
            "references": references,
            "documents": documents,
            "turns": turns,
            "telemetry": {
                "gpu": gpu,
                "disk": disk,
                "system_memory": system_memory,
                "model_ready": bool(getattr(llm, "_is_loaded", False) and not getattr(llm, "_load_error", None)),
                "web": web,
            },
            "policy": policy,
            "errors": errors,
        }

    def _dispatch_action(self, action: str, req: dict[str, Any]) -> dict[str, Any]:
        """Route request through persistent singletons."""
        memory = filevo_cli.get_memory()
        llm = filevo_cli.get_llm()
        rlcd = filevo_cli.get_rlcd()

        if action == "ping":
            return {
                "status": "ok",
                "protocol": 2,
                "active_model": llm.model_id,
                "device": llm.device,
                "model_loaded": bool(getattr(llm, "_is_loaded", False)),
                "active_topic": memory.active_document_topic,
                "active_doc": memory.active_document_path,
                "turns": len(memory.turns),
                "pid": os.getpid(),
            }

        elif action == "dashboard":
            return self._dashboard_payload()

        elif action == "chat":
            text = req.get("text", "")
            clean_text, attachments = filevo_cli.resolve_file_mentions(text)
            memory.add_user_message(clean_text, attachments)
            resolved_ref = memory.resolve_references(clean_text)

            p_lower = clean_text.lower()
            is_question = any(p_lower.startswith(q) for q in ("why", "how", "what", "explain", "describe", "tell me", "does", "can you")) or ("?" in p_lower and not any(r in p_lower for r in ("revise", "make it", "rewrite")))
            revision_cues = ["make it", "more formal", "revise", "rewrite", "shorter", "longer", "add a section", "update the doc"]

            if memory.active_document_path and not is_question and any(rc in p_lower for rc in revision_cues):
                new_path = filevo_cli.cmd_revise(clean_text)
                return {
                    "status": "revised",
                    "type": "revision",
                    "active_doc": str(new_path) if new_path else None,
                    "topic": memory.active_document_topic,
                    "message": f"Revised document version created at {new_path.name if new_path else ''}",
                }

            intent_eval = rlcd.evaluate_intent(clean_text)
            intent_type = intent_eval.get("intent", "CONVERSATION")

            if intent_type == "DOCUMENT_CREATION":
                filevo_cli.cmd_create(clean_text, attachments)
                return {
                    "status": "created",
                    "type": "document_creation",
                    "active_doc": memory.active_document_path,
                    "topic": memory.active_document_topic,
                    "archetype": memory.active_archetype,
                    "decision": intent_eval,
                }
            elif intent_type == "DOCUMENT_ANALYSIS":
                filevo_cli.cmd_analyze(clean_text)
                return {"status": "ok", "type": "analysis"}
            elif intent_type == "KNOWLEDGE_INDEXING":
                filevo_cli.cmd_index(".")
                return {"status": "ok", "type": "indexing"}

            # Conversational path
            question_cues = ["why", "how", "what", "explain", "describe", "tell me", "does", "difference"]
            if any(q in p_lower for q in question_cues) or "?" in clean_text:
                try:
                    from src.doc_gen.web_researcher import WebResearcher
                    wr = WebResearcher()
                    res = wr.research_topic(clean_text)
                    if res.get("sources"):
                        filevo_cli._latest_references = res["sources"]
                except Exception:
                    pass

            messages = memory.get_messages_for_llm()
            response = llm.generate_chat_response(messages)
            memory.add_assistant_message(response)

            return {
                "status": "ok",
                "type": "chat_reply",
                "response": response,
                "references": filevo_cli._latest_references,
                "decision": rlcd.last_decision_intent,
            }

        elif action == "create":
            req_str = req.get("request", "")
            filevo_cli.cmd_create(req_str)
            return {
                "status": "ok",
                "active_doc": memory.active_document_path,
                "topic": memory.active_document_topic,
                "archetype": memory.active_archetype,
            }

        elif action == "revise":
            instruction = req.get("instruction", "")
            new_path = filevo_cli.cmd_revise(instruction)
            return {
                "status": "ok",
                "active_doc": str(new_path) if new_path else None,
                "topic": memory.active_document_topic,
            }

        elif action == "research":
            topic = req.get("topic", "")
            filevo_cli.cmd_research(topic)
            return {"status": "ok", "topic": topic}

        elif action == "analyze":
            path = req.get("path", ".")
            filevo_cli.cmd_analyze(path)
            return {"status": "ok", "path": path}

        elif action == "index":
            path = req.get("path", ".")
            filevo_cli.cmd_index(path)
            return {"status": "ok", "path": path}

        elif action == "train":
            args = req.get("args", "corpus")
            filevo_cli.cmd_train(args)
            return {"status": "ok"}

        elif action == "feedback":
            reward = req.get("reward", "1.0")
            filevo_cli.cmd_feedback(reward)
            return {"status": "ok", "reward": reward}

        elif action == "status":
            summary = filevo_cli.get_kb().get_status_summary()
            mem = memory.get_summary()
            rlcd_sum = rlcd.get_telemetry()
            return {
                "status": "ok",
                "knowledge": summary,
                "memory": mem,
                "rlcd": rlcd_sum,
                "model_id": llm.model_id,
                "device": llm.device,
            }

        elif action == "model":
            filevo_cli.cmd_model()
            return {"status": "ok", "model_id": llm.model_id, "device": llm.device}

        elif action == "clear":
            memory.clear()
            return {"status": "ok", "cleared": True}

        else:
            return {"status": "error", "message": f"Unknown action: {action}"}


def main():
    """Daemon runner entry point."""
    daemon = FilevoDaemon()
    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
