#!/usr/bin/env python3
"""Jarvis AI one-click installer.

Usage:
    python install.py          # GUI installer wizard
    python install.py --cli    # CLI-only installer
"""
import subprocess
import sys
import os

def main():
    # Ensure we're in the right directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Check Python version
    if sys.version_info < (3, 11):
        print(f"Warning: Python 3.11+ recommended (you have {sys.version})")
        print("Continuing anyway...")

    # Install dependencies
    print("Installing dependencies...")
    req_file = os.path.join(script_dir, "jarvis", "requirements.txt")
    if os.path.exists(req_file):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
    else:
        print(f"Error: {req_file} not found")
        sys.exit(1)

    print("\nDependencies installed successfully!")
    print()

    # Launch installer
    if "--cli" in sys.argv:
        print("Running CLI installer...")
        from jarvis.daemon.installer import install
        install()
    else:
        print("Launching GUI installer wizard...")
        try:
            from jarvis.face.installer_wizard import install_gui
            install_gui()
        except ImportError:
            print("PyQt6 not available. Falling back to CLI installer.")
            from jarvis.daemon.installer import install
            install()

    print()
    print("Installation complete!")
    print("Run 'jarvis start' or 'python -m jarvis.daemon.cli start' to begin.")

if __name__ == "__main__":
    main()
