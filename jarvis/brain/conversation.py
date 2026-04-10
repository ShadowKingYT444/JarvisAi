"""Conversation history manager for Jarvis.

Maintains a rolling in-memory history (last *max_turns* turns) and persists
every entry to a date-stamped JSONL file under ``~/.jarvis/conversations/``.
On startup the current day's log is loaded so the model has context from
earlier interactions in the same session.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
from google.generativeai import protos

from jarvis.shared.config import JarvisConfig

logger = logging.getLogger(__name__)


class ConversationManager:
    """Rolling conversation history with JSONL persistence."""

    def __init__(self, config: JarvisConfig, max_turns: int = 20) -> None:
        self._config = config
        self._max_turns = max_turns
        self._history: list[dict[str, Any]] = []
        self._conv_dir = Path(config.conversation_dir).expanduser()
        self._conv_dir.mkdir(parents=True, exist_ok=True)

    # ── public helpers ────────────────────────────────────────────────

    def add_user_message(self, text: str) -> None:
        """Append a user turn and persist it."""
        entry = self._make_entry("user", text)
        self._history.append(entry)
        self._trim()
        # fire-and-forget persistence (caller is async, but we keep sync path safe)
        self._persist_sync(entry)

    def add_assistant_message(
        self, text: str, tools_used: list[str] | None = None
    ) -> None:
        """Append an assistant turn and persist it."""
        entry = self._make_entry("assistant", text, tools_used=tools_used or [])
        self._history.append(entry)
        self._trim()
        self._persist_sync(entry)

    def get_history(self) -> list[dict[str, Any]]:
        """Return a copy of the current in-memory history."""
        return list(self._history)

    def get_gemini_history(self) -> list[protos.Content]:
        """Convert the in-memory history into a list of Gemini
        ``Content`` objects suitable for ``generate_content``."""
        contents: list[protos.Content] = []
        for entry in self._history:
            role = entry["role"]
            text = entry.get("text", "")
            # Gemini uses "user" and "model" roles
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                protos.Content(
                    role=gemini_role,
                    parts=[protos.Part(text=text)],
                )
            )
        return contents

    def load_today(self) -> None:
        """Load today's JSONL log file (if it exists) into the history."""
        log_path = self._today_path()
        if not log_path.exists():
            logger.debug("No conversation log for today yet.")
            return

        loaded = 0
        try:
            with open(log_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._history.append(entry)
                        loaded += 1
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed JSONL line")
        except OSError:
            logger.exception("Failed to read conversation log %s", log_path)

        self._trim()
        logger.info("Loaded %d turns from today's conversation log.", loaded)

    def clear(self) -> None:
        """Reset the in-memory history (does *not* delete the log file)."""
        self._history.clear()

    # ── async persistence (preferred in async contexts) ───────────────

    async def apersist(self, entry: dict[str, Any]) -> None:
        """Append *entry* as a JSON line to today's log file (async)."""
        log_path = self._today_path()
        try:
            async with aiofiles.open(log_path, "a", encoding="utf-8") as fh:
                await fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("Failed to persist conversation entry")

    # ── internal ──────────────────────────────────────────────────────

    def _persist_sync(self, entry: dict[str, Any]) -> None:
        """Synchronous fallback for persistence when we are not in an
        async context or when fire-and-forget is acceptable."""
        log_path = self._today_path()
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("Failed to persist conversation entry")

    # alias kept for spec compatibility
    _persist = _persist_sync

    def _today_path(self) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._conv_dir / f"{today}.jsonl"

    @staticmethod
    def _make_entry(
        role: str, text: str, tools_used: list[str] | None = None
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "text": text,
            "tools_used": tools_used or [],
        }

    def _trim(self) -> None:
        """Keep only the last ``_max_turns`` entries."""
        if len(self._history) > self._max_turns:
            self._history = self._history[-self._max_turns :]
