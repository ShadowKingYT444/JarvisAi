
import sys
import os
import asyncio
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QLabel, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
import PIL.ImageGrab
import pyautogui
from io import BytesIO

# Import the agent logic

# Import the agent logic
# from agent_logic import agent_service (FIXME: agent_logic missing, suspect agent.py)

class AgentWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, command, screenshot):
        super().__init__()
        self.command = command
        self.screenshot = screenshot

    def run(self):
        # Create a new event loop for this thread or run in a new loop
        try:
            # loop = asyncio.new_event_loop()
            # asyncio.set_event_loop(loop)
            # result = loop.run_until_complete(agent_service.process_request(self.command, self.screenshot))
            # loop.close()
            result = "Agent connection temporarily disabled for refactoring."
            self.finished.emit(str(result))
        except Exception as e:
            self.finished.emit(f"Error in worker: {e}")

class AgentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.worker = None

    def initUI(self):
        # Window Flags for frameless, always on top, tool window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        
        # Translucent Background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Main Frame (Glassmorphism look)
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 220);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 15px;
            }
        """)
        frame_layout = QVBoxLayout()
        self.frame.setLayout(frame_layout)
        layout.addWidget(self.frame)

        # Status Label
        self.status_label = QLabel("AI Agent Ready (Ctrl+Shift+Space)")
        self.status_label.setStyleSheet("color: #aaaaaa; font-size: 10pt; background: transparent; border: none;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.status_label)

        # Input Field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 50);
                color: white;
                border: none;
                border-bottom: 2px solid #0078d7;
                font-size: 14pt;
                padding: 5px;
            }
            QLineEdit:focus {
                border-bottom: 2px solid #00aaff;
            }
        """)
        self.input_field.returnPressed.connect(self.process_command)
        frame_layout.addWidget(self.input_field)

        # Sizing and Positioning
        self.resize(600, 100)
        self.center_on_screen()

    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y // 2)

    def activate_overlay(self):
        """Captures screen and shows overlay"""
        try:
            # Capture screen BEFORE showing the overlay to get clean context
            self.current_screenshot = PIL.ImageGrab.grab()
        except Exception as e:
            print(f"Error capturing: {e}")
            self.current_screenshot = None

        self.center_on_screen()
        self.show()
        self.activateWindow()
        self.raise_()
        self.input_field.setFocus()
        self.status_label.setText("AI Agent Ready (Ctrl+Shift+Space)")

    def process_command(self):
        command = self.input_field.text()
        if not command:
            return

        self.input_field.setDisabled(False) # Keep enabled but clear? No, disable to prevent double submit.
        # Actually user wants it to close immediately.
        
        # Hide immediately
        self.hide()
        QApplication.processEvents()
        
        try:
            # Use pre-captured screenshot
            if not hasattr(self, 'current_screenshot') or self.current_screenshot is None:
                self.current_screenshot = PIL.ImageGrab.grab()

            # Run Agent in background thread
            self.worker = AgentWorker(command, self.current_screenshot)
            self.worker.finished.connect(self.on_agent_finished)
            self.worker.start()

        except Exception as e:
            self.show()
            self.status_label.setText(f"Error processing: {e}")

    def on_agent_finished(self, result):
        self.input_field.setText("")
        # Optional: Show a small notification or just stay hidden?
        # User said: "make sure the textobx closes RIGHT AFTER the user hits enter... otherwise it is inconvient"
        # But if we stay hidden, how does user know it finished?
        # Maybe pop up for 1 second? Or just do nothing.
        # I'll just clear the input and be ready for next hotkey.
        print(f"Agent finished: {result}") # Console log

