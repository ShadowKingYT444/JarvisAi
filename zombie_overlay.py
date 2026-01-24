from PyQt6.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QBrush, QFont

class ZombieOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self._opacity_level = 0.0

    def initUI(self):
        # Frameless, Always on Top, Transparent for Mouse, Tool
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Screen geometry
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        
        # UI Elements (Optional "Wake Up" text)
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.label = QLabel("⚠️ ZOMBIE MODE DETECTED ⚠️")
        self.label.setStyleSheet("color: rgba(255, 50, 50, 200); font-weight: bold; font-size: 30pt;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.label.hide() # Initially hidden

    @pyqtProperty(float)
    def opacity_level(self):
        return self._opacity_level

    @opacity_level.setter
    def opacity_level(self, value):
        self._opacity_level = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._opacity_level > 0:
            # Draw semi-transparent black overlay
            # Max alpha 230 out of 255 (very dark)
            alpha = int(self._opacity_level * 230)
            painter.fillRect(self.rect(), QColor(20, 20, 20, alpha))

    def fade_in(self):
        """Slowly fade in the darkness."""
        self.show()
        self.anim = QPropertyAnimation(self, b"opacity_level")
        self.anim.setDuration(5000) # 5 seconds to fade to black
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.start()
        
        # Show label halfway
        QTimer.singleShot(2500, self.label.show)

    def fade_out(self):
        """Restore screen."""
        self.anim = QPropertyAnimation(self, b"opacity_level")
        self.anim.setDuration(1000)
        self.anim.setStartValue(self._opacity_level)
        self.anim.setEndValue(0.0)
        self.anim.start()
        self.label.hide()
        self.anim.finished.connect(self.hide)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    overlay = ZombieOverlay()
    overlay.fade_in()
    sys.exit(app.exec())
