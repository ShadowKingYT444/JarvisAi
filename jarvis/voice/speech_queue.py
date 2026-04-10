"""Ordered speech queue with priority and interruption support.

Ensures spoken responses are delivered in order, interim status phrases
play immediately, and speech can be cancelled by a new activation.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from jarvis.shared.events import EventBus
from jarvis.voice.tts_engine import TTSEngine

logger = logging.getLogger(__name__)


# ── Interim feedback phrases ─────────────────────────────────────────

INTERIM_PHRASES: dict[str, list[str]] = {
    "search": [
        "Let me look that up...",
        "Searching for that now...",
        "Let me check on that...",
        "One moment while I search...",
    ],
    "open_tabs": [
        "Pulling up some sources for you...",
        "Opening those pages now...",
        "Let me show you what I found...",
    ],
    "open_app": [
        "Opening {app_name}...",
        "Launching {app_name} for you...",
        "Starting {app_name}...",
    ],
    "focus_start": [
        "Starting focus mode for {goal}. I'll keep distractions away.",
        "Focus mode activated. Let's stay on track with {goal}.",
        "Got it — focusing on {goal}. I'll watch for distractions.",
    ],
    "error": [
        "I ran into an issue with that.",
        "Something went wrong. Let me try a different approach.",
        "That didn't work as expected.",
    ],
    "working": [
        "Working on it...",
        "Give me just a moment...",
        "On it...",
        "Processing that now...",
    ],
}


def get_interim_phrase(category: str, **kwargs: Any) -> str:
    """Pick a random interim phrase from *category*, formatted with *kwargs*."""
    phrases = INTERIM_PHRASES.get(category, INTERIM_PHRASES["working"])
    phrase = random.choice(phrases)
    try:
        return phrase.format(**kwargs)
    except KeyError:
        return phrase


# ── SpeechQueue ──────────────────────────────────────────────────────


class SpeechQueue:
    """Manages ordered TTS output with priority and interruption.

    Parameters
    ----------
    tts_engine:
        The :class:`TTSEngine` to use for speaking.
    event_bus:
        Shared event bus for speech start/end events.
    """

    def __init__(
        self,
        tts_engine: TTSEngine,
        event_bus: EventBus | None = None,
    ) -> None:
        self._tts = tts_engine
        self._event_bus = event_bus or EventBus()
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._speaking = False
        self._cancelled = False
        self._worker_task: asyncio.Task | None = None
        self._seq = 0  # tie-breaker for same priority

    async def start(self) -> None:
        """Start the background queue worker."""
        if self._worker_task is None or self._worker_task.done():
            self._cancelled = False
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Stop the queue worker and cancel any pending speech."""
        self._cancelled = True
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def say(self, text: str, priority: int = 0) -> None:
        """Queue *text* for speaking at the given *priority* (lower = higher).

        This returns immediately. The text will be spoken when it reaches
        the front of the queue.
        """
        if not text or not text.strip():
            return
        self._seq += 1
        await self._queue.put((priority, self._seq, text))

    async def say_interim(self, text: str) -> None:
        """Speak *text* immediately with highest priority.

        Interrupts any current interim speech but not final responses.
        """
        if not text or not text.strip():
            return
        # Priority -1 = higher than normal (0)
        self._seq += 1
        await self._queue.put((-1, self._seq, text))

    def cancel(self) -> None:
        """Cancel current speech and clear the queue."""
        self._cancelled = True
        # Drain the queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        asyncio.ensure_future(self._tts.stop())

    @property
    def is_speaking(self) -> bool:
        """``True`` if TTS is currently producing audio."""
        return self._speaking

    async def _worker(self) -> None:
        """Background worker that processes the speech queue."""
        while not self._cancelled:
            try:
                priority, seq, text = await asyncio.wait_for(
                    self._queue.get(), timeout=0.5
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if self._cancelled:
                break

            self._speaking = True
            self._event_bus.emit("speech_start", text)

            try:
                await self._tts.speak(text)
            except Exception:
                logger.exception("TTS speak failed for: %s", text[:50])
            finally:
                self._speaking = False
                self._event_bus.emit("speech_end", None)
                self._cancelled = False  # reset cancel flag after speech ends
