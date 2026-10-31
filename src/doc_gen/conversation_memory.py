"""Multi-Turn Conversational Memory for Filevo.

Maintains sliding-window session history, tracks active document context,
and resolves anaphora/references (e.g., "make it more formal", "expand section 2")
across consecutive turns without sending unbounded token history.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ConversationTurn:
    """A single turn in the conversation session."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationMemory:
    """Manages short-term conversation turns and active context in memory."""

    def __init__(self, max_turns: int = 8):
        self.max_turns = max_turns
        self.turns: list[ConversationTurn] = []
        # Active contextual state
        self.active_document_path: str | None = None
        self.active_document_topic: str | None = None
        self.active_archetype: str | None = None
        self.last_expanded_section: str | None = None
        self.last_referenced_files: list[str] = []
        self.session_file = Path.home() / ".filevo" / "session_memory.json"
        self.load()

    def load(self):
        """Load session state from ~/.filevo/session_memory.json if present."""
        if self.session_file.exists():
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_document_path = data.get("active_document_path")
                    self.active_document_topic = data.get("active_document_topic")
                    self.active_archetype = data.get("active_archetype")
                    self.last_expanded_section = data.get("last_expanded_section")
                    self.last_referenced_files = data.get("last_referenced_files", [])
                    raw_turns = data.get("turns", [])
                    self.turns = [
                        ConversationTurn(
                            role=t.get("role", "user"),
                            content=t.get("content", ""),
                            timestamp=t.get("timestamp", time.time()),
                            metadata=t.get("metadata", {}),
                        )
                        for t in raw_turns
                    ]
            except Exception:
                pass

        # If still no active document, auto-detect latest .docx in ~/.filevo/output
        if not self.active_document_path or not Path(self.active_document_path).exists():
            out_dir = Path.home() / ".filevo" / "output"
            if out_dir.exists():
                docx_files = sorted(out_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
                if docx_files:
                    latest = docx_files[0]
                    self.active_document_path = str(latest)
                    self.active_document_topic = latest.stem.replace("_", " ")

    def save(self):
        """Persist session state to ~/.filevo/session_memory.json."""
        try:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "active_document_path": self.active_document_path,
                "active_document_topic": self.active_document_topic,
                "active_archetype": self.active_archetype,
                "last_expanded_section": self.last_expanded_section,
                "last_referenced_files": self.last_referenced_files,
                "turns": [
                    {
                        "role": t.role,
                        "content": t.content,
                        "timestamp": t.timestamp,
                        "metadata": t.metadata,
                    }
                    for t in self.turns[-self.max_turns:]
                ],
            }
            tmp_file = self.session_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_file.replace(self.session_file)
        except Exception:
            if "tmp_file" in locals() and tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass

    def add_user_message(self, content: str, attachments: list[dict[str, Any]] | None = None):
        """Record a user turn."""
        meta = {}
        if attachments:
            meta["attachments"] = [a.get("name", "") for a in attachments]
            self.last_referenced_files = [a.get("path", "") for a in attachments if a.get("path")]

        self.turns.append(ConversationTurn(role="user", content=content, metadata=meta))
        self._prune()
        self.save()

    def add_assistant_message(
        self,
        content: str,
        generated_doc: str | None = None,
        archetype: str | None = None,
        topic: str | None = None,
        expanded_section: str | None = None,
    ):
        """Record an assistant turn and update active document state."""
        meta = {}
        if generated_doc:
            meta["generated_doc"] = generated_doc
            self.active_document_path = generated_doc
        if archetype:
            meta["archetype"] = archetype
            self.active_archetype = archetype
        if topic:
            meta["topic"] = topic
            self.active_document_topic = topic
        if expanded_section:
            self.last_expanded_section = expanded_section
            meta["expanded_section"] = expanded_section

        self.turns.append(ConversationTurn(role="assistant", content=content, metadata=meta))
        self._prune()
        self.save()

    def _prune(self):
        """Keep only the most recent N turns to prevent context window overflow."""
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def get_messages_for_llm(self, system_prompt: str | None = None) -> list[dict[str, str]]:
        """Return formatted messages for Hugging Face tokenizer chat templates."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        for turn in self.turns:
            messages.append({"role": turn.role, "content": turn.content})

        return messages

    def resolve_references(self, current_prompt: str) -> dict[str, Any]:
        """Resolve references like 'it', 'that document', 'make it formal' using active context."""
        p_lower = current_prompt.lower()
        resolved = {
            "target_topic": self.active_document_topic,
            "target_doc": self.active_document_path,
            "target_archetype": self.active_archetype,
            "referenced_files": list(self.last_referenced_files),
            "is_followup": False,
        }

        # Check for referential pronouns and follow-up markers with word boundaries
        import re
        pattern = r"\b(it|that|this|previous|earlier|again|more formal|longer|shorter|regenerate|rewrite|expand|summarize that|continue|instead)\b"
        if re.search(pattern, p_lower):
            resolved["is_followup"] = True

        return resolved

    def clear(self):
        """Reset conversation session memory."""
        self.turns.clear()
        self.active_document_path = None
        self.active_document_topic = None
        self.active_archetype = None
        self.last_expanded_section = None
        self.last_referenced_files.clear()
        self.save()

    def get_summary(self) -> dict[str, Any]:
        """Return diagnostic state of memory."""
        return {
            "total_turns": len(self.turns),
            "active_topic": self.active_document_topic,
            "active_document": self.active_document_path,
            "active_archetype": self.active_archetype,
            "recent_turns": [
                {"role": t.role, "snippet": t.content[:60] + "..." if len(t.content) > 60 else t.content}
                for t in self.turns[-4:]
            ],
        }
