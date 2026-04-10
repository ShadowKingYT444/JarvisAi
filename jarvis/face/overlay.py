"""Minimal floating HUD overlay for Jarvis status and transcription.

A frameless, translucent, always-on-top pill widget that appears at the
bottom-center of the screen on activation and auto-hides after speech.
"""

from __future__ import annotations

import logging

from jarvis.shared.events import EventBus
from jarvis.shared.types import JarvisState

logger = logging.getLogger(__name__)

# Auto-hide delay in ms after speech ends
_AUTOHIDE_DELAY_MS = 2000


class OverlayHUD:
    """Floating HUD overlay that shows Jarvis status and transcription.

    Parameters
    ----------
    event_bus:
        Shared event bus for state and transcript events.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._event_bus = event_bus or EventBus()
        self._widget = None
        self._label = None
        self._hide_timer = None
        self._current_state = JarvisState.IDLE

        # Subscribe to events
        self._event_bus.on("state_changed", self._on_state_changed)
        self._event_bus.on("transcript_partial", self._on_partial_transcript)
        self._event_bus.on("speech_start", self._on_speech_start)
        self._event_bus.on("speech_end", self._on_speech_end)

    def setup(self) -> None:
        """Create the overlay widget. Must be called after QApplication init."""
        try:
            from PyQt6.QtCore import QTimer, Qt
            from PyQt6.QtGui import QColor, QFont
            from PyQt6.QtWidgets import QApplication, QLabel, QWidget

            screen = QApplication.primaryScreen()
            if screen is None:
                logger.warning("No screen available for overlay")
                return

            screen_geom = screen.geometry()

            # Pill-shaped container
            self._widget = QWidget()
            self._widget.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool  # doesn't appear in taskbar
            )
            self._widget.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground
            )
            self._widget.setFixedSize(400, 60)

            # Position: bottom-center of screen
            x = (screen_geom.width() - 400) // 2
            y = screen_geom.height() - 100
            self._widget.move(x, y)

            # Styled label inside
            self._label = QLabel(self._widget)
            self._label.setFixedSize(400, 60)
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._label.setFont(QFont("SF Pro Display", 14))
            self._label.setStyleSheet(
                """
                QLabel {
                    background-color: rgba(30, 30, 30, 200);
                    color: white;
                    border-radius: 30px;
                    padding: 0 20px;
                }
                """
            )

            # Auto-hide timer
            self._hide_timer = QTimer()
            self._hide_timer.setSingleShot(True)
            self._hide_timer.timeout.connect(self._hide)

            # Click to dismiss
            self._widget.mousePressEvent = lambda _: self._hide()

            # Start hidden
            self._widget.hide()
            logger.info("Overlay HUD initialized")

        except ImportError:
            logger.warning("PyQt6 not available — overlay disabled")
        except Exception:
            logger.exception("Failed to set up overlay HUD")

    def _show(self, text: str) -> None:
        """Show the overlay with the given text."""
        if self._widget is None or self._label is None:
            return

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

    # ── Event handlers ───────────────────────────────────────────────

    def _on_state_changed(self, data) -> None:
        if isinstance(data, tuple) and len(data) >= 1:
            state = data[0]
        else:
            state = data

        if not isinstance(state, JarvisState):
            return

        self._current_state = state

        if state == JarvisState.LISTENING:
            self._show("\U0001F3A4  Listening...")
        elif state == JarvisState.PROCESSING:
            self._show("\U0001F504  Thinking...")
        elif state == JarvisState.IDLE:
            self._schedule_hide()
        elif state == JarvisState.ERROR:
            self._show("\U0000274C  Error")
            self._schedule_hide()

    def _on_partial_transcript(self, text) -> None:
        if isinstance(text, str) and text.strip():
            self._show(f"\U0001F3A4  {text}")

    def _on_speech_start(self, text) -> None:
        if isinstance(text, str) and text.strip():
            display = text[:60] + "..." if len(text) > 60 else text
            self._show(f"\U0001F50A  {display}")

    def _on_speech_end(self, _data) -> None:
        self._schedule_hide()
