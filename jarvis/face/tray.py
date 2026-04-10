"""System tray icon with state-based color indicators and context menu.

Provides a persistent tray icon that changes color based on Jarvis state
and offers quick actions via a context menu.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import JarvisState

logger = logging.getLogger(__name__)

# Color map: state → (R, G, B) for the tray icon
STATE_COLORS: dict[JarvisState, tuple[int, int, int]] = {
    JarvisState.IDLE: (128, 128, 128),       # Gray
    JarvisState.LISTENING: (66, 133, 244),    # Blue
    JarvisState.PROCESSING: (255, 179, 0),    # Amber
    JarvisState.SPEAKING: (52, 168, 83),      # Green
    JarvisState.ERROR: (234, 67, 53),         # Red
    JarvisState.FOCUS_MODE: (156, 39, 176),   # Purple
}


class SystemTray:
    """PyQt6-based system tray icon for Jarvis.

    Parameters
    ----------
    app:
        The QApplication instance (needed for system tray).
    event_bus:
        Shared event bus to subscribe to state changes.
    config:
        Jarvis configuration.
    """

    def __init__(
        self,
        app: object,  # QApplication
        event_bus: EventBus | None = None,
        config: JarvisConfig | None = None,
    ) -> None:
        self._app = app
        self._event_bus = event_bus or EventBus()
        self._config = config or JarvisConfig()
        self._tray = None
        self._current_state = JarvisState.IDLE

        self._event_bus.on("state_changed", self._on_state_changed)

    def setup(self) -> None:
        """Create the system tray icon and menu."""
        try:
            from PyQt6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter
            from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

            if not QSystemTrayIcon.isSystemTrayAvailable():
                logger.warning("System tray not available on this platform")
                return

            self._tray = QSystemTrayIcon(self._app)

            # Create initial icon
            self._update_icon(JarvisState.IDLE)

            # Context menu
            menu = QMenu()

            status_action = QAction("Jarvis — Idle", menu)
            status_action.setEnabled(False)
            self._status_action = status_action
            menu.addAction(status_action)

            menu.addSeparator()

            focus_action = QAction("Focus Mode", menu)
            focus_action.setCheckable(True)
            focus_action.triggered.connect(self._toggle_focus_mode)
            self._focus_action = focus_action
            menu.addAction(focus_action)

            text_mode_action = QAction("Text Mode", menu)
            text_mode_action.triggered.connect(self._open_text_mode)
            menu.addAction(text_mode_action)

            menu.addSeparator()

            settings_action = QAction("Settings", menu)
            settings_action.triggered.connect(self._open_settings)
            menu.addAction(settings_action)

            log_action = QAction("Conversation Log", menu)
            log_action.triggered.connect(self._open_log)
            menu.addAction(log_action)

            menu.addSeparator()

            quit_action = QAction("Quit Jarvis", menu)
            quit_action.triggered.connect(self._quit)
            menu.addAction(quit_action)

            self._tray.setContextMenu(menu)
            self._tray.setToolTip("Jarvis AI Assistant")
            self._tray.show()

            logger.info("System tray initialized")

        except ImportError:
            logger.warning("PyQt6 not available — system tray disabled")
        except Exception:
            logger.exception("Failed to set up system tray")

    def _update_icon(self, state: JarvisState) -> None:
        """Generate a colored circle icon for the given state."""
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

            r, g, b = STATE_COLORS.get(state, (128, 128, 128))
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 0, 0, 0))

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(r, g, b))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(2, 2, 28, 28)
            painter.end()

            if self._tray:
                self._tray.setIcon(QIcon(pixmap))
        except Exception:
            logger.exception("Failed to update tray icon")

    def _on_state_changed(self, data) -> None:
        """Handle state change events."""
        if isinstance(data, tuple) and len(data) >= 1:
            state = data[0]
        else:
            state = data

        if isinstance(state, JarvisState):
            self._current_state = state
            self._update_icon(state)
            if hasattr(self, "_status_action"):
                self._status_action.setText(f"Jarvis — {state.value.title()}")
            if hasattr(self, "_focus_action"):
                self._focus_action.setChecked(state == JarvisState.FOCUS_MODE)

    def _toggle_focus_mode(self, checked: bool) -> None:
        """Toggle focus mode from tray menu."""
        if checked:
            self._event_bus.emit("tray_focus_start", None)
        else:
            self._event_bus.emit("tray_focus_stop", None)

    def _open_text_mode(self) -> None:
        """Open text mode input."""
        self._event_bus.emit("tray_text_mode", None)

    def _open_settings(self) -> None:
        """Open config file in the system editor."""
        config_path = Path(self._config.jarvis_home).expanduser() / "config.yaml"
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(config_path)])
            elif sys.platform == "win32":
                os.startfile(str(config_path))
            else:
                subprocess.Popen(["xdg-open", str(config_path)])
        except Exception:
            logger.exception("Failed to open config file")

    def _open_log(self) -> None:
        """Open today's conversation log."""
        from datetime import date

        log_path = (
            Path(self._config.conversation_dir).expanduser()
            / f"{date.today().isoformat()}.jsonl"
        )
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(log_path)])
            elif sys.platform == "win32":
                os.startfile(str(log_path))
            else:
                subprocess.Popen(["xdg-open", str(log_path)])
        except Exception:
            logger.exception("Failed to open conversation log")

    def _quit(self) -> None:
        """Quit the Jarvis application."""
        self._event_bus.emit("quit_requested", None)
        try:
            from PyQt6.QtWidgets import QApplication

            QApplication.instance().quit()
        except Exception:
            sys.exit(0)
