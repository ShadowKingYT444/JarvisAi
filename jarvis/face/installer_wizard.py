"""GUI installer wizard for Jarvis."""

from __future__ import annotations

import importlib
import logging
import platform
import subprocess
import sys
from pathlib import Path

from jarvis.shared.config import JarvisConfig
from jarvis.shared.windows_apps import find_chrome_path, find_obsidian_path, find_warp_path

logger = logging.getLogger(__name__)

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
    background-color: #0f172a;
    color: #e2e8f0;
}
QWizardPage {
    padding: 10px;
}
QLabel {
    color: #e2e8f0;
}
QLabel[role="muted"] {
    color: #94a3b8;
}
QFrame#card {
    background-color: #111827;
    border: 1px solid #1f2937;
    border-radius: 14px;
}
QLineEdit, QComboBox, QTextEdit {
    background-color: #0b1220;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 6px 8px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #38bdf8;
}
QPushButton {
    background-color: #1d4ed8;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 7px 14px;
}
QPushButton:hover {
    background-color: #2563eb;
}
QPushButton:pressed {
    background-color: #1e40af;
}
QPushButton:disabled {
    background-color: #334155;
    color: #94a3b8;
}
QCheckBox {
    spacing: 8px;
}
QSlider::groove:horizontal {
    background: #334155;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #38bdf8;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QProgressBar {
    background-color: #0b1220;
    border: 1px solid #334155;
    border-radius: 8px;
    text-align: center;
    color: #e2e8f0;
}
QProgressBar::chunk {
    background-color: #38bdf8;
    border-radius: 8px;
}
"""


def check_dependencies() -> tuple[list[str], list[str]]:
    """Return missing required and optional packages."""
    missing_req: list[str] = []
    missing_opt: list[str] = []

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
    """Best-effort key validation used from the setup wizard."""
    if not key or len(key) < 10:
        return False

    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        list(genai.list_models())
        return True
    except Exception:
        return False


def _device_rows() -> list[tuple[int, str]]:
    import sounddevice

    devices = sounddevice.query_devices()
    rows: list[tuple[int, str]] = []
    for index, device in enumerate(devices):
        if device["max_input_channels"] > 0:
            rows.append((index, f"[{index}] {device['name']} ({device['max_input_channels']} ch)"))
    return rows


def _default_input_device() -> int | None:
    import sounddevice

    try:
        default_in = sounddevice.default.device[0]
    except Exception:
        return None
    return default_in if isinstance(default_in, int) and default_in >= 0 else None


def _styled_card(title: str, body: str):
    from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    heading = QLabel(f"<b>{title}</b>")
    heading.setWordWrap(True)
    layout.addWidget(heading)

    text = QLabel(body)
    text.setWordWrap(True)
    layout.addWidget(text)

    return frame


def install_gui() -> None:
    """Launch the GUI installer wizard."""
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QSlider,
            QSpinBox,
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
    app.setStyleSheet(DARK_STYLESHEET)

    class WelcomePage(QWizardPage):
        def __init__(self) -> None:
            super().__init__()
            self.setTitle("Welcome")
            self.setSubTitle("This wizard installs Jarvis and defines its startup profile.")

            layout = QVBoxLayout(self)
            layout.addWidget(
                _styled_card(
                    "What this installer does",
                    "It installs the package, stores your API keys, saves the initial "
                    "launch profile, and configures auto-start if you want it.",
                )
            )

            info = QLabel(
                f"<b>Platform:</b> {platform.system()} ({platform.machine()})<br>"
                f"<b>Python:</b> {sys.version.split()[0]}"
            )
            info.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(info)

            py_ok = sys.version_info >= (3, 11)
            status = QLabel(
                "Python 3.11+ requirement met." if py_ok else
                f"Python 3.11+ is recommended (detected {sys.version_info.major}.{sys.version_info.minor})."
            )
            status.setStyleSheet(
                "color: #22c55e;" if py_ok else "color: #f59e0b;"
            )
            layout.addWidget(status)

            missing_req, missing_opt = check_dependencies()
            dep_title = QLabel("<b>Dependency check</b>")
            layout.addWidget(dep_title)

            if missing_req:
                req = QLabel("Missing required packages: " + ", ".join(missing_req))
                req.setWordWrap(True)
                req.setStyleSheet("color: #f87171;")
                layout.addWidget(req)
            else:
                ok = QLabel("All required runtime packages are already available.")
                ok.setStyleSheet("color: #22c55e;")
                layout.addWidget(ok)

            if missing_opt:
                opt = QLabel("Optional packages not installed: " + ", ".join(missing_opt))
                opt.setWordWrap(True)
                opt.setStyleSheet("color: #94a3b8;")
                layout.addWidget(opt)

            detected_apps = {
                "Chrome": find_chrome_path(),
                "Obsidian": find_obsidian_path(),
                "Warp": find_warp_path(),
            }
            detection_lines = []
            for label, path in detected_apps.items():
                state = "detected" if path else "not found"
                suffix = f" - {path}" if path else ""
                detection_lines.append(f"{label}: {state}{suffix}")
            app_status = QLabel("<b>Windows app detection</b><br>" + "<br>".join(detection_lines))
            app_status.setTextFormat(Qt.TextFormat.RichText)
            app_status.setWordWrap(True)
            layout.addWidget(app_status)

            layout.addStretch(1)

    class SecretsPage(QWizardPage):
        def __init__(self) -> None:
            super().__init__()
            self.setTitle("API Keys")
            self.setSubTitle("Store keys locally in your Jarvis home directory.")

            layout = QFormLayout(self)

            self.gemini_key = QLineEdit()
            self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.gemini_key.setPlaceholderText("Required - Gemini API key")
            layout.addRow("Gemini key:", self.gemini_key)

            self.gemini_status = QLabel("")
            self.gemini_status.setProperty("role", "muted")
            validate_btn = QPushButton("Validate")
            validate_btn.clicked.connect(self._validate_gemini)
            validate_row = QHBoxLayout()
            validate_row.addWidget(validate_btn)
            validate_row.addWidget(self.gemini_status, 1)
            layout.addRow("Check key:", validate_row)

            self.porcupine_key = QLineEdit()
            self.porcupine_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.porcupine_key.setPlaceholderText("Optional - enables wake word")
            layout.addRow("Porcupine key:", self.porcupine_key)

            self.elevenlabs_key = QLineEdit()
            self.elevenlabs_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.elevenlabs_key.setPlaceholderText("Optional - premium TTS")
            layout.addRow("ElevenLabs key:", self.elevenlabs_key)

        def _validate_gemini(self) -> None:
            key = self.gemini_key.text().strip()
            if not key:
                self.gemini_status.setText("Enter a key first.")
                return

            self.gemini_status.setText("Validating...")
            QApplication.processEvents()

            if validate_gemini_key(key):
                self.gemini_status.setText("Valid.")
                self.gemini_status.setStyleSheet("color: #22c55e;")
            else:
                self.gemini_status.setText("Invalid.")
                self.gemini_status.setStyleSheet("color: #f87171;")

    class BehaviorPage(QWizardPage):
        def __init__(self) -> None:
            super().__init__()
            self.setTitle("Startup Experience")
            self.setSubTitle("Choose how Jarvis wakes up and what it does first.")

            layout = QVBoxLayout(self)
            layout.addWidget(
                _styled_card(
                    "Recommended flow",
                    "Use double-clap to initialize Jarvis, then the wake word 'Jarvis' "
                    "for follow-up commands. The installer saves this profile together "
                    "with your startup defaults.",
                )
            )

            form = QFormLayout()

            self.tts_engine = QComboBox()
            tts_options = ["auto", "pyttsx3"]
            if platform.system() == "Darwin":
                tts_options.insert(1, "macos_say")
            tts_options.append("elevenlabs")
            self.tts_engine.addItems(tts_options)
            self.tts_engine.setCurrentText("auto")
            form.addRow("TTS engine:", self.tts_engine)

            self.tts_voice = QLineEdit("Daniel" if platform.system() == "Darwin" else "")
            form.addRow("TTS voice:", self.tts_voice)

            self.whisper_model = QComboBox()
            self.whisper_model.addItems(["tiny.en", "base.en", "small.en", "medium.en"])
            self.whisper_model.setCurrentText("base.en")
            self.model_label = QLabel("Balanced default")
            self.whisper_model.currentTextChanged.connect(self._update_model_hint)
            model_row = QHBoxLayout()
            model_row.addWidget(self.whisper_model)
            model_row.addWidget(self.model_label)
            form.addRow("STT model:", model_row)

            self.double_clap = QCheckBox("Double-clap to initialize Jarvis")
            self.double_clap.setChecked(True)
            form.addRow(self.double_clap)

            self.wake_word = QCheckBox("Enable wake word 'Jarvis'")
            self.wake_word.setChecked(True)
            form.addRow(self.wake_word)

            self.hotkey = QCheckBox("Enable hotkey fallback")
            self.hotkey.setChecked(True)
            form.addRow(self.hotkey)

            self.clap_gap = QSpinBox()
            self.clap_gap.setRange(80, 300)
            self.clap_gap.setValue(140)
            form.addRow("Clap gap (ms):", self.clap_gap)

            self.clap_timeout = QSpinBox()
            self.clap_timeout.setRange(300, 1200)
            self.clap_timeout.setValue(600)
            form.addRow("Clap timeout (ms):", self.clap_timeout)

            self.clap_sensitivity = QSlider(Qt.Orientation.Horizontal)
            self.clap_sensitivity.setRange(10, 100)
            self.clap_sensitivity.setValue(70)
            self.sensitivity_label = QLabel("0.70")
            self.clap_sensitivity.valueChanged.connect(
                lambda value: self.sensitivity_label.setText(f"{value / 100:.2f}")
            )
            sensitivity_row = QHBoxLayout()
            sensitivity_row.addWidget(self.clap_sensitivity)
            sensitivity_row.addWidget(self.sensitivity_label)
            form.addRow("Clap sensitivity:", sensitivity_row)

            self.hotkey_text = QLineEdit("ctrl+shift+j")
            form.addRow("Hotkey:", self.hotkey_text)

            layout.addLayout(form)

        def _update_model_hint(self, value: str) -> None:
            hints = {
                "tiny.en": "Fastest, least accurate",
                "base.en": "Balanced default",
                "small.en": "Better accuracy",
                "medium.en": "Best accuracy, heavier",
            }
            self.model_label.setText(hints.get(value, ""))

    class MicPage(QWizardPage):
        def __init__(self) -> None:
            super().__init__()
            self.setTitle("Microphone")
            self.setSubTitle("Pick the microphone behavior that fits your setup.")

            layout = QVBoxLayout(self)
            layout.addWidget(
                _styled_card(
                    "Default microphone behavior",
                    "Leave this on system default if you switch microphones often. Jarvis "
                    "will follow whatever Windows marks as the active input device on the next launch.",
                )
            )

            self.use_default = QCheckBox("Use the current system default microphone")
            self.use_default.setChecked(True)
            self.use_default.toggled.connect(self._refresh_enabled_state)
            layout.addWidget(self.use_default)

            self.device_combo = QComboBox()
            self._device_map: list[int] = []
            try:
                for index, label in _device_rows():
                    self.device_combo.addItem(label)
                    self._device_map.append(index)
            except Exception as exc:
                self.device_combo.addItem(f"Unable to list devices: {exc}")
                self.device_combo.setEnabled(False)

            layout.addWidget(QLabel("Pinned device:"))
            layout.addWidget(self.device_combo)

            default_index = _default_input_device()
            if default_index is not None:
                layout.addWidget(QLabel(f"Default device index detected: {default_index}"))

            self._refresh_enabled_state(self.use_default.isChecked())

        def _refresh_enabled_state(self, checked: bool) -> None:
            self.device_combo.setEnabled(not checked and self.device_combo.count() > 0)

        def selected_device(self) -> tuple[int | None, str]:
            if self.use_default.isChecked() or not self._device_map:
                return None, ""
            current = self.device_combo.currentIndex()
            if current < 0 or current >= len(self._device_map):
                return None, ""
            index = self._device_map[current]
            return index, self.device_combo.currentText()

    class LaunchPage(QWizardPage):
        def __init__(self) -> None:
            super().__init__()
            self.setTitle("Startup Profile")
            self.setSubTitle("Set the defaults for Jarvis's first launch sequence.")

            layout = QVBoxLayout(self)
            layout.addWidget(
                _styled_card(
                    "What gets persisted",
                    "Project directory, browser tabs, and the app defaults used for the initial launch sequence are saved to your Jarvis home directory.",
                )
            )

            form = QFormLayout()

            self.project_dir = QLineEdit(str(Path.cwd()))
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(self._browse_project_dir)
            project_row = QHBoxLayout()
            project_row.addWidget(self.project_dir, 1)
            project_row.addWidget(browse_btn)
            form.addRow("Project directory:", project_row)

            self.startup_browser = QLineEdit("chrome")
            form.addRow("Startup browser:", self.startup_browser)

            self.gmail_url = QLineEdit("https://mail.google.com")
            self.classroom_url = QLineEdit("https://classroom.google.com")
            self.docs_url = QLineEdit("https://docs.google.com")
            self.docs_url.setText("https://docs.google.com/document/u/0/")
            self.song_url = QLineEdit("https://www.youtube.com/watch?v=fPO76Jlnz6c&autoplay=1")
            form.addRow("Gmail URL:", self.gmail_url)
            form.addRow("Classroom URL:", self.classroom_url)
            form.addRow("Docs URL:", self.docs_url)
            form.addRow("Song URL:", self.song_url)

            self.app_defaults = QLineEdit("Obsidian, Warp")
            form.addRow("App defaults:", self.app_defaults)

            self.claude_command = QLineEdit("claude")
            form.addRow("Claude command:", self.claude_command)

            layout.addLayout(form)

        def _browse_project_dir(self) -> None:
            selected = QFileDialog.getExistingDirectory(
                self,
                "Select project directory",
                self.project_dir.text().strip() or str(Path.cwd()),
            )
            if selected:
                self.project_dir.setText(selected)

        def launch_profile_payload(self) -> dict[str, object]:
            browser_defaults = [
                self.gmail_url.text().strip(),
                self.classroom_url.text().strip(),
                self.docs_url.text().strip(),
                self.song_url.text().strip(),
            ]
            browser_defaults = [value for value in browser_defaults if value]

            apps = [
                item.strip()
                for item in self.app_defaults.text().split(",")
                if item.strip()
            ]

            return {
                "startup_project_dir": self.project_dir.text().strip(),
                "startup_browser": self.startup_browser.text().strip() or "chrome",
                "startup_urls": browser_defaults,
                "startup_apps": apps,
                "launch_warp_with_claude": True,
                "claude_command": self.claude_command.text().strip() or "claude",
                "startup_enabled": True,
            }

    class FinishPage(QWizardPage):
        def __init__(self, wizard_ref: QWizard) -> None:
            super().__init__()
            self._wizard_ref = wizard_ref
            self._installed = False
            self._install_payload: dict[str, object] = {}
            self.setTitle("Finish")
            self.setSubTitle("Review the saved settings and install Jarvis.")

            layout = QVBoxLayout(self)

            self.summary = QTextEdit()
            self.summary.setReadOnly(True)
            layout.addWidget(self.summary)

            self.auto_start = QCheckBox("Install auto-start on login")
            self.auto_start.setChecked(True)
            self.auto_start.toggled.connect(lambda _: self._refresh_summary())
            layout.addWidget(self.auto_start)

            self.start_now = QCheckBox("Launch Jarvis after setup")
            self.start_now.setChecked(True)
            layout.addWidget(self.start_now)

        def initializePage(self) -> None:
            self._refresh_summary()

        def _build_install_payload(self) -> tuple[dict[str, object], list[str]]:
            wizard = self._wizard_ref
            secrets: SecretsPage = wizard.page(1)  # type: ignore[assignment]
            behavior: BehaviorPage = wizard.page(2)  # type: ignore[assignment]
            mic: MicPage = wizard.page(3)  # type: ignore[assignment]
            launch: LaunchPage = wizard.page(4)  # type: ignore[assignment]
            launch_payload = launch.launch_profile_payload()
            device_index, device_name = mic.selected_device()

            activation_methods = []
            if behavior.wake_word.isChecked():
                activation_methods.append("wake_word")
            if behavior.hotkey.isChecked():
                activation_methods.append("hotkey")
            if not activation_methods:
                activation_methods = ["wake_word", "hotkey"]

            overrides: dict[str, object] = {
                "gemini_api_key": secrets.gemini_key.text().strip(),
                "porcupine_access_key": secrets.porcupine_key.text().strip(),
                "elevenlabs_api_key": secrets.elevenlabs_key.text().strip(),
                "tts_engine": behavior.tts_engine.currentText().strip(),
                "tts_voice": behavior.tts_voice.text().strip() or "Daniel",
                "whisper_model_size": behavior.whisper_model.currentText().strip(),
                "clap_sensitivity": behavior.clap_sensitivity.value() / 100.0,
                "clap_min_gap_ms": behavior.clap_gap.value(),
                "clap_timeout_ms": behavior.clap_timeout.value(),
                "activation_methods": activation_methods,
                "require_initialization_clap": behavior.double_clap.isChecked(),
                "hotkey": behavior.hotkey_text.text().strip() or "ctrl+shift+j",
                "audio_input_device": device_index,
                "audio_input_device_follow_default": mic.use_default.isChecked(),
                "auto_detect_microphone": mic.use_default.isChecked(),
                "preferred_microphone_name": device_name,
            }
            overrides.update(launch_payload)

            summary_lines = [
                "Installer will write:",
                "- ~/.jarvis/config.yaml",
                "- ~/.jarvis/.env",
                "",
                f"Initialization clap: {'enabled' if behavior.double_clap.isChecked() else 'disabled'}",
                f"Wake word / hotkey: {', '.join(activation_methods)}",
                f"Project directory: {launch_payload['startup_project_dir']}",
                f"Startup browser: {launch_payload['startup_browser']}",
                f"Browser URLs: {', '.join(launch_payload['startup_urls'])}",
                f"Startup apps: {', '.join(launch_payload['startup_apps'])}",
                f"Mic mode: {'system default' if mic.use_default.isChecked() else device_name or 'pinned device'}",
                f"Auto-start: {'enabled' if self.auto_start.isChecked() else 'disabled'}",
            ]

            if not secrets.gemini_key.text().strip():
                summary_lines.append("")
                summary_lines.append("Warning: the Gemini key is empty. Jarvis will not be usable until a key is added.")

            return overrides, summary_lines

        def _refresh_summary(self) -> None:
            overrides, summary_lines = self._build_install_payload()
            self._install_payload = overrides
            self.summary.setPlainText("\n".join(summary_lines))

        def validatePage(self) -> bool:
            if self._installed:
                return True

            from jarvis.daemon.installer import install

            overrides, summary_lines = self._build_install_payload()
            try:
                install(
                    config_overrides=overrides,
                    enable_autostart=self.auto_start.isChecked(),
                )
                self.summary.setPlainText("\n".join(summary_lines))
                self._installed = True
                self._install_payload = overrides
                return True
            except Exception as exc:
                self.summary.setPlainText("\n".join(summary_lines + ["", f"Installation failed: {exc}"]))
                logger.exception("Installer wizard failed")
                QMessageBox.critical(
                    self,
                    "Installation failed",
                    str(exc),
                )
                return False

    wizard = QWizard()
    wizard.setWindowTitle("Jarvis AI Setup")
    wizard.setMinimumSize(760, 560)
    wizard.addPage(WelcomePage())
    wizard.addPage(SecretsPage())
    wizard.addPage(BehaviorPage())
    wizard.addPage(MicPage())
    wizard.addPage(LaunchPage())
    finish_page = FinishPage(wizard)
    wizard.addPage(finish_page)

    result = wizard.exec()
    if result != QWizard.DialogCode.Accepted:
        return

    if finish_page.start_now.isChecked() and finish_page._installed:
        from jarvis.daemon.installer import _jarvis_command, _preferred_windows_python

        python = sys.executable
        if sys.platform == "win32":
            python = _preferred_windows_python()
            subprocess.Popen(
                _jarvis_command(python),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            subprocess.Popen(
                _jarvis_command(python),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        QMessageBox.information(
            wizard,
            "Jarvis started",
            "Jarvis was launched in the background.",
        )
