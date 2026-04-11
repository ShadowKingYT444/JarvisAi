"""Floating HUD overlay with animated arc reactor for Jarvis.

A frameless, translucent, always-on-top widget that shows an animated
arc reactor orb and status text. Appears at the bottom-right of the
screen and auto-hides when idle.
"""

from __future__ import annotations

import logging
import sys

from jarvis.shared.events import EventBus
from jarvis.shared.types import JarvisState

logger = logging.getLogger(__name__)

# Auto-hide delay in ms after speech ends
_AUTOHIDE_DELAY_MS = 4000

# State name mapping for the arc reactor
_STATE_NAMES = {
    JarvisState.IDLE: "idle",
    JarvisState.INITIALIZING: "initializing",
    JarvisState.LISTENING: "listening",
    JarvisState.PROCESSING: "processing",
    JarvisState.SPEAKING: "speaking",
    JarvisState.ERROR: "error",
    JarvisState.FOCUS_MODE: "focus_mode",
}


class OverlayHUD:
    """Floating HUD overlay with arc reactor and status text.

    Parameters
    ----------
    event_bus:
        Shared event bus for state and transcript events.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus or EventBus()
        self._widget = None
        self._arc_reactor = None
        self._label = None
        self._hide_timer = None
        self._current_state = JarvisState.IDLE

        # Subscribe to events
        self._event_bus.on("state_changed", self._on_state_changed)
        self._event_bus.on("transcript_partial", self._on_partial_transcript)
        self._event_bus.on("speech_start", self._on_speech_start)
        self._event_bus.on("speech_end", self._on_speech_end)
        self._event_bus.on("overlay_status", self._on_overlay_status)

    def setup(self) -> None:
        """Create the overlay widget. Must be called after QApplication init."""
        try:
            from PyQt6.QtCore import QTimer, Qt
            from PyQt6.QtGui import QFont
            from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

            screen = QApplication.primaryScreen()
            if screen is None:
                logger.warning("No screen available for overlay")
                return

            screen_geom = screen.geometry()

            # Main container
            self._widget = QWidget()
            self._widget.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self._widget.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground
            )
            self._widget.setFixedSize(320, 220)

            # Position: bottom-right of screen
            x = screen_geom.width() - 340
            y = screen_geom.height() - 260
            self._widget.move(x, y)

            # Layout
            layout = QVBoxLayout(self._widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)

            # Arc reactor widget
            try:
                from jarvis.face.arc_reactor import ArcReactorWidget
                self._arc_reactor = ArcReactorWidget()
                layout.addWidget(self._arc_reactor, alignment=Qt.AlignmentFlag.AlignCenter)
            except Exception:
                logger.warning("Arc reactor widget unavailable — using text-only overlay")

            # Status text label
            font_name = "Segoe UI" if sys.platform == "win32" else "SF Pro Display"
            self._label = QLabel()
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._label.setFont(QFont(font_name, 11))
            self._label.setWordWrap(True)
            self._label.setFixedWidth(300)
            self._label.setStyleSheet(
                """
                QLabel {
                    background-color: rgba(20, 20, 20, 180);
                    color: rgba(255, 255, 255, 220);
                    border-radius: 16px;
                    padding: 8px 16px;
                }
                """
            )
            layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignCenter)

            # Auto-hide timer
            self._hide_timer = QTimer()
            self._hide_timer.setSingleShot(True)
            self._hide_timer.timeout.connect(self._hide)

            # Click to dismiss
            self._widget.mousePressEvent = lambda _: self._hide()

            # Start hidden
            self._widget.hide()
            logger.info("Overlay HUD initialized (with arc reactor)")

        except ImportError:
            logger.warning("PyQt6 not available — overlay disabled")
        except Exception:
            logger.exception("Failed to set up overlay HUD")

    def _show(self, text: str) -> None:
        """Show the overlay with the given text."""
        if self._widget is None:
            return

        if self._label is not None:
            self._label.setText(text)
        if not self._widget.isVisible():
            self._widget.show()

        # Cancel any pending hide
        if self._hide_timer and self._hide_timer.isActive():
            self._hide_timer.stop()

    def _hide(self) -> None:
        """Hide the overlay."""
        if self._widget:
            self._widget.hide()

    def _schedule_hide(self) -> None:
        """Schedule auto-hide after a delay."""
        if self._hide_timer:
            self._hide_timer.start(_AUTOHIDE_DELAY_MS)

    def _set_reactor_state(self, state: JarvisState) -> None:
        """Update the arc reactor animation state."""
        if self._arc_reactor is not None:
            state_name = _STATE_NAMES.get(state, "idle")
            self._arc_reactor.set_state(state_name)

    # ── Event handlers ───────────────────────────────────────────────

    def _on_state_changed(self, data) -> None:
        if isinstance(data, tuple) and len(data) >= 1:
            state = data[0]
        else:
            state = data

        if not isinstance(state, JarvisState):
            return

        self._current_state = state
        self._set_reactor_state(state)
        metadata = data[1] if isinstance(data, tuple) and len(data) > 1 else {}

        if state == JarvisState.INITIALIZING:
            self._show(metadata.get("text", "Initializing Jarvis..."))
        elif state == JarvisState.LISTENING:
            self._show("Listening...")
        elif state == JarvisState.PROCESSING:
            self._show("Thinking...")
        elif state == JarvisState.IDLE:
            self._schedule_hide()
        elif state == JarvisState.ERROR:
            self._show("Something went wrong.")
            self._schedule_hide()

    def _on_partial_transcript(self, text) -> None:
        if isinstance(text, str) and text.strip():
            self._show(text)

    def _on_speech_start(self, text) -> None:
        if isinstance(text, str) and text.strip():
            display = text[:80] + "..." if len(text) > 80 else text
            self._show(display)

    def _on_speech_end(self, _data) -> None:
        self._schedule_hide()

    def _on_overlay_status(self, text) -> None:
        if isinstance(text, str) and text.strip():
            self._show(text)
