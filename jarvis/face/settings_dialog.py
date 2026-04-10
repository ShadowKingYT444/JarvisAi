"""GUI Settings Dialog for Jarvis configuration.

Provides a tabbed dialog accessible from the system tray that lets users
edit all config fields with proper widgets (sliders, dropdowns, spinboxes).
The SettingsWidget is also reused by the installer wizard.
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path

from jarvis.shared.config import JarvisConfig

logger = logging.getLogger(__name__)

# Whisper model RAM estimates for display
WHISPER_RAM = {
    "tiny.en": "~40 MB",
    "base.en": "~130 MB",
    "small.en": "~250 MB",
    "medium.en": "~500 MB",
}


class SettingsWidget:
    """Reusable settings widget with all Jarvis config fields.

    Can be embedded in the SettingsDialog or the Installer Wizard.
    Uses PyQt6 widgets — imports are deferred to setup().
    """

    def __init__(self, parent=None) -> None:
        self._parent = parent
        self._widget = None
        self._fields: dict = {}

    def setup(self) -> "QWidget":
        """Create and return the settings widget."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QComboBox,
            QDoubleSpinBox,
            QFormLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSlider,
            QSpinBox,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )

        tabs = QTabWidget()

        # ── Tab 1: General ───────────────────────────────────
        general = QWidget()
        gl = QFormLayout(general)

        self._fields["gemini_model"] = QComboBox()
        self._fields["gemini_model"].setEditable(True)
        self._fields["gemini_model"].addItems([
            "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash",
        ])
        gl.addRow("Gemini Model:", self._fields["gemini_model"])

        whisper_row = QWidget()
        wl = QHBoxLayout(whisper_row)
        wl.setContentsMargins(0, 0, 0, 0)
        self._fields["whisper_model_size"] = QComboBox()
        self._fields["whisper_model_size"].addItems(["tiny.en", "base.en", "small.en", "medium.en"])
        self._whisper_ram_label = QLabel("~130 MB")
        self._fields["whisper_model_size"].currentTextChanged.connect(
            lambda t: self._whisper_ram_label.setText(WHISPER_RAM.get(t, ""))
        )
        wl.addWidget(self._fields["whisper_model_size"])
        wl.addWidget(self._whisper_ram_label)
        gl.addRow("Whisper Model:", whisper_row)

        self._fields["search_provider"] = QComboBox()
        self._fields["search_provider"].addItems(["google_cse", "serpapi"])
        gl.addRow("Search Provider:", self._fields["search_provider"])

        self._fields["keep_model_loaded"] = QComboBox()
        self._fields["keep_model_loaded"].addItems(["No (save RAM)", "Yes (faster response)"])
        gl.addRow("Keep STT in RAM:", self._fields["keep_model_loaded"])

        self._fields["headless"] = QComboBox()
        self._fields["headless"].addItems(["No (show tray + HUD)", "Yes (no GUI)"])
        gl.addRow("Headless Mode:", self._fields["headless"])

        tabs.addTab(general, "General")

        # ── Tab 2: Voice & Audio ─────────────────────────────
        voice = QWidget()
        vl = QFormLayout(voice)

        self._fields["tts_engine"] = QComboBox()
        tts_choices = ["pyttsx3"]
        if platform.system() == "Darwin":
            tts_choices.insert(0, "macos_say")
        tts_choices.append("elevenlabs")
        self._fields["tts_engine"].addItems(tts_choices)
        vl.addRow("TTS Engine:", self._fields["tts_engine"])

        self._fields["tts_voice"] = QLineEdit()
        self._fields["tts_voice"].setPlaceholderText("e.g. Daniel, Samantha")
        vl.addRow("TTS Voice:", self._fields["tts_voice"])

        self._fields["tts_rate"] = QSpinBox()
        self._fields["tts_rate"].setRange(80, 300)
        self._fields["tts_rate"].setSingleStep(10)
        vl.addRow("TTS Rate (WPM):", self._fields["tts_rate"])

        # Clap sensitivity slider
        sens_row = QWidget()
        sl = QHBoxLayout(sens_row)
        sl.setContentsMargins(0, 0, 0, 0)
        self._fields["clap_sensitivity"] = QSlider(Qt.Orientation.Horizontal)
        self._fields["clap_sensitivity"].setRange(0, 100)
        self._fields["clap_sensitivity"].setTickInterval(5)
        self._sens_label = QLabel("0.70")
        self._fields["clap_sensitivity"].valueChanged.connect(
            lambda v: self._sens_label.setText(f"{v / 100:.2f}")
        )
        sl.addWidget(self._fields["clap_sensitivity"])
        sl.addWidget(self._sens_label)
        vl.addRow("Clap Sensitivity:", sens_row)

        self._fields["listen_timeout_s"] = QSpinBox()
        self._fields["listen_timeout_s"].setRange(1, 30)
        vl.addRow("Listen Timeout (s):", self._fields["listen_timeout_s"])

        self._fields["max_record_s"] = QSpinBox()
        self._fields["max_record_s"].setRange(5, 60)
        vl.addRow("Max Record Time (s):", self._fields["max_record_s"])

        tabs.addTab(voice, "Voice & Audio")

        # ── Tab 3: API Keys ──────────────────────────────────
        keys = QWidget()
        kl = QFormLayout(keys)

        for key_name, label in [
            ("gemini_api_key", "Gemini API Key:"),
            ("search_api_key", "Search API Key:"),
            ("search_engine_id", "Search Engine ID:"),
            ("elevenlabs_api_key", "ElevenLabs API Key (optional):"),
            ("elevenlabs_voice_id", "ElevenLabs Voice ID:"),
        ]:
            field = QLineEdit()
            if "api_key" in key_name:
                field.setEchoMode(QLineEdit.EchoMode.Password)
            self._fields[key_name] = field
            kl.addRow(label, field)

        tabs.addTab(keys, "API Keys")

        # ── Tab 4: Focus Mode & Apps ─────────────────────────
        focus = QWidget()
        fl = QFormLayout(focus)

        self._fields["focus_check_interval_s"] = QSpinBox()
        self._fields["focus_check_interval_s"].setRange(5, 300)
        fl.addRow("Check Interval (s):", self._fields["focus_check_interval_s"])

        self._fields["focus_warn_before_close_s"] = QSpinBox()
        self._fields["focus_warn_before_close_s"].setRange(0, 60)
        fl.addRow("Warn Before Close (s):", self._fields["focus_warn_before_close_s"])

        # App aliases table
        self._alias_table = QTableWidget(0, 2)
        self._alias_table.setHorizontalHeaderLabels(["Alias", "Application Name"])
        self._alias_table.horizontalHeader().setStretchLastSection(True)
        fl.addRow("App Aliases:", self._alias_table)

        btn_row = QWidget()
        bl = QHBoxLayout(btn_row)
        bl.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_alias_row)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_alias_row)
        bl.addWidget(add_btn)
        bl.addWidget(remove_btn)
        bl.addStretch()
        fl.addRow("", btn_row)

        tabs.addTab(focus, "Focus & Apps")

        self._widget = tabs
        return tabs

    def load_config(self, config: JarvisConfig) -> None:
        """Populate all widgets from a config object."""
        from PyQt6.QtWidgets import QComboBox, QLineEdit, QSlider, QSpinBox

        _set_combo(self._fields["gemini_model"], config.gemini_model)
        _set_combo(self._fields["whisper_model_size"], config.whisper_model_size)
        _set_combo(self._fields["search_provider"], config.search_provider)
        _set_combo(self._fields["keep_model_loaded"], "Yes (faster response)" if config.keep_model_loaded else "No (save RAM)")
        _set_combo(self._fields["headless"], "Yes (no GUI)" if config.headless else "No (show tray + HUD)")

        _set_combo(self._fields["tts_engine"], config.tts_engine)
        self._fields["tts_voice"].setText(config.tts_voice)
        self._fields["tts_rate"].setValue(config.tts_rate)

        self._fields["clap_sensitivity"].setValue(int(config.clap_sensitivity * 100))
        self._sens_label.setText(f"{config.clap_sensitivity:.2f}")
        self._fields["listen_timeout_s"].setValue(config.listen_timeout_s)
        self._fields["max_record_s"].setValue(config.max_record_s)

        self._fields["gemini_api_key"].setText(config.gemini_api_key)
        self._fields["search_api_key"].setText(config.search_api_key)
        self._fields["search_engine_id"].setText(config.search_engine_id)
        self._fields["elevenlabs_api_key"].setText(config.elevenlabs_api_key)
        self._fields["elevenlabs_voice_id"].setText(config.elevenlabs_voice_id)

        self._fields["focus_check_interval_s"].setValue(config.focus_check_interval_s)
        self._fields["focus_warn_before_close_s"].setValue(config.focus_warn_before_close_s)

        # App aliases
        self._alias_table.setRowCount(0)
        for alias, app_name in config.app_aliases.items():
            self._add_alias_row(alias, app_name)

    def save_config(self) -> JarvisConfig:
        """Read all widget values and return a new JarvisConfig."""
        config = JarvisConfig(
            gemini_api_key=self._fields["gemini_api_key"].text(),
            gemini_model=self._fields["gemini_model"].currentText(),
            whisper_model_size=self._fields["whisper_model_size"].currentText(),
            tts_engine=self._fields["tts_engine"].currentText(),
            tts_voice=self._fields["tts_voice"].text() or "Daniel",
            tts_rate=self._fields["tts_rate"].value(),
            search_provider=self._fields["search_provider"].currentText(),
            search_api_key=self._fields["search_api_key"].text(),
            search_engine_id=self._fields["search_engine_id"].text(),
            elevenlabs_api_key=self._fields["elevenlabs_api_key"].text(),
            elevenlabs_voice_id=self._fields["elevenlabs_voice_id"].text(),
            clap_sensitivity=self._fields["clap_sensitivity"].value() / 100.0,
            listen_timeout_s=self._fields["listen_timeout_s"].value(),
            max_record_s=self._fields["max_record_s"].value(),
            focus_check_interval_s=self._fields["focus_check_interval_s"].value(),
            focus_warn_before_close_s=self._fields["focus_warn_before_close_s"].value(),
            keep_model_loaded=self._fields["keep_model_loaded"].currentText().startswith("Yes"),
            headless=self._fields["headless"].currentText().startswith("Yes"),
            app_aliases=self._get_aliases(),
        )
        config.save()
        config.save_env()
        return config

    def _get_aliases(self) -> dict:
        aliases = {}
        for row in range(self._alias_table.rowCount()):
            alias_item = self._alias_table.item(row, 0)
            name_item = self._alias_table.item(row, 1)
            if alias_item and name_item and alias_item.text().strip():
                aliases[alias_item.text().strip()] = name_item.text().strip()
        return aliases

    def _add_alias_row(self, alias: str = "", app_name: str = "") -> None:
        from PyQt6.QtWidgets import QTableWidgetItem

        row = self._alias_table.rowCount()
        self._alias_table.insertRow(row)
        self._alias_table.setItem(row, 0, QTableWidgetItem(alias))
        self._alias_table.setItem(row, 1, QTableWidgetItem(app_name))

    def _remove_alias_row(self) -> None:
        row = self._alias_table.currentRow()
        if row >= 0:
            self._alias_table.removeRow(row)


class SettingsDialog:
    """Standalone settings dialog window.

    Wraps SettingsWidget with OK/Cancel/Apply buttons.
    """

    def __init__(self, config: JarvisConfig | None = None, event_bus=None) -> None:
        self._config = config or JarvisConfig.load()
        self._event_bus = event_bus
        self._dialog = None
        self._settings_widget = None

    def show(self) -> None:
        """Create and show the settings dialog."""
        from PyQt6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QVBoxLayout,
        )

        self._dialog = QDialog()
        self._dialog.setWindowTitle("Jarvis Settings")
        self._dialog.setMinimumSize(550, 500)

        layout = QVBoxLayout(self._dialog)

        self._settings_widget = SettingsWidget()
        tabs = self._settings_widget.setup()
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self._dialog.reject)
        apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        if apply_btn:
            apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(buttons)

        self._settings_widget.load_config(self._config)
        self._dialog.exec()

    def _on_ok(self) -> None:
        self._on_apply()
        self._dialog.accept()

    def _on_apply(self) -> None:
        new_config = self._settings_widget.save_config()
        self._config = new_config
        if self._event_bus:
            self._event_bus.emit("config_reloaded", new_config)
        logger.info("Settings saved")


def _set_combo(combo, value: str) -> None:
    """Set a QComboBox to a value, adding it if not present."""
    idx = combo.findText(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    else:
        combo.addItem(value)
        combo.setCurrentIndex(combo.count() - 1)
