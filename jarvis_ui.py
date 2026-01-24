
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QRadialGradient

class JarvisOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        
    def initUI(self):
        # 1. Window Flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput 
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # 2. Geometry (Full Screen)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(0, 0, screen.width(), screen.height())

        # Labels removed per user request for cleaner UI
        # 3. Top Label "JARVIS" - REMOVED
        # 4. Bottom Label "JARVIS" - REMOVED
        # 5. Glow Effects for Text - REMOVED
        
        # Start hidden
        self.hide()
        
    def _add_glow(self, widget):
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(25)
        effect.setColor(QColor("#00E5FF"))
        effect.setOffset(0, 0)
        widget.setGraphicsEffect(effect)

    def paintEvent(self, event):
        """Draws the screen border glow."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # Create a thick border pen with some transparency for glow effect
        pen_width = 10
        pen = QPen(QColor(0, 229, 255, 180)) # Teal with alpha
        pen.setWidth(pen_width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        
        # Draw the rectangle slightly inset
        inset = pen_width // 2
        painter.drawRect(rect.adjusted(inset, inset, -inset, -inset))
        
        # Optional: Add a second thinner, brighter line for "core"
        pen.setColor(QColor(255, 255, 255, 200))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(rect.adjusted(inset, inset, -inset, -inset))

    def wake_up(self):
        self.show()
        # Optional: Add animation here (fade in)
        
    def sleep(self):
        self.hide()
