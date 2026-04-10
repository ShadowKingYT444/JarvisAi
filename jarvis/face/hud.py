"""HUD state manager — bridges Jarvis state to the Face layer.

Wraps :class:`JarvisState` transitions and notifies the overlay
and system tray through the event bus.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from jarvis.shared.events import EventBus
from jarvis.shared.types import JarvisState

logger = logging.getLogger(__name__)


class StateManager:
    """Central state manager for the Jarvis UI.

    Tracks current Jarvis state and notifies subscribers (tray, overlay)
    via the event bus.

    Parameters
    ----------
    event_bus:
        Shared event bus (emits ``"state_changed"`` events).
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus or EventBus()
        self._state = JarvisState.IDLE
        self._metadata: dict[str, Any] = {}
        self._subscribers: list[Callable[[JarvisState, dict], None]] = []

    def set_state(self, state: JarvisState, metadata: dict | None = None) -> None:
        """Transition to a new state.

        Parameters
        ----------
        state:
            The new :class:`JarvisState`.
        metadata:
            Optional metadata (e.g. ``{"goal": "writing essay"}``
            for ``FOCUS_MODE``).
        """
        old = self._state
        self._state = state
        self._metadata = metadata or {}

        logger.debug("State: %s -> %s (meta=%s)", old.value, state.value, self._metadata)

        # Notify via event bus
        self._event_bus.emit("state_changed", (state, self._metadata))

        # Notify direct subscribers
        for callback in self._subscribers:
            try:
                callback(state, self._metadata)
            except Exception:
                logger.exception("Error in state subscriber callback")

    def subscribe(self, callback: Callable[[JarvisState, dict], None]) -> None:
        """Register a callback that fires on every state change.

        The callback receives ``(state, metadata)``.
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[JarvisState, dict], None]) -> None:
        """Remove a previously registered callback."""
        self._subscribers = [cb for cb in self._subscribers if cb != callback]

    @property
    def current_state(self) -> JarvisState:
        """The current Jarvis state."""
        return self._state

    @property
    def metadata(self) -> dict[str, Any]:
        """Metadata associated with the current state."""
        return self._metadata
