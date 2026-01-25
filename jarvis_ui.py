import sys
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, pyqtProperty, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush

class JarvisOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self._border_opacity = 0.0
        self._pulse_size = 0
        self.initUI()
        
        # Pulse Animation Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_pulse)
        self.pulse_direction = 1
        self.base_width = 10

    def initUI(self):
        # Frameless, Always on Top, Transparent for Mouse, Tool
        flags = Qt.WindowType.FramelessWindowHint | \
                Qt.WindowType.WindowStaysOnTopHint | \
                Qt.WindowType.Tool | \
                Qt.WindowType.WindowTransparentForInput
        
        # macOS specific: Remove system shadow so our glow is visible
        if sys.platform == "darwin":
            flags |= Qt.WindowType.NoDropShadowWindowHint
            
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Screen geometry
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

    @pyqtProperty(float)
    def border_opacity(self):
        return self._border_opacity

    @border_opacity.setter
    def border_opacity(self, value):
        self._border_opacity = value
        self.update()

    def update_pulse(self):
        # Animate the border width
        self._pulse_size += self.pulse_direction * 0.5
        if self._pulse_size > 10:
            self.pulse_direction = -1
        elif self._pulse_size < 0:
            self.pulse_direction = 1
        self.update()

    def paintEvent(self, event):
        if self._border_opacity <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw Blue Border with Pulse
        # Color: Cyan/Blue (0, 200, 255)
        alpha = int(self._border_opacity * 255)
        color = QColor(0, 200, 255, alpha)
        
        pen_width = self.base_width + self._pulse_size
        pen = QPen(color, pen_width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Draw rect slightly inside to account for pen width
        rect = self.rect().adjusted(int(pen_width/2), int(pen_width/2), -int(pen_width/2), -int(pen_width/2))
        painter.drawRect(rect)
        
        # Optional: Add a subtle glow (inner second rect)
        glow_color = QColor(0, 100, 255, int(alpha * 0.5))
        painter.setPen(QPen(glow_color, pen_width + 10))
        painter.drawRect(rect)

    def wake_up(self):
        """Show the overlay with animation."""
        self.show()
        self.raise_()  # Critical for macOS to ensure it's above other apps
        # Fade In
        self.anim = QPropertyAnimation(self, b"border_opacity")
        self.anim.setDuration(300) # Fast wake up
        self.anim.setStartValue(self._border_opacity)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.start()
        
        # Start Pulse
        self.timer.start(30)

    def sleep(self):
        """Hide the overlay."""
        # Fade Out
        self.anim = QPropertyAnimation(self, b"border_opacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(self._border_opacity)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self.anim.start()
        self.anim.finished.connect(self.hide_and_stop)

    def hide_and_stop(self):
        self.timer.stop()
        self.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = JarvisOverlay()
    overlay.wake_up()
    # Simulate sleep after 3 seconds
    QTimer.singleShot(3000, overlay.sleep)
    sys.exit(app.exec())
