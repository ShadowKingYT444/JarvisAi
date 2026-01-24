import math
from PyQt6.QtWidgets import QWidget, QLabel, QApplication, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QRadialGradient, QPainterPath

class JarvisOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.phase = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.setInterval(16) # ~60 FPS
        
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
        """Draws a dynamic dark blue sine wave border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        
        # Wave Parameters
        amplitude = 10     # Pixel height of wave
        frequency = 0.05   # How tight the waves are
        step = 20          # Pixel step for optimization (lower = smoother, higher = faster)
        base_inset = 20    # Base distance from edge
        
        # Current Phase
        self.phase += 0.2
        if self.phase > math.pi * 2:
            self.phase -= math.pi * 2
            
        path = QPainterPath()
        
        # --- 1. Top Edge (Left to Right) ---
        # Start at top-left
        path.moveTo(0, base_inset + math.sin(0 * frequency + self.phase) * amplitude)
        
        for x in range(0, width, step):
            y_offset = math.sin(x * frequency + self.phase) * amplitude
            path.lineTo(x, base_inset + y_offset)
        path.lineTo(width, base_inset + math.sin(width * frequency + self.phase) * amplitude)

        # --- 2. Right Edge (Top to Bottom) ---
        for y in range(0, height, step):
            x_offset = math.sin(y * frequency + self.phase) * amplitude
            # Inset from right side
            path.lineTo(width - base_inset + x_offset, y)
        path.lineTo(width - base_inset + math.sin(height * frequency + self.phase) * amplitude, height)

        # --- 3. Bottom Edge (Right to Left) ---
        for x in range(width, 0, -step):
            y_offset = math.sin(x * frequency + self.phase) * amplitude
            # Inset from bottom
            path.lineTo(x, height - base_inset + y_offset)
        path.lineTo(0, height - base_inset + math.sin(0 * frequency + self.phase) * amplitude)

        # --- 4. Left Edge (Bottom to Top) ---
        for y in range(height, 0, -step):
            x_offset = math.sin(y * frequency + self.phase) * amplitude
            path.lineTo(base_inset + x_offset, y)
        path.lineTo(base_inset + math.sin(0 * frequency + self.phase) * amplitude, 0)
        
        path.closeSubpath()

        # Styles
        # "Dark blue and vibrant... like dark blue waves"
        # Core Color: Deep Electric Blue
        color_core = QColor("#2962FF") # Vibrant Deep Blue
        color_glow = QColor("#00B0FF") # Lighter Blue/Cyan for glow
        
        # Oscillate opacity for "breathing" life
        pulse = (math.sin(self.phase * 0.5) + 1) / 2
        alpha = int(180 + (75 * pulse))
        color_core.setAlpha(alpha)

        # 1. Draw Glow (Thick, transparent)
        pen_glow = QPen(color_glow)
        pen_glow.setWidth(15)
        pen_glow.setColor(QColor(0, 229, 255, 60)) # Cyan glow, very transparent
        pen_glow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen_glow)
        painter.drawPath(path)

        # 2. Draw Core (Thinner, solid)
        pen_core = QPen(color_core)
        pen_core.setWidth(6)
        pen_core.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen_core)
        painter.drawPath(path)

    def wake_up(self):
        self.show()
        self.timer.start()
        
    def sleep(self):
        self.timer.stop()
        self.hide()
