"""Jarvis auto-start installer.

Creates launchd plist (macOS) or Task Scheduler entry (Windows)
for automatic startup on login.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

PLIST_LABEL = "com.jarvis.agent"


def install(config_overrides: dict | None = None) -> None:
    """Install Jarvis auto-start for the current platform.

    Parameters
    ----------
    config_overrides:
        Optional dict of config values to write instead of defaults.
    """
    system = platform.system()

    # Create ~/.jarvis directory structure
    jarvis_home = Path("~/.jarvis").expanduser()
    for subdir in ("logs", "conversations", "backups"):
        (jarvis_home / subdir).mkdir(parents=True, exist_ok=True)

    # Create config — use overrides if provided, otherwise platform defaults
    config_path = jarvis_home / "config.yaml"
    if config_overrides:
        from jarvis.shared.config import JarvisConfig
        config = JarvisConfig(**{
            k: v for k, v in config_overrides.items()
            if k in {f.name for f in JarvisConfig.__dataclass_fields__.values()}
        })
        config.save(str(config_path))
        print(f"Saved config: {config_path}")
    elif not config_path.exists():
        default_tts = "macos_say" if system == "Darwin" else "pyttsx3"
        config_path.write_text(
            "# Jarvis AI Configuration\n"
            f"gemini_model: gemini-2.0-flash\n"
            f"whisper_model_size: base.en\n"
            f"tts_engine: {default_tts}\n"
            f"tts_voice: {'Daniel' if system == 'Darwin' else ''}\n"
            f"tts_rate: 180\n"
            f"clap_sensitivity: 0.7\n"
            f"search_provider: google_cse\n"
        )
        print(f"Created default config: {config_path}")

    # Create .env template if missing
    env_path = jarvis_home / ".env"
    if not env_path.exists():
        env_path.write_text(
            "# Jarvis API Keys\n"
            "GOOGLE_API_KEY=\n"
            "SEARCH_API_KEY=\n"
            "SEARCH_ENGINE_ID=\n"
            "# ELEVENLABS_API_KEY=\n"
        )
        env_path.chmod(0o600)
        print(f"Created .env template: {env_path}")
        print("  -> Edit this file to add your API keys!")

    if system == "Darwin":
        _install_macos()
    elif system == "Windows":
        _install_windows()
    elif system == "Linux":
        _install_linux()
    else:
        print(f"Unsupported platform: {system}")
        print("You can still run Jarvis manually: jarvis start")


def uninstall() -> None:
    """Remove Jarvis auto-start."""
    system = platform.system()
    if system == "Darwin":
        _uninstall_macos()
    elif system == "Windows":
        _uninstall_windows()
    elif system == "Linux":
        _uninstall_linux()
    else:
        print(f"Unsupported platform: {system}")


# ── macOS (launchd) ─────────────────────────────────────────────────


def _install_macos() -> None:
    python = sys.executable
    service_path = str(Path(__file__).parent / "service.py")
    log_dir = Path("~/.jarvis/logs").expanduser()

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{service_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir / 'jarvis.log'}</string>
    <key>StandardErrorPath</key>
    <string>{log_dir / 'jarvis_error.log'}</string>
</dict>
</plist>
"""
    plist_path = Path("~/Library/LaunchAgents").expanduser() / f"{PLIST_LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)

    # Load the plist
    subprocess.run(["launchctl", "load", str(plist_path)], check=False)
    print(f"Installed launchd plist: {plist_path}")
    print("Jarvis will start automatically on login.")


def _uninstall_macos() -> None:
    plist_path = Path("~/Library/LaunchAgents").expanduser() / f"{PLIST_LABEL}.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        print("Removed launchd plist. Jarvis will no longer auto-start.")
    else:
        print("Jarvis auto-start is not installed.")


# ── Windows (Task Scheduler) ────────────────────────────────────────


def _install_windows() -> None:
    python = sys.executable
    service_path = str(Path(__file__).parent / "service.py")

    # Create scheduled task
    cmd = [
        "schtasks", "/create",
        "/tn", "JarvisAI",
        "/tr", f'"{python}" "{service_path}"',
        "/sc", "onlogon",
        "/rl", "highest",
        "/f",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Installed Windows Task Scheduler entry.")
        print("Jarvis will start automatically on login.")
    else:
        print(f"Failed to create scheduled task: {result.stderr}")


def _uninstall_windows() -> None:
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", "JarvisAI", "/f"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("Removed scheduled task. Jarvis will no longer auto-start.")
    else:
        print("Jarvis auto-start is not installed.")


# ── Linux (systemd user service) ────────────────────────────────────


def _install_linux() -> None:
    python = sys.executable
    service_path = str(Path(__file__).parent / "service.py")

    unit_content = f"""[Unit]
Description=Jarvis AI Desktop Assistant
After=graphical-session.target

[Service]
Type=simple
ExecStart={python} {service_path}
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
"""
    unit_dir = Path("~/.config/systemd/user").expanduser()
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "jarvis.service"
    unit_path.write_text(unit_content)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "jarvis"], check=False)
    subprocess.run(["systemctl", "--user", "start", "jarvis"], check=False)
    print(f"Installed systemd user service: {unit_path}")
    print("Jarvis will start automatically on login.")


def _uninstall_linux() -> None:
    subprocess.run(["systemctl", "--user", "stop", "jarvis"], check=False)
    subprocess.run(["systemctl", "--user", "disable", "jarvis"], check=False)
    unit_path = Path("~/.config/systemd/user/jarvis.service").expanduser()
    if unit_path.exists():
        unit_path.unlink()
        print("Removed systemd user service.")
    else:
        print("Jarvis auto-start is not installed.")
