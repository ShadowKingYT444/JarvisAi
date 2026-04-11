"""Jarvis AI cross-platform installer bootstrap."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _install_package(script_dir: Path) -> int:
    result = subprocess.run([sys.executable, "-m", "pip", "install", str(script_dir)])
    return result.returncode


def _launch_setup(cli_only: bool) -> int:
    command = [sys.executable, "-m", "jarvis", "install"]
    if cli_only:
        command.append("--no-gui")
    result = subprocess.run(command)
    return result.returncode


def main() -> int:
    script_dir = Path(__file__).parent.resolve()

    print("=" * 52)
    print("  Jarvis AI Installer")
    print("=" * 52)
    print()

    if sys.version_info < (3, 11):
        print(f"ERROR: Python 3.11+ required (you have {sys.version})")
        return 1

    cli_only = "--cli" in sys.argv

    if sys.platform == "win32" and not cli_only:
        ps_script = script_dir / "Install-Jarvis.ps1"
        if ps_script.exists():
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)],
            )
            return result.returncode

    print("Installing Jarvis AI package...")
    print()

    if _install_package(script_dir) != 0:
        print()
        print("ERROR: Package installation failed.")
        print("Try: pip install .")
        return 1

    print()
    print("Package installed successfully.")
    print()
    print("Launching setup...")
    print()

    return _launch_setup(cli_only=cli_only)


if __name__ == "__main__":
    raise SystemExit(main())
