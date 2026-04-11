"""GUI Installer Wizard for Jarvis.

A 5-page QWizard that walks users through setup: platform detection,
API key entry with validation, preferences, clap calibration, and
auto-start installation.
"""

from __future__ import annotations

import importlib
import logging
import platform
import subprocess
import sys
from pathlib import Path

from jarvis.shared.config import JarvisConfig

logger = logging.getLogger(__name__)

# Required packages to check
REQUIRED_PACKAGES = [
    ("sounddevice", "sounddevice"),
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("webrtcvad", "webrtcvad"),
    ("faster_whisper", "faster-whisper"),
    ("google.generativeai", "google-generativeai"),
    ("pyttsx3", "pyttsx3"),
    ("yaml", "pyyaml"),
    ("dotenv", "python-dotenv"),
    ("aiofiles", "aiofiles"),
    ("pyperclip", "pyperclip"),
]

OPTIONAL_PACKAGES = [
    ("PyQt6", "PyQt6"),
    ("elevenlabs", "elevenlabs"),
]

DARK_STYLESHEET = """
    QWizard, QWizardPage {
        background-color: #1e1e2e;
        color: #cdd6f4;
    }
    QLabel {
        color: #cdd6f4;
    }
    QLineEdit, QComboBox, QTextEdit, QSpinBox {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px;
    }
    QLineEdit:focus, QComboBox:focus {
        border: 1px solid #89b4fa;
    }
    QPushButton {
        background-color: #45475a;
        color: #cdd6f4;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
    }
    QPushButton:hover {
        background-color: #585b70;
    }
    QPushButton:pressed {
        background-color: #313244;
    }
    QCheckBox {
        color: #cdd6f4;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
    }
    QSlider::groove:horizontal {
        background: #313244;
        height: 6px;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #89b4fa;
        width: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }
    QProgressBar {
        background-color: #313244;
        border: none;
        border-radius: 4px;
        text-align: center;
        color: #cdd6f4;
    }
    QProgressBar::chunk {
        background-color: #89b4fa;
        border-radius: 4px;
    }
"""


def check_dependencies() -> tuple[list[str], list[str]]:
    """Check which packages are installed.

    Returns (missing_required, missing_optional).
    """
    missing_req = []
    missing_opt = []
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing_req.append(pip_name)
    for import_name, pip_name in OPTIONAL_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing_opt.append(pip_name)
    return missing_req, missing_opt


def validate_gemini_key(key: str) -> bool:
    """Test if a Gemini API key is valid."""
    if not key or len(key) < 10:
        return False
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        list(genai.list_models())
        return True
    except Exception:
        return False


def install_gui() -> None:
    """Launch the GUI installer wizard."""
    try:
        from PyQt6.QtCore import Qt, QThread, pyqtSignal
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QSlider,
            QTextEdit,
            QVBoxLayout,
            QWizard,
            QWizardPage,
        )
    except ImportError:
        print("PyQt6 is not installed. Running CLI installer instead.")
        from jarvis.daemon.installer import install
        install()
        return

    app = QApplication.instance() or QApplication(sys.argv)

    # -- Page 1: Welcome --
    class WelcomePage(QWizardPage):
        def __init__(self):
            super().__init__()
            self.setTitle("Welcome to Jarvis AI")
            self.setSubTitle("This wizard will set up Jarvis on your system.")

            layout = QVBoxLayout(self)

            info = QLabel(
                f"<b>Platform:</b> {platform.system()} ({platform.machine()})<br>"
                f"<b>Python:</b> {sys.version.split()[0]}<br>"
            )
            info.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(info)

            py_ok = sys.version_info >= (3, 11)
            if py_ok:
                status = QLabel("Python 3.11+ requirement met.")
                status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            else:
                status = QLabel(
                    f"Warning: Python 3.11+ recommended (you have {sys.version_info.major}.{sys.version_info.minor})"
                )
                status.setStyleSheet("color: #fab387; font-weight: bold;")
            layout.addWidget(status)

            # Dependency check
            layout.addWidget(QLabel("\n<b>Checking dependencies...</b>"))
            missing_req, missing_opt = check_dependencies()

            if not missing_req:
                dep_label = QLabel("All required packages installed.")
                dep_label.setStyleSheet("color: #a6e3a1;")
            else:
                dep_label = QLabel(
                    f"Missing required: {', '.join(missing_req)}\n"
                    f"Run: pip install {' '.join(missing_req)}"
                )
                dep_label.setStyleSheet("color: #f38ba8;")
                dep_label.setWordWrap(True)
            layout.addWidget(dep_label)

            if missing_opt:
                opt_label = QLabel(f"Optional (not installed): {', '.join(missing_opt)}")
                opt_label.setStyleSheet("color: #9399b2;")
                layout.addWidget(opt_label)

            layout.addStretch()

    # -- Page 2: API Keys --
    class APIKeyPage(QWizardPage):
        def __init__(self):
            super().__init__()
            self.setTitle("API Keys")
            self.setSubTitle("Enter your API keys. These are stored locally in ~/.jarvis/.env")

            layout = QFormLayout(self)

            self.gemini_key = QLineEdit()
            self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.gemini_key.setPlaceholderText("Required -- from ai.google.dev")
            layout.addRow("Gemini API Key:", self.gemini_key)

            self.gemini_status = QLabel("")
            validate_btn = QPushButton("Validate Key")
            validate_btn.clicked.connect(self._validate_gemini)
            key_row = QHBoxLayout()
            key_row.addWidget(validate_btn)
            key_row.addWidget(self.gemini_status)
            layout.addRow("", key_row)

            self.elevenlabs_key = QLineEdit()
            self.elevenlabs_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.elevenlabs_key.setPlaceholderText("Optional -- for premium TTS")
            layout.addRow("ElevenLabs Key:", self.elevenlabs_key)

        def _validate_gemini(self):
            key = self.gemini_key.text().strip()
            if not key:
                self.gemini_status.setText("Enter a key first")
                self.gemini_status.setStyleSheet("color: #fab387;")
                return
            self.gemini_status.setText("Validating...")
            self.gemini_status.setStyleSheet("color: #9399b2;")
            QApplication.processEvents()

            if validate_gemini_key(key):
                self.gemini_status.setText("Valid!")
                self.gemini_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            else:
                self.gemini_status.setText("Invalid key")
                self.gemini_status.setStyleSheet("color: #f38ba8; font-weight: bold;")

    # -- Page 3: Preferences --
    class PreferencesPage(QWizardPage):
        def __init__(self):
            super().__init__()
            self.setTitle("Preferences")
            self.setSubTitle("Configure Jarvis behavior.")

            layout = QFormLayout(self)

            self.tts_engine = QComboBox()
            tts_opts = ["pyttsx3"]
            if platform.system() == "Darwin":
                tts_opts.insert(0, "macos_say")
            tts_opts.append("elevenlabs")
            self.tts_engine.addItems(tts_opts)
            layout.addRow("TTS Engine:", self.tts_engine)

            self.tts_voice = QLineEdit("Daniel" if platform.system() == "Darwin" else "")
            layout.addRow("TTS Voice:", self.tts_voice)

            self.whisper_model = QComboBox()
            self.whisper_model.addItems(["tiny.en", "base.en", "small.en", "medium.en"])
            self.whisper_model.setCurrentText("base.en")
            self.ram_label = QLabel("~130 MB RAM")
            self.whisper_model.currentTextChanged.connect(
                lambda t: self.ram_label.setText(
                    {"tiny.en": "~40 MB RAM", "base.en": "~130 MB RAM",
                     "small.en": "~250 MB RAM", "medium.en": "~500 MB RAM"}.get(t, "")
                )
            )
            model_row = QHBoxLayout()
            model_row.addWidget(self.whisper_model)
            model_row.addWidget(self.ram_label)
            layout.addRow("STT Model:", model_row)

            self.sensitivity = QSlider(Qt.Orientation.Horizontal)
            self.sensitivity.setRange(0, 100)
            self.sensitivity.setValue(70)
            self.sens_label = QLabel("0.70")
            self.sensitivity.valueChanged.connect(
                lambda v: self.sens_label.setText(f"{v / 100:.2f}")
            )
            sens_row = QHBoxLayout()
            sens_row.addWidget(self.sensitivity)
            sens_row.addWidget(self.sens_label)
            layout.addRow("Clap Sensitivity:", sens_row)

    # -- Page 4: Calibration --
    class CalibrationPage(QWizardPage):
        def __init__(self):
            super().__init__()
            self.setTitle("Clap Calibration")
            self.setSubTitle("Test double-clap detection.")

            layout = QVBoxLayout(self)

            self.status_label = QLabel(
                "Click 'Calibrate' to measure ambient noise, then test with a double-clap."
            )
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)

            self.progress = QProgressBar()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            layout.addWidget(self.progress)

            btn_row = QHBoxLayout()
            self.calibrate_btn = QPushButton("Calibrate (3 seconds)")
            self.calibrate_btn.clicked.connect(self._run_calibration)
            btn_row.addWidget(self.calibrate_btn)

            self.test_btn = QPushButton("Test Double-Clap")
            self.test_btn.setEnabled(False)
            self.test_btn.clicked.connect(self._test_clap)
            btn_row.addWidget(self.test_btn)
            layout.addLayout(btn_row)

            self.result_label = QLabel("")
            layout.addWidget(self.result_label)
            layout.addStretch()

            self._calibrated = False
            self._detector = None

        def _run_calibration(self):
            self.calibrate_btn.setEnabled(False)
            self.status_label.setText("Be quiet for 3 seconds...")
            self.progress.setValue(0)
            QApplication.processEvents()

            try:
                from jarvis.activation.clap_detector import ClapDetector

                self._detector = ClapDetector(on_clap=lambda: None)
                # Simulate progress (calibrate blocks for 3s)
                import threading
                def _cal():
                    self._detector.calibrate()
                t = threading.Thread(target=_cal, daemon=True)
                t.start()

                import time
                for i in range(30):
                    time.sleep(0.1)
                    self.progress.setValue(int((i + 1) / 30 * 100))
                    QApplication.processEvents()

                t.join(timeout=5)
                self._calibrated = True
                self.status_label.setText("Calibration complete! Now test with a double-clap.")
                self.test_btn.setEnabled(True)
                self.result_label.setText("")
            except Exception as e:
                self.status_label.setText(f"Calibration failed: {e}")
                self.status_label.setStyleSheet("color: #f38ba8;")
            finally:
                self.calibrate_btn.setEnabled(True)

        def _test_clap(self):
            if not self._detector:
                return

            self.result_label.setText("Listening for double-clap (5 seconds)...")
            self.result_label.setStyleSheet("color: #9399b2;")
            QApplication.processEvents()

            detected = False

            def on_clap():
                nonlocal detected
                detected = True

            self._detector._on_clap = on_clap
            self._detector.start()

            import time
            for _ in range(50):  # 5 seconds
                time.sleep(0.1)
                QApplication.processEvents()
                if detected:
                    break

            self._detector.stop()

            if detected:
                self.result_label.setText("Double-clap detected! Everything works.")
                self.result_label.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            else:
                self.result_label.setText("No clap detected. Try adjusting sensitivity or clapping louder.")
                self.result_label.setStyleSheet("color: #fab387;")

    # -- Page 5: Finish --
    class FinishPage(QWizardPage):
        def __init__(self, wizard_ref):
            super().__init__()
            self._wizard_ref = wizard_ref
            self.setTitle("Installation Complete")
            self.setSubTitle("Jarvis is ready to use!")

            layout = QVBoxLayout(self)

            self.summary = QTextEdit()
            self.summary.setReadOnly(True)
            layout.addWidget(self.summary)

            self.auto_start_cb = QCheckBox("Start Jarvis on login")
            self.auto_start_cb.setChecked(True)
            layout.addWidget(self.auto_start_cb)

            self.start_now_cb = QCheckBox("Start Jarvis now")
            self.start_now_cb.setChecked(True)
            layout.addWidget(self.start_now_cb)

        def initializePage(self):
            """Perform the actual installation when this page is shown."""
            wizard = self._wizard_ref
            api_page = wizard.page(1)
            pref_page = wizard.page(2)

            # Build config from wizard data
            config = JarvisConfig(
                gemini_api_key=api_page.gemini_key.text().strip(),
                elevenlabs_api_key=api_page.elevenlabs_key.text().strip(),
                tts_engine=pref_page.tts_engine.currentText(),
                tts_voice=pref_page.tts_voice.text() or "Daniel",
                whisper_model_size=pref_page.whisper_model.currentText(),
                clap_sensitivity=pref_page.sensitivity.value() / 100.0,
                gemini_model="gemini-2.0-flash",
            )

            # Run installation
            config.ensure_dirs()
            config.save()
            config.save_env()

            summary_lines = [
                f"Config saved to: ~/.jarvis/config.yaml",
                f"API keys saved to: ~/.jarvis/.env",
                f"TTS engine: {config.tts_engine}",
                f"STT model: {config.whisper_model_size}",
                f"Clap sensitivity: {config.clap_sensitivity:.2f}",
                "",
            ]

            if self.auto_start_cb.isChecked():
                try:
                    from jarvis.daemon.installer import install
                    install()
                    summary_lines.append("Auto-start installed.")
                except Exception as e:
                    summary_lines.append(f"Auto-start failed: {e}")
            else:
                summary_lines.append("Auto-start skipped.")

            summary_lines.append("\nRun 'jarvis start' to begin.")
            self.summary.setPlainText("\n".join(summary_lines))

            # Store config for post-finish actions
            self._config = config

    # -- Build the wizard --
    wizard = QWizard()
    wizard.setWindowTitle("Jarvis AI -- Setup Wizard")
    wizard.setMinimumSize(600, 450)
    wizard.setStyleSheet(DARK_STYLESHEET)

    wizard.addPage(WelcomePage())
    wizard.addPage(APIKeyPage())
    wizard.addPage(PreferencesPage())
    wizard.addPage(CalibrationPage())
    finish_page = FinishPage(wizard)
    wizard.addPage(finish_page)

    result = wizard.exec()

    if result == QWizard.DialogCode.Accepted:
        # Start Jarvis if requested
        if finish_page.start_now_cb.isChecked():
            service_path = str(Path(__file__).parent.parent / "daemon" / "service.py")
            if sys.platform == "win32":
                python = sys.executable
                pythonw = python.replace("python.exe", "pythonw.exe")
                if Path(pythonw).exists():
                    python = pythonw
                subprocess.Popen(
                    [python, service_path, "--headless"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.Popen(
                    [sys.executable, service_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            print("Jarvis started!")

    # Don't call app.exec() if we created the app -- wizard.exec() was modal
