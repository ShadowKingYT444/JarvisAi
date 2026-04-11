"""Tests for the top-level installer bootstrap."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import Mock


def _load_install_module():
    module_path = Path(__file__).resolve().parents[2] / "install.py"
    spec = importlib.util.spec_from_file_location("jarvis_install_bootstrap", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_windows_bootstrap_uses_powershell(monkeypatch):
    module = _load_install_module()
    run = Mock(return_value=Mock(returncode=0))

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.sys, "argv", ["install.py"])
    monkeypatch.setattr(module.sys, "version_info", (3, 14, 0))
    monkeypatch.setattr(module.subprocess, "run", run)

    assert module.main() == 0
    command = run.call_args.args[0]
    assert command[:4] == ["powershell", "-ExecutionPolicy", "Bypass", "-File"]
    assert command[-1].endswith("Install-Jarvis.ps1")


def test_windows_bootstrap_passes_no_gui_for_cli(monkeypatch):
    module = _load_install_module()
    run = Mock(return_value=Mock(returncode=0))

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.sys, "argv", ["install.py", "--cli"])
    monkeypatch.setattr(module.sys, "version_info", (3, 14, 0))
    monkeypatch.setattr(module.subprocess, "run", run)

    assert module.main() == 0
    command = run.call_args.args[0]
    assert "-NoGui" in command
    assert any(str(part).endswith("Install-Jarvis.ps1") for part in command)
