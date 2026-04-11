"""Global hotkey listener for Jarvis activation.

Registers a system-wide hotkey (default Ctrl+Shift+J) that triggers
the Jarvis activation cycle, as an alternative to voice/clap activation.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from pynput.keyboard import GlobalHotKeys

logger = logging.getLogger(__name__)

_SPECIAL_KEYS = {"ctrl", "shift", "alt", "cmd", "super"}


class HotkeyListener:
    """Listen for a global hotkey combination.

    Parameters
    ----------
    on_hotkey:
        Callback fired when the hotkey is pressed.
    hotkey:
        Key combination string like ``"ctrl+shift+j"``.
    """

    def __init__(
        self,
        on_hotkey: Callable[[], None],
        hotkey: str = "ctrl+shift+j",
    ) -> None:
        self._on_hotkey = on_hotkey
        self._hotkey_str = hotkey
        self._listener: Optional[GlobalHotKeys] = None
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start listening for the hotkey in a background thread."""
        with self._lock:
            if self._running:
                logger.debug("HotkeyListener already running – ignoring start()")
                return

            pynput_combo = self._parse_hotkey(self._hotkey_str)
            logger.info("Registering global hotkey: %s -> %s", self._hotkey_str, pynput_combo)

            try:
                self._listener = GlobalHotKeys({pynput_combo: self._fire})
                self._listener.daemon = True
                self._listener.start()
                self._running = True
                logger.info("HotkeyListener started")
            except Exception:
                logger.exception("Failed to start HotkeyListener")
                self._listener = None
                raise

    def stop(self) -> None:
        """Stop the hotkey listener and release resources."""
        with self._lock:
            if not self._running or self._listener is None:
                return

            try:
                self._listener.stop()
                self._listener.join(timeout=2.0)
            except Exception:
                logger.exception("Error stopping HotkeyListener")
            finally:
                self._listener = None
                self._running = False
                logger.info("HotkeyListener stopped")

    @property
    def running(self) -> bool:
        """Return ``True`` if the listener is currently active."""
        return self._running

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire(self) -> None:
        """Invoke the user callback, catching any exceptions."""
        logger.debug("Hotkey triggered: %s", self._hotkey_str)
        try:
            self._on_hotkey()
        except Exception:
            logger.exception("Error in hotkey callback")

    @staticmethod
    def _parse_hotkey(hotkey_str: str) -> str:
        """Convert a human-readable hotkey string to pynput format.

        ``"ctrl+shift+j"`` becomes ``"<ctrl>+<shift>+j"``

        Special/modifier keys are wrapped in angle brackets; regular
        single-character keys are left as-is.
        """
        parts: list[str] = []
        for token in hotkey_str.lower().split("+"):
            token = token.strip()
            if not token:
                continue
            if token in _SPECIAL_KEYS:
                parts.append(f"<{token}>")
            else:
                parts.append(token)
        combo = "+".join(parts)
        if not combo:
            raise ValueError(f"Invalid hotkey string: {hotkey_str!r}")
        return combo
