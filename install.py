#!/usr/bin/env python3
"""Jarvis AI cross-platform installer.

Usage:
    python install.py          # Auto-detect platform and install
    python install.py --cli    # CLI-only installer (no GUI)
"""
import os
import subprocess
import sys
from pathlib import Path


def main():
    script_dir = Path(__file__).parent.resolve()
    os.chdir(script_dir)

    print("=" * 50)
    print("  Jarvis AI Installer")
    print("=" * 50)
    print()

    # Check Python version
    if sys.version_info < (3, 11):
        print(f"ERROR: Python 3.11+ required (you have {sys.version})")
        print("Download from: https://python.org/downloads")
        sys.exit(1)

    # On Windows, delegate to PowerShell installer for best experience
    if sys.platform == "win32" and "--cli" not in sys.argv:
        ps_script = script_dir / "Install-Jarvis.ps1"
        if ps_script.exists():
            print("Launching Windows installer...")
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)],
            )
            sys.exit(result.returncode)
        # Fall through to Python-based install if PS1 not found

    # Python-based install (macOS/Linux or --cli)
    print("Installing Jarvis AI package...")
    print()

    # Install the package (creates the 'jarvis' CLI command)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", str(script_dir)],
    )
    if result.returncode != 0:
        print()
        print("ERROR: Package installation failed.")
        print("Try: pip install .")
        sys.exit(1)

    print()
    print("Package installed successfully!")
    print()

    # Run the setup wizard
    if "--cli" in sys.argv:
        print("Running CLI installer...")
        from jarvis.daemon.installer import install
        install()
    else:
        print("Launching setup wizard...")
        try:
            from jarvis.face.installer_wizard import install_gui
            install_gui()
        except ImportError:
            print("PyQt6 not available. Running CLI installer.")
            from jarvis.daemon.installer import install
            install()

    print()
    print("Installation complete!")
    print("Run 'jarvis start' to begin, or 'jarvis start --headless' for background mode.")


if __name__ == "__main__":
    main()
