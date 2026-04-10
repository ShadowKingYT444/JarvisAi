"""Simple pub/sub event bus for cross-module communication."""

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """Simple pub/sub event bus for cross-module communication.

    Standard events:
        "state_changed"       -> (JarvisState, dict)
        "clap_detected"       -> None
        "transcript_partial"  -> str
        "transcript_final"    -> TranscriptResult
        "tool_executing"      -> ToolCall
        "tool_complete"       -> ToolResult
        "speech_start"        -> str
        "speech_end"          -> None
        "error"               -> str
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable) -> None:
        """Remove a callback for an event."""
        if event in self._listeners:
            self._listeners[event] = [
                cb for cb in self._listeners[event] if cb != callback
            ]

    def emit(self, event: str, data: Any = None) -> None:
        """Emit an event synchronously."""
        for callback in self._listeners.get(event, []):
            try:
                callback(data)
            except Exception:
                logger.exception("Error in event handler for %s", event)

    async def emit_async(self, event: str, data: Any = None) -> None:
        """Emit an event, awaiting any async callbacks."""
        for callback in self._listeners.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception:
                logger.exception("Error in async event handler for %s", event)
