"""Animated arc reactor widget for Jarvis visual feedback.

A QPainter-based animated orb that changes color and animation style
based on the current Jarvis state. Inspired by the JARVIS HUD from
the Iron Man films.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import (
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

# ---------------------------------------------------------------------------
# State colour palette
# ---------------------------------------------------------------------------

STATE_COLORS: dict[str, QColor] = {
    "idle": QColor(0, 120, 215),
    "initializing": QColor(0, 188, 212),
    "listening": QColor(0, 200, 83),
    "processing": QColor(255, 179, 0),
    "speaking": QColor(0, 210, 211),
    "error": QColor(234, 67, 53),
    "focus_mode": QColor(156, 39, 176),
}

_DEFAULT_STATE = "idle"


# ---------------------------------------------------------------------------
# Internal orb canvas (draws only the reactor graphic)
# ---------------------------------------------------------------------------

class _OrbCanvas(QWidget):
    """Low-level QPainter canvas for the arc reactor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(120, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Colour state
        self._color = QColor(STATE_COLORS[_DEFAULT_STATE])
        self._target_color = QColor(STATE_COLORS[_DEFAULT_STATE])
        self._state: str = _DEFAULT_STATE

        # Animation accumulators
        self._phase: float = 0.0
        self._rotation: float = 0.0
        self._pulse: float = 0.0

        # 30 FPS tick
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        # Smooth colour transition via QPropertyAnimation
        self._color_anim = QPropertyAnimation(self, b"orb_color")
        self._color_anim.setDuration(300)

    # ------------------------------------------------------------------
    # Qt property so QPropertyAnimation can interpolate the colour
    # ------------------------------------------------------------------

    def _get_orb_color(self) -> QColor:
        return self._color

    def _set_orb_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    orb_color = pyqtProperty(QColor, fget=_get_orb_color, fset=_set_orb_color)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Transition to *state* (lowercase key into STATE_COLORS)."""
        state = state.lower()
        if state not in STATE_COLORS:
            state = _DEFAULT_STATE
        self._state = state
        self._target_color = QColor(STATE_COLORS[state])
        self._color_anim.stop()
        self._color_anim.setStartValue(self._color)
        self._color_anim.setEndValue(self._target_color)
        self._color_anim.start()

    # ------------------------------------------------------------------
    # Animation tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._phase += 0.05

        state = self._state
        if state == "idle":
            self._pulse = math.sin(self._phase) * 3.0
        elif state == "initializing":
            self._pulse = math.sin(self._phase * 1.7) * 7.0
            self._rotation = (self._rotation + 5.0) % 360.0
        elif state == "listening":
            self._pulse = math.sin(self._phase * 2.0) * 5.0
        elif state == "processing":
            self._pulse = math.sin(self._phase) * 2.0
            self._rotation = (self._rotation + 3.0) % 360.0
        elif state == "speaking":
            self._pulse = math.sin(self._phase * 1.5) * 6.0
        elif state == "error":
            self._pulse = abs(math.sin(self._phase * 4.0)) * 8.0
        elif state == "focus_mode":
            self._pulse = math.sin(self._phase * 0.5) * 2.0
        else:
            self._pulse = 0.0

        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        base_radius = 40.0
        color = self._color

        # 1. Outer glow (pulsing radial gradient) ----------------------
        glow_radius = base_radius + 18.0 + self._pulse
        grad = QRadialGradient(cx, cy, glow_radius)
        glow_color = QColor(color)
        glow_color.setAlpha(80)
        grad.setColorAt(0.0, glow_color)
        glow_mid = QColor(color)
        glow_mid.setAlpha(30)
        grad.setColorAt(0.6, glow_mid)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QRectF(
            cx - glow_radius, cy - glow_radius,
            glow_radius * 2, glow_radius * 2,
        ))
        painter.restore()

        # 2. Outer ring -------------------------------------------------
        ring_radius = base_radius + 4.0 + self._pulse * 0.3
        pen = QPen(QColor(color))
        pen.setWidthF(1.5)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(
            cx - ring_radius, cy - ring_radius,
            ring_radius * 2, ring_radius * 2,
        ))
        painter.restore()

        # 3. Inner arc segments (rotate during PROCESSING) --------------
        seg_radius = base_radius - 2.0
        seg_rect = QRectF(
            cx - seg_radius, cy - seg_radius,
            seg_radius * 2, seg_radius * 2,
        )
        seg_pen = QPen(QColor(color))
        seg_pen.setWidthF(2.5)
        seg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter.save()
        painter.setPen(seg_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        num_segments = 4
        gap_deg = 12.0
        arc_span = (360.0 / num_segments) - gap_deg
        for i in range(num_segments):
            start_angle = self._rotation + i * (360.0 / num_segments)
            # QPainter angles are in 1/16th of a degree
            painter.drawArc(
                seg_rect,
                int(start_angle * 16),
                int(arc_span * 16),
            )
        painter.restore()

        # 4. Core (solid centre) ----------------------------------------
        core_radius = base_radius * 0.45
        core_grad = QRadialGradient(cx, cy, core_radius)
        bright = QColor(color)
        bright.setAlpha(220)
        core_grad.setColorAt(0.0, bright)
        dim = QColor(color)
        dim.setAlpha(140)
        core_grad.setColorAt(1.0, dim)

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core_grad)
        painter.drawEllipse(QRectF(
            cx - core_radius, cy - core_radius,
            core_radius * 2, core_radius * 2,
        ))
        painter.restore()

        # 5. Highlight (3-D glass effect) -------------------------------
        hl_radius = core_radius * 0.35
        hl_x = cx - core_radius * 0.28
        hl_y = cy - core_radius * 0.32

        hl_grad = QRadialGradient(hl_x, hl_y, hl_radius)
        hl_grad.setColorAt(0.0, QColor(255, 255, 255, 180))
        hl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(hl_grad)
        painter.drawEllipse(QRectF(
            hl_x - hl_radius, hl_y - hl_radius,
            hl_radius * 2, hl_radius * 2,
        ))
        painter.restore()

        painter.end()


# ---------------------------------------------------------------------------
# Public composite widget (orb + status label)
# ---------------------------------------------------------------------------

class ArcReactorWidget(QWidget):
    """Animated arc reactor orb with an optional status text label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._orb = _OrbCanvas(self)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._label.setFont(QFont("Segoe UI", 9))
        self._label.setStyleSheet("color: #aaaaaa; background: transparent;")
        self._label.setWordWrap(True)
        self._label.setFixedWidth(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._orb, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignHCenter)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Change the reactor colour / animation to match *state*."""
        self._orb.set_state(state)

    def set_text(self, text: str) -> None:
        """Update the status label below the orb."""
        self._label.setText(text)
