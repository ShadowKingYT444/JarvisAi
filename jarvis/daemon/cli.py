"""Jarvis CLI -- lightweight interface to the running daemon.

Communicates with the daemon over TCP localhost.

Usage::

    jarvis start          # Start daemon (or install + start)
    jarvis stop           # Graceful shutdown
    jarvis restart        # Restart daemon
    jarvis status         # Show current state, uptime
    jarvis text "query"   # Send text command without voice
    jarvis log            # Tail the conversation log
    jarvis config         # Open config in $EDITOR
    jarvis install        # Install auto-start
    jarvis uninstall      # Remove auto-start
    jarvis calibrate      # Re-run clap detection calibration
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import time
from datetime import date
from pathlib import Path


def _get_port_file() -> Path:
    return Path("~/.jarvis/jarvis.port").expanduser()


def _get_pid_file() -> Path:
    return Path("~/.jarvis/jarvis.pid").expanduser()


def _get_ipc_port() -> int | None:
    """Read the IPC port from the port file."""
    port_file = _get_port_file()
    if not port_file.exists():
        return None
    try:
        return int(port_file.read_text().strip())
    except (ValueError, OSError):
        return None


async def _send_ipc(message: str) -> str | None:
    """Send a message to the running daemon and return the response."""
    port = _get_ipc_port()
    if port is None:
        return None

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(message.encode("utf-8"))
        await writer.drain()
        writer.write_eof()

        data = await asyncio.wait_for(reader.read(4096), timeout=10)
        writer.close()
        await writer.wait_closed()
        return data.decode("utf-8")
    except Exception:
        return None


def _is_daemon_running() -> bool:
    """Check if the daemon is running via the PID file."""
    pid_file = _get_pid_file()
    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())
        if sys.platform == "win32":
            # os.kill(pid, 0) is unreliable on Windows — use tasklist
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            if str(pid) not in result.stdout:
                pid_file.unlink(missing_ok=True)
                return False
            return True
        else:
            os.kill(pid, 0)
            return True
    except (ValueError, OSError, subprocess.TimeoutExpired):
        pid_file.unlink(missing_ok=True)
        return False


def cmd_start(args):
    """Start the Jarvis daemon."""
    if _is_daemon_running():
        print("Jarvis is already running.")
        return

    # Find the service module
    service_path = Path(__file__).parent / "service.py"
    python = sys.executable

    cmd = [python, str(service_path)]
    if getattr(args, "headless", False):
        cmd.append("--headless")
    if getattr(args, "verbose", False):
        cmd.append("--verbose")

    if getattr(args, "test", False):
        cmd.append("--test")
        # In test mode, run in foreground
        os.execvp(python, cmd)
    elif getattr(args, "verbose", False):
        # Verbose mode: run in foreground with full console output
        print("Starting Jarvis in verbose mode (foreground)...")
        print("Press Ctrl+C to stop.\n")
        try:
            proc = subprocess.run(cmd)
            sys.exit(proc.returncode)
        except KeyboardInterrupt:
            print("\nJarvis stopped.")
    else:
        # Daemonize (background mode)
        pid_file = _get_pid_file()
        pid_file.parent.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            # Use pythonw.exe for windowless background process
            pythonw = python.replace("python.exe", "pythonw.exe")
            if Path(pythonw).exists():
                cmd[0] = pythonw
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        pid_file.write_text(str(proc.pid))
        print(f"Jarvis started (PID {proc.pid})")

        # Health check: wait for IPC port file to confirm startup
        port_file = _get_port_file()
        print("Waiting for Jarvis to initialize...", end="", flush=True)
        for _ in range(20):  # wait up to 10 seconds
            time.sleep(0.5)
            if port_file.exists():
                print(" ready!")
                return
            # Check if process died
            if sys.platform == "win32":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {proc.pid}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                if str(proc.pid) not in result.stdout:
                    print(" FAILED")
                    print("Jarvis process exited. Run 'jarvis start --verbose' to see errors.")
                    pid_file.unlink(missing_ok=True)
                    return
            else:
                if proc.poll() is not None:
                    print(" FAILED")
                    print("Jarvis process exited. Run 'jarvis start --verbose' to see errors.")
                    pid_file.unlink(missing_ok=True)
                    return
        print(" timeout (may still be loading)")


def cmd_devices(args):
    """List available audio input devices."""
    try:
        import sounddevice
        devices = sounddevice.query_devices()
        default_in = sounddevice.default.device[0]

        print("Available audio input devices:")
        print("-" * 50)
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                marker = " ← DEFAULT" if i == default_in else ""
                print(f"  [{i}] {d['name']} ({d['max_input_channels']} ch, {int(d['default_samplerate'])} Hz){marker}")
        print()
        print("To use a specific device, add to ~/.jarvis/config.yaml:")
        print("  audio_input_device: <number>")
    except ImportError:
        print("sounddevice not installed. Run: pip install sounddevice")
    except Exception as e:
        print(f"Error listing devices: {e}")


def cmd_stop(args):
    """Stop the Jarvis daemon."""
    pid_file = _get_pid_file()
    if not pid_file.exists():
        print("Jarvis is not running.")
        return

    # Try graceful IPC stop first
    response = asyncio.run(_send_ipc("__stop__"))
    if response:
        print("Jarvis stopping gracefully...")
        # Wait briefly for process to exit
        try:
            pid = int(pid_file.read_text().strip())
            for _ in range(30):  # wait up to 3 seconds
                if not _is_daemon_running():
                    break
                time.sleep(0.1)
        except (ValueError, OSError):
            pass
    else:
        # Fallback: kill the process directly
        try:
            pid = int(pid_file.read_text().strip())
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            print(f"Jarvis stopped (PID {pid})")
        except (ValueError, OSError) as e:
            print(f"Failed to stop Jarvis: {e}")

    pid_file.unlink(missing_ok=True)
    port_file = _get_port_file()
    port_file.unlink(missing_ok=True)


def cmd_restart(args):
    """Restart the Jarvis daemon."""
    cmd_stop(args)
    cmd_start(args)


def cmd_status(args):
    """Show daemon status."""
    if _is_daemon_running():
        pid = _get_pid_file().read_text().strip()
        response = asyncio.run(_send_ipc("__status__"))
        status = response or "unknown"
        print(f"Jarvis is running (PID {pid}, status: {status})")
    else:
        print("Jarvis is not running.")


def cmd_text(args):
    """Send a text command to the daemon."""
    query = " ".join(args.query)
    if not query:
        print("Usage: jarvis text \"your command\"")
        return

    if not _is_daemon_running():
        print("Jarvis is not running. Use 'jarvis start' first.")
        return

    response = asyncio.run(_send_ipc(query))
    if response:
        print(f"Jarvis: {response}")
    else:
        print("No response from Jarvis (is the daemon running?)")


def cmd_log(args):
    """Tail today's conversation log."""
    log_path = Path("~/.jarvis/conversations").expanduser() / f"{date.today().isoformat()}.jsonl"
    if not log_path.exists():
        print("No conversation log for today.")
        return

    try:
        with open(log_path, "r") as f:
            # Print last 20 lines
            lines = f.readlines()
            for line in lines[-20:]:
                print(line, end="")
            # Follow new lines
            print("\n--- Following log (Ctrl+C to stop) ---")
            while True:
                line = f.readline()
                if line:
                    print(line, end="")
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def cmd_config(args):
    """Open config file in $EDITOR."""
    config_path = Path("~/.jarvis/config.yaml").expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        config_path.write_text(
            "# Jarvis AI Configuration\n"
            "# See docs for all options\n\n"
            "gemini_model: gemini-2.0-flash\n"
            "whisper_model_size: base.en\n"
            "tts_engine: pyttsx3\n"
            "clap_sensitivity: 0.7\n"
        )

    if sys.platform == "win32":
        editor = os.environ.get("EDITOR", "notepad")
    else:
        editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(config_path)])


def cmd_install(args):
    """Install Jarvis via GUI wizard (or CLI with --no-gui)."""
    skip_autostart = os.environ.get("JARVIS_SKIP_AUTOSTART", "").strip().lower() in {"1", "true", "yes"}
    if getattr(args, "no_gui", False):
        from jarvis.daemon.installer import install
        install(enable_autostart=not skip_autostart)
    else:
        try:
            from jarvis.face.installer_wizard import install_gui
            install_gui()
        except ImportError:
            print("PyQt6 not available -- falling back to CLI installer.")
            from jarvis.daemon.installer import install
            install(enable_autostart=not skip_autostart)


def cmd_uninstall(args):
    """Remove Jarvis auto-start."""
    from jarvis.daemon.installer import uninstall
    uninstall()


def cmd_calibrate(args):
    """Re-run clap detection calibration."""
    print("Calibrating clap detection...")
    print("Please be quiet for 3 seconds...")

    from jarvis.activation.clap_detector import ClapDetector

    detector = ClapDetector(on_clap=lambda: None)
    detector.calibrate()
    print("Calibration complete!")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Jarvis AI Desktop Assistant",
    )
    subparsers = parser.add_subparsers(dest="command")

    # start
    start_parser = subparsers.add_parser("start", help="Start Jarvis daemon")
    start_parser.add_argument("--test", "--text", action="store_true", help="Text mode")
    start_parser.add_argument("--headless", action="store_true", help="No GUI (lower RAM)")
    start_parser.add_argument("--verbose", "-v", action="store_true", help="Run in foreground with full output")
    start_parser.set_defaults(func=cmd_start)

    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop Jarvis daemon")
    stop_parser.set_defaults(func=cmd_stop)

    # restart
    restart_parser = subparsers.add_parser("restart", help="Restart Jarvis daemon")
    restart_parser.set_defaults(func=cmd_restart)

    # status
    status_parser = subparsers.add_parser("status", help="Show daemon status")
    status_parser.set_defaults(func=cmd_status)

    # text
    text_parser = subparsers.add_parser("text", help="Send text command")
    text_parser.add_argument("query", nargs="+", help="Command text")
    text_parser.set_defaults(func=cmd_text)

    # log
    log_parser = subparsers.add_parser("log", help="Tail conversation log")
    log_parser.set_defaults(func=cmd_log)

    # config
    config_parser = subparsers.add_parser("config", help="Open config file")
    config_parser.set_defaults(func=cmd_config)

    # install
    install_parser = subparsers.add_parser("install", help="Install via GUI wizard")
    install_parser.add_argument("--no-gui", action="store_true", help="CLI-only install")
    install_parser.set_defaults(func=cmd_install)

    # setup (alias for install)
    setup_parser = subparsers.add_parser("setup", help="Setup wizard (alias for install)")
    setup_parser.add_argument("--no-gui", action="store_true", help="CLI-only install")
    setup_parser.set_defaults(func=cmd_install)

    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="Remove auto-start")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # calibrate
    calibrate_parser = subparsers.add_parser("calibrate", help="Calibrate clap detection")
    calibrate_parser.set_defaults(func=cmd_calibrate)

    # devices
    devices_parser = subparsers.add_parser("devices", help="List audio input devices")
    devices_parser.set_defaults(func=cmd_devices)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
