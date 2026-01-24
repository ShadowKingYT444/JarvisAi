"""
Jarvis HUD - Voice-Controlled Focus Manager (PyQt6 Version)
Integrates Wake Word detection, Speech-to-Text, and the Deep Work Fortress Enforcer.

Features:
- Always-on-top HUD with Focus controls
- Background wake word listener ("Jarvis")
- Voice commands: "focus on [goal]", "restore tabs", etc.
- Thread-safe UI updates via Qt signals
"""

import sys
import os
import re
import threading

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wakeword.listener import WakeWordListener
from wakeword.stt import SpeechToText
from enforcer import Enforcer


class VoiceWorker(QThread):
    """Background thread for voice listening."""
    
    # Signals for thread-safe UI updates
    voice_ready = pyqtSignal()
    voice_error = pyqtSignal(str)
    wake_detected = pyqtSignal()
    command_received = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.listener = None
        self.stt = None
        self.running = True
    
    def run(self):
        """Main voice listening loop."""
        try:
            # Initialize voice components
            self.status_update.emit("Initializing voice...")
            self.listener = WakeWordListener()
            self.stt = SpeechToText()
            self.voice_ready.emit()
            
            # Main listening loop
            while self.running:
                try:
                    self.status_update.emit("🎤 Listening for 'Jarvis'...")
                    
                    # Wait for wake word
                    detected = self.listener.listen()
                    
                    if detected and self.running:
                        self.wake_detected.emit()
                        self.status_update.emit("🎙️ Listening for command...")
                        
                        # Get speech command
                        result = self.stt.listen_and_transcribe()
                        
                        if result and result.get("text"):
                            self.command_received.emit(result["text"])
                        else:
                            self.status_update.emit("❓ Could not understand. Try again.")
                            
                except Exception as e:
                    if self.running:
                        self.status_update.emit(f"Voice error: {str(e)[:50]}")
                    
        except Exception as e:
            self.voice_error.emit(str(e))
    
    def stop(self):
        """Stop the voice thread."""
        self.running = False
        if self.listener:
            try:
                self.listener.cleanup()
            except:
                pass


class EnforcerWorker(QThread):
    """Background thread for enforcer operations."""
    
    finished = pyqtSignal(dict)
    log_message = pyqtSignal(str)
    
    def __init__(self, enforcer, action: str, goal: str = ""):
        super().__init__()
        self.enforcer = enforcer
        self.action = action
        self.goal = goal
    
    def run(self):
        try:
            if self.action == "focus":
                result = self.enforcer.enforce_focus(self.goal, dry_run=False)
                self.finished.emit(result)
                
            elif self.action == "scan":
                tabs = self.enforcer.scan_tabs()
                for tab in tabs:
                    self.log_message.emit(f"  [{tab['id']}] {tab['title'][:45]}")
                self.finished.emit({"tabs": len(tabs)})
                
            elif self.action == "restore":
                result = self.enforcer.restore_session()
                self.finished.emit(result)
                
        except Exception as e:
            self.finished.emit({"error": str(e)})


class JarvisHUD(QWidget):
    """Main HUD window with voice control integration."""
    
    def __init__(self):
        super().__init__()
        
        # Enforcer instance
        self.enforcer = Enforcer(browser="chrome")
        
        # Workers
        self.voice_worker = None
        self.enforcer_worker = None
        
        # Build UI
        self.init_ui()
        
        # Start voice listener
        self.start_voice_listener()
    
    def init_ui(self):
        """Build the HUD interface."""
        # Window settings
        self.setWindowTitle("🏰 Deep Work Fortress")
        self.setFixedSize(520, 400)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Dark theme
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                color: #eaeaea;
                font-family: 'Helvetica Neue', Arial, sans-serif;
            }
            QLineEdit {
                background-color: #0f3460;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                color: #eaeaea;
            }
            QLineEdit:focus {
                border: 2px solid #e94560;
            }
            QPushButton {
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
                cursor: pointer;
            }
            QPushButton:hover {
                opacity: 0.9;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
            QTextEdit {
                background-color: #0d0d1a;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                color: #888;
            }
        """)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        self.setLayout(layout)
        
        # Title
        title = QLabel("🏰 DEEP WORK FORTRESS")
        title.setFont(QFont("Helvetica Neue", 20, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Voice status
        self.voice_status = QLabel("🎤 Initializing voice...")
        self.voice_status.setStyleSheet("color: #f39c12; font-size: 11px;")
        layout.addWidget(self.voice_status)
        
        # Goal input
        goal_label = QLabel("🎯 Current Goal:")
        goal_label.setFont(QFont("Helvetica Neue", 12))
        layout.addWidget(goal_label)
        
        self.goal_input = QLineEdit()
        self.goal_input.setPlaceholderText("Enter your focus goal...")
        self.goal_input.setText("Working on Jarvis AI agent")
        layout.addWidget(self.goal_input)
        
        # Focus button
        self.focus_btn = QPushButton("🛡️ ACTIVATE FOCUS MODE")
        self.focus_btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560;
                color: white;
                font-size: 14px;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #c13b50;
            }
        """)
        self.focus_btn.clicked.connect(self.focus_mode)
        layout.addWidget(self.focus_btn)
        
        # Secondary buttons
        btn_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("📑 Scan Tabs")
        self.scan_btn.setStyleSheet("background-color: #0f3460; color: #eaeaea;")
        self.scan_btn.clicked.connect(self.scan_tabs)
        btn_layout.addWidget(self.scan_btn)
        
        self.restore_btn = QPushButton("🔄 Restore Tabs")
        self.restore_btn.setStyleSheet("background-color: #0f3460; color: #eaeaea;")
        self.restore_btn.clicked.connect(self.restore_session)
        btn_layout.addWidget(self.restore_btn)
        
        layout.addLayout(btn_layout)
        
        # Status label
        self.status_label = QLabel("Ready. Say 'Jarvis' to activate voice control.")
        self.status_label.setStyleSheet("color: #666; font-size: 10px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # Results log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        layout.addWidget(self.log_text)
    
    def start_voice_listener(self):
        """Start the background voice listener."""
        self.voice_worker = VoiceWorker()
        self.voice_worker.voice_ready.connect(self.on_voice_ready)
        self.voice_worker.voice_error.connect(self.on_voice_error)
        self.voice_worker.wake_detected.connect(self.on_wake_detected)
        self.voice_worker.command_received.connect(self.handle_voice_command)
        self.voice_worker.status_update.connect(self.set_status)
        self.voice_worker.start()
    
    def on_voice_ready(self):
        """Called when voice is initialized."""
        self.voice_status.setText("🎤 Voice active - Say 'Jarvis'")
        self.voice_status.setStyleSheet("color: #00d26a; font-size: 11px;")
        self.set_status("Voice control ready. Say 'Jarvis' followed by a command.")
    
    def on_voice_error(self, error: str):
        """Called on voice initialization error."""
        self.voice_status.setText(f"🎤 Voice error: {error[:40]}")
        self.voice_status.setStyleSheet("color: #e94560; font-size: 11px;")
    
    def on_wake_detected(self):
        """Called when wake word is detected."""
        self.voice_status.setText("🎙️ Listening for command...")
        self.voice_status.setStyleSheet("color: #f39c12; font-size: 11px;")
    
    def handle_voice_command(self, text: str):
        """Process a voice command."""
        text_lower = text.lower().strip()
        self.set_status(f'Heard: "{text}"')
        self.log(f"Voice: {text}")
        
        # Reset voice indicator
        self.voice_status.setText("🎤 Voice active - Say 'Jarvis'")
        self.voice_status.setStyleSheet("color: #00d26a; font-size: 11px;")
        
        # Check for "focus on [goal]"
        focus_patterns = [
            r"focus on (.+)",
            r"set goal (.+)",
            r"set focus (.+)",
            r"work on (.+)",
            r"working on (.+)",
            r"focus mode (.+)",
        ]
        
        for pattern in focus_patterns:
            match = re.search(pattern, text_lower)
            if match:
                goal = match.group(1).strip()
                goal = goal[0].upper() + goal[1:] if goal else goal
                
                self.set_status(f"🎯 Setting goal: {goal}")
                self.goal_input.setText(goal)
                self.focus_mode()
                return
        
        # Check for "restore" commands
        restore_patterns = ["restore", "bring back", "undo", "recover tabs", "open backup"]
        for pattern in restore_patterns:
            if pattern in text_lower:
                self.restore_session()
                return
        
        # Check for "scan" commands
        scan_patterns = ["scan tabs", "show tabs", "list tabs", "what tabs"]
        for pattern in scan_patterns:
            if pattern in text_lower:
                self.scan_tabs()
                return
        
        # No command matched
        self.set_status(f'Heard: "{text}" - Try "focus on [goal]" or "restore tabs"')
    
    def set_status(self, message: str):
        """Update status label."""
        self.status_label.setText(message)
    
    def log(self, message: str):
        """Add message to log."""
        self.log_text.append(message)
    
    def focus_mode(self):
        """Activate focus mode."""
        goal = self.goal_input.text().strip()
        if not goal:
            self.set_status("⚠️ Please enter a goal first.")
            return
        
        self.set_status(f"🛡️ Activating Focus Mode...")
        self.focus_btn.setEnabled(False)
        self.focus_btn.setText("⏳ Processing...")
        self.log(f"\n--- Focus Mode: {goal} ---")
        
        self.enforcer_worker = EnforcerWorker(self.enforcer, "focus", goal)
        self.enforcer_worker.finished.connect(self.on_focus_complete)
        self.enforcer_worker.log_message.connect(self.log)
        self.enforcer_worker.start()
    
    def on_focus_complete(self, result: dict):
        """Called when focus mode completes."""
        self.focus_btn.setEnabled(True)
        self.focus_btn.setText("🛡️ ACTIVATE FOCUS MODE")
        
        if "error" in result:
            self.set_status(f"❌ Error: {result['error']}")
            self.log(f"Error: {result['error']}")
        else:
            closed = result.get("closed", 0)
            kept = result.get("kept", 0)
            self.set_status(f"✅ Closed {closed} distractions, kept {kept} tabs")
            self.log(f"Closed: {closed}, Kept: {kept}")
            
            for title in result.get("tabs_closed", []):
                self.log(f"  🚫 {title[:45]}")
    
    def scan_tabs(self):
        """Scan current tabs."""
        self.set_status("📑 Scanning tabs...")
        self.log("\n--- Scanning Tabs ---")
        
        self.enforcer_worker = EnforcerWorker(self.enforcer, "scan")
        self.enforcer_worker.finished.connect(self.on_scan_complete)
        self.enforcer_worker.log_message.connect(self.log)
        self.enforcer_worker.start()
    
    def on_scan_complete(self, result: dict):
        """Called when scan completes."""
        if "error" in result:
            self.set_status(f"❌ Error: {result['error']}")
        else:
            self.set_status(f"📑 Found {result.get('tabs', 0)} tabs")
    
    def restore_session(self):
        """Restore closed tabs."""
        self.set_status("🔄 Restoring tabs...")
        self.log("\n--- Restoring Tabs ---")
        
        self.enforcer_worker = EnforcerWorker(self.enforcer, "restore")
        self.enforcer_worker.finished.connect(self.on_restore_complete)
        self.enforcer_worker.log_message.connect(self.log)
        self.enforcer_worker.start()
    
    def on_restore_complete(self, result: dict):
        """Called when restore completes."""
        if "error" in result:
            self.set_status(f"❌ {result['error']}")
            self.log(result['error'])
        else:
            restored = result.get("restored", 0)
            if restored > 0:
                self.set_status(f"✅ Restored {restored} tabs")
                self.log(f"Restored {restored} tabs")
            else:
                self.set_status("📭 No tabs to restore")
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.voice_worker:
            self.voice_worker.stop()
            self.voice_worker.wait(1000)
        event.accept()


def main():
    """Entry point."""
    app = QApplication(sys.argv)
    
    # Set app-wide font
    app.setFont(QFont("Helvetica Neue", 11))
    
    hud = JarvisHUD()
    hud.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
