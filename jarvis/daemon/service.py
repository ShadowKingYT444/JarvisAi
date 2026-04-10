"""Jarvis main daemon service — persistent background process.

Orchestrates all subsystems: clap detection, STT, brain, tools,
TTS, and GUI. Entry point for both daemon and test modes.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

logger = logging.getLogger("jarvis")


async def run_service(test_mode: bool = False) -> None:
    """Start the Jarvis daemon.

    Parameters
    ----------
    test_mode:
        If ``True``, disables mic/clap detection and reads commands
        from stdin instead (for CI and development).
    """
    from jarvis.shared.config import JarvisConfig
    from jarvis.shared.events import EventBus
    from jarvis.shared.types import JarvisState
    from jarvis.face.hud import StateManager

    # 1. Load config
    config = JarvisConfig.load()
    config.ensure_dirs()

    # 2. Set up logging
    _setup_logging(config)
    logger.info("Jarvis v2.0 starting (test_mode=%s)", test_mode)

    # 3. Event bus + state manager
    event_bus = EventBus()
    state_mgr = StateManager(event_bus=event_bus)

    # 4. Platform + tool executor
    from jarvis.hands.platform import get_platform
    from jarvis.hands.tool_executor import ToolExecutor

    platform = get_platform()
    tool_executor = ToolExecutor(platform=platform, config=config, event_bus=event_bus)

    # 5. Brain
    from jarvis.brain.orchestrator import BrainOrchestrator

    brain = BrainOrchestrator(
        tool_executor=tool_executor,
        config=config,
        event_bus=event_bus,
    )

    # 6. TTS + speech queue
    from jarvis.voice.tts_engine import TTSEngine
    from jarvis.voice.speech_queue import SpeechQueue

    tts_engine = TTSEngine(config=config)
    speech_queue = SpeechQueue(tts_engine=tts_engine, event_bus=event_bus)
    await speech_queue.start()

    # 7. Process a single command
    async def process_command(text: str) -> str:
        """Run one command through the full pipeline."""
        if not text.strip():
            return ""

        state_mgr.set_state(JarvisState.PROCESSING)

        try:
            response = await brain.process(text)

            if response.error:
                state_mgr.set_state(JarvisState.ERROR)
                await speech_queue.say(f"I ran into an issue: {response.error}")
                return response.error

            state_mgr.set_state(JarvisState.SPEAKING)
            await speech_queue.say(response.spoken_text)

            state_mgr.set_state(JarvisState.IDLE)
            return response.spoken_text

        except Exception:
            logger.exception("Error processing command")
            state_mgr.set_state(JarvisState.ERROR)
            await speech_queue.say("I ran into an unexpected error.")
            state_mgr.set_state(JarvisState.IDLE)
            return ""

    if test_mode:
        # --- Text mode: read from stdin ---
        await _run_text_mode(process_command, state_mgr)
    else:
        # --- Full mode: clap detection + STT + GUI ---
        await _run_full_mode(
            config=config,
            event_bus=event_bus,
            state_mgr=state_mgr,
            process_command=process_command,
            speech_queue=speech_queue,
        )


async def _run_text_mode(
    process_command,
    state_mgr,
) -> None:
    """Text-only mode for testing (no mic, no GUI)."""
    from jarvis.shared.types import JarvisState

    print("Jarvis v2.0 — Text Mode (type commands, Ctrl+C to quit)")
    print("-" * 50)

    loop = asyncio.get_event_loop()
    try:
        while True:
            try:
                text = await loop.run_in_executor(None, lambda: input("You: "))
            except EOFError:
                break

            text = text.strip()
            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                break

            result = await process_command(text)
            if result:
                print(f"Jarvis: {result}")
    except KeyboardInterrupt:
        pass

    print("\nJarvis shutting down.")


async def _run_full_mode(
    config,
    event_bus,
    state_mgr,
    process_command,
    speech_queue,
) -> None:
    """Full mode with clap detection, STT, and GUI."""
    from jarvis.shared.types import JarvisState
    from jarvis.activation.mic_manager import MicManager
    from jarvis.activation.clap_detector import ClapDetector
    from jarvis.ears.stt_engine import STTEngine

    # Mic manager
    mic_manager = MicManager(sample_rate=16000)

    # STT
    stt_engine = STTEngine(
        model_size=config.whisper_model_size,
        mic_manager=mic_manager,
        event_bus=event_bus,
        config=config,
    )

    # Command cycle triggered by clap
    processing_lock = asyncio.Lock()

    async def on_clap_async():
        if processing_lock.locked():
            return  # already processing a command

        async with processing_lock:
            state_mgr.set_state(JarvisState.LISTENING)
            try:
                result = await stt_engine.listen()
                if result.text.strip():
                    await process_command(result.text)
                else:
                    state_mgr.set_state(JarvisState.IDLE)
            except Exception:
                logger.exception("Error in command cycle")
                state_mgr.set_state(JarvisState.IDLE)

    def on_clap():
        asyncio.ensure_future(on_clap_async())

    # Clap detector
    clap_detector = ClapDetector(
        on_clap=on_clap,
        sensitivity=config.clap_sensitivity,
    )

    # Start IPC listener
    ipc_task = asyncio.create_task(
        _run_ipc_server(config, process_command)
    )

    # Try to set up GUI (optional — works without it)
    _try_setup_gui(event_bus, config)

    # Start clap detection
    logger.info("Starting clap detection — double-clap to activate")
    clap_detector.calibrate()
    clap_detector.start()
    state_mgr.set_state(JarvisState.IDLE)

    # Keep running
    stop_event = asyncio.Event()

    def _handle_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass  # Windows

    event_bus.on("quit_requested", lambda _: stop_event.set())

    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    clap_detector.stop()
    await speech_queue.stop()
    ipc_task.cancel()


async def _run_ipc_server(config, process_command) -> None:
    """Unix domain socket server for CLI ↔ daemon communication."""
    socket_path = Path(config.jarvis_home).expanduser() / "jarvis.sock"
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean up stale socket
    if socket_path.exists():
        socket_path.unlink()

    async def handle_client(reader, writer):
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=30)
            text = data.decode("utf-8").strip()

            if text == "__status__":
                response = "running"
            elif text == "__stop__":
                response = "stopping"
                # Will be handled by the main loop
            else:
                response = await process_command(text)

            writer.write(response.encode("utf-8"))
            await writer.drain()
        except Exception:
            logger.exception("IPC handler error")
        finally:
            writer.close()
            await writer.wait_closed()

    try:
        server = await asyncio.start_unix_server(
            handle_client, path=str(socket_path)
        )
        logger.info("IPC server listening on %s", socket_path)
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        if socket_path.exists():
            socket_path.unlink()


def _try_setup_gui(event_bus, config) -> None:
    """Attempt to set up system tray and overlay. Non-fatal if it fails."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            # No Qt event loop — skip GUI
            logger.info("No QApplication — GUI disabled (use daemon mode for GUI)")
            return

        from jarvis.face.tray import SystemTray
        from jarvis.face.overlay import OverlayHUD

        tray = SystemTray(app=app, event_bus=event_bus, config=config)
        tray.setup()

        overlay = OverlayHUD(event_bus=event_bus)
        overlay.setup()

        logger.info("GUI components initialized")
    except ImportError:
        logger.info("PyQt6 not available — running headless")
    except Exception:
        logger.exception("GUI setup failed — running headless")


def _setup_logging(config) -> None:
    """Configure logging to file and stderr."""
    log_dir = Path(config.log_dir).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "jarvis.log"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main():
    """Entry point for ``python -m jarvis.daemon.service``."""
    import argparse

    parser = argparse.ArgumentParser(description="Jarvis AI Daemon")
    parser.add_argument(
        "--test", "--text",
        action="store_true",
        dest="test_mode",
        help="Run in text mode (stdin commands, no mic/clap/GUI)",
    )
    args = parser.parse_args()

    asyncio.run(run_service(test_mode=args.test_mode))


if __name__ == "__main__":
    main()
