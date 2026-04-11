"""Tests for the Daemon layer (CLI, service lifecycle, IPC)."""

from __future__ import annotations

import os
from unittest.mock import patch

from jarvis.daemon.cli import _is_daemon_running
from jarvis.daemon.installer import (
    PLIST_LABEL,
    _jarvis_command,
    _preferred_windows_python,
    _write_windows_startup_script,
)


class TestIsDaemonRunning:
    def test_no_pid_file(self, tmp_path):
        with patch("jarvis.daemon.cli._get_pid_file", return_value=tmp_path / "no.pid"):
            assert _is_daemon_running() is False

    def test_stale_pid_file(self, tmp_path):
        pid_file = tmp_path / "jarvis.pid"
        pid_file.write_text("999999999")  # non-existent PID
        with patch("jarvis.daemon.cli._get_pid_file", return_value=pid_file):
            assert _is_daemon_running() is False
            assert not pid_file.exists()  # cleaned up

    def test_running_process(self, tmp_path):
        pid_file = tmp_path / "jarvis.pid"
        pid_file.write_text(str(os.getpid()))  # current process
        with patch("jarvis.daemon.cli._get_pid_file", return_value=pid_file):
            assert _is_daemon_running() is True

    def test_invalid_pid_content(self, tmp_path):
        pid_file = tmp_path / "jarvis.pid"
        pid_file.write_text("not-a-number")
        with patch("jarvis.daemon.cli._get_pid_file", return_value=pid_file):
            assert _is_daemon_running() is False


class TestInstaller:
    def test_installer_module_imports(self):
        assert PLIST_LABEL == "com.jarvis.agent"

    def test_jarvis_command_defaults_to_full_start(self):
        assert _jarvis_command("python") == ["python", "-m", "jarvis", "start"]

    def test_jarvis_command_supports_headless(self):
        assert _jarvis_command("python", headless=True) == [
            "python",
            "-m",
            "jarvis",
            "start",
            "--headless",
        ]

    def test_preferred_windows_python_uses_adjacent_pythonw(self, tmp_path):
        python = tmp_path / "python.exe"
        pythonw = tmp_path / "pythonw.exe"
        python.write_text("")
        pythonw.write_text("")

        with patch("jarvis.daemon.installer.sys.platform", "win32"):
            with patch("jarvis.daemon.installer.sys.executable", str(python)):
                with patch.dict(os.environ, {}, clear=True):
                    assert _preferred_windows_python() == str(pythonw)

    def test_windows_startup_script_uses_full_start_command(self, tmp_path):
        with patch.dict(os.environ, {"APPDATA": str(tmp_path)}):
            script_path = _write_windows_startup_script(
                _jarvis_command("pythonw.exe"),
                name="Jarvis Test.cmd",
            )

        text = script_path.read_text(encoding="utf-8")
        assert "jarvis start" in text
        assert "--headless" not in text
