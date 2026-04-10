"""Jarvis CLI — lightweight interface to the running daemon.

Communicates with the daemon over a Unix domain socket (macOS/Linux)
or named pipe (Windows).

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
import subprocess
import sys
from datetime import date
from pathlib import Path


def _get_socket_path() -> Path:
    return Path("~/.jarvis/jarvis.sock").expanduser()


def _get_pid_file() -> Path:
    return Path("~/.jarvis/jarvis.pid").expanduser()


async def _send_ipc(message: str) -> str | None:
    """Send a message to the running daemon and return the response."""
    socket_path = _get_socket_path()
    if not socket_path.exists():
        return None

    try:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
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
        os.kill(pid, 0)  # signal 0 = check if process exists
        return True
    except (ValueError, OSError):
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
    if getattr(args, "test", False):
        cmd.append("--test")
        # In test mode, run in foreground
        os.execvp(python, cmd)
    else:
        # Daemonize
        pid_file = _get_pid_file()
        pid_file.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid_file.write_text(str(proc.pid))
        print(f"Jarvis started (PID {proc.pid})")


def cmd_stop(args):
    """Stop the Jarvis daemon."""
    pid_file = _get_pid_file()
    if not pid_file.exists():
        print("Jarvis is not running.")
        return

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 15)  # SIGTERM
        print(f"Jarvis stopped (PID {pid})")
        pid_file.unlink(missing_ok=True)
    except (ValueError, OSError) as e:
        print(f"Failed to stop Jarvis: {e}")
        pid_file.unlink(missing_ok=True)

    # Clean up socket
    socket_path = _get_socket_path()
    if socket_path.exists():
        socket_path.unlink()


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
        subprocess.run(["tail", "-f", str(log_path)])
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
            "tts_engine: macos_say\n"
            "tts_voice: Daniel\n"
            "clap_sensitivity: 0.7\n"
        )

    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, str(config_path)])


def cmd_install(args):
    """Install Jarvis auto-start."""
    from jarvis.daemon.installer import install
    install()


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
    install_parser = subparsers.add_parser("install", help="Install auto-start")
    install_parser.set_defaults(func=cmd_install)

    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="Remove auto-start")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # calibrate
    calibrate_parser = subparsers.add_parser("calibrate", help="Calibrate clap detection")
    calibrate_parser.set_defaults(func=cmd_calibrate)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
