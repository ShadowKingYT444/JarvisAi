
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame, QScrollArea, QApplication
from PyQt6.QtCore import Qt, pyqtProperty, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QPainter

class ScribeOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.notes = []

    def initUI(self):
        # Frameless, Always on Top, Tool
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput  # Initially transparent for input so it doesn't block clicks unless we want it to
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Position: Top Right? Bottom Right? Let's go with Top Right for now, acting like a HUD.
        screen = QApplication.primaryScreen().availableGeometry()
        width = 400
        height = 600
        self.setGeometry(screen.width() - width - 20, 50, width, height)
        
        # Main Layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Glass Frame
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(10, 10, 20, 200);
                border: 1px solid rgba(100, 200, 255, 50);
                border-radius: 15px;
            }
        """)
        frame_layout = QVBoxLayout()
        self.frame.setLayout(frame_layout)
        layout.addWidget(self.frame)
        
        # Header
        header = QLabel("Ghost Writer 👻")
        header.setStyleSheet("color: #00E5FF; font-weight: bold; font-size: 14pt; background: transparent; border: none;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(header)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 30);")
        frame_layout.addWidget(sep)
        
        # Notes Container (Scrollable)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 5px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 50); border-radius: 2px; }
        """)
        
        self.notes_container = QWidget()
        self.notes_container.setStyleSheet("background: transparent;")
        self.notes_layout = QVBoxLayout()
        self.notes_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.notes_container.setLayout(self.notes_layout)
        self.scroll_area.setWidget(self.notes_container)
        
        frame_layout.addWidget(self.scroll_area)
        
        # Initial Placeholder
        self.placeholder = QLabel("Watching for insights...")
        self.placeholder.setStyleSheet("color: #888; font-style: italic; margin-top: 20px;")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notes_layout.addWidget(self.placeholder)
        
    def add_note(self, text):
        if self.placeholder:
            self.notes_layout.removeWidget(self.placeholder)
            self.placeholder.deleteLater()
            self.placeholder = None
            
        note_frame = QFrame()
        note_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 10);
                border-radius: 8px;
                padding: 5px;
                margin-bottom: 5px;
            }
        """)
        note_layout = QVBoxLayout()
        note_frame.setLayout(note_layout)
        
        note_label = QLabel(text)
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: #eee; font-size: 10pt; background: transparent; border: none;")
        note_layout.addWidget(note_label)
        
        # Insert at top
        self.notes_layout.insertWidget(0, note_frame)
        self.notes.append(text)
        
        # Flash effect?
        self.flash_frame()

    def flash_frame(self):
        # TODO: Add a subtle flash animation to indicate update
        pass

    def clear_notes(self):
        while self.notes_layout.count():
            child = self.notes_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.notes = []
        
        self.placeholder = QLabel("Watching for insights...")
        self.placeholder.setStyleSheet("color: #888; font-style: italic; margin-top: 20px;")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notes_layout.addWidget(self.placeholder)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    overlay = ScribeOverlay()
    overlay.show()
    overlay.add_note("Found solution for React Hook error: Use dependency array []")
    sys.exit(app.exec())
