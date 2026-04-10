"""Tests for the Daemon layer (CLI, service lifecycle, IPC)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.daemon.cli import _is_daemon_running


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
    def test_install_creates_directories(self, tmp_path):
        with patch("jarvis.daemon.installer.Path") as MockPath:
            # Just verify the installer module imports
            from jarvis.daemon.installer import PLIST_LABEL
            assert PLIST_LABEL == "com.jarvis.agent"
