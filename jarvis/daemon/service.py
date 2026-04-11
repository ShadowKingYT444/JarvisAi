"""Jarvis main daemon service -- persistent background process.

Orchestrates all subsystems: clap detection, STT, brain, tools,
TTS, and GUI. Entry point for both daemon and test modes.
"""

from __future__ import annotations

import asyncio
import atexit
import datetime
import logging
import os
import signal
import sys
from pathlib import Path

logger = logging.getLogger("jarvis")


async def run_service(test_mode: bool = False, headless: bool = False) -> None:
    """Start the Jarvis daemon.

    Parameters
    ----------
    test_mode:
        If ``True``, disables mic/clap detection and reads commands
        from stdin instead (for CI and development).
    headless:
        If ``True``, skips all GUI initialization to save RAM.
    """
    from jarvis.shared.config import JarvisConfig
    from jarvis.shared.events import EventBus
    from jarvis.shared.types import JarvisState
    from jarvis.face.hud import StateManager

    # 1. Load config
    config = JarvisConfig.load()
    config.ensure_dirs()
    if config.headless:
        headless = True

    # 2. Set up logging
    _setup_logging(config)
    logger.info("Jarvis v2.0 starting (test_mode=%s, headless=%s)", test_mode, headless)

    # 3. Write PID file
    pid_path = Path(config.jarvis_home).expanduser() / "jarvis.pid"
    pid_path.write_text(str(os.getpid()))
    atexit.register(lambda: pid_path.unlink(missing_ok=True))

    # 4. Event bus + state manager
    event_bus = EventBus()
    state_mgr = StateManager(event_bus=event_bus)

    # 5. Brain + tools -- lazy-loaded on first command to reduce idle RAM
    _brain = None

    async def _get_brain():
        nonlocal _brain
        if _brain is None:
            from jarvis.hands.platform import get_platform
            from jarvis.hands.tool_executor import ToolExecutor
            from jarvis.brain.orchestrator import BrainOrchestrator

            platform = get_platform()
            tool_executor = ToolExecutor(platform=platform, config=config)
            _brain = BrainOrchestrator(
                tool_executor=tool_executor,
                config=config,
                event_bus=event_bus,
            )
            logger.info("Brain + tools loaded on first command")
        return _brain

    # 6. Log audio devices
    try:
        import sounddevice
        devices = sounddevice.query_devices()
        default_in = sounddevice.default.device[0]
        logger.info("Audio devices detected:")
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                marker = " [DEFAULT]" if i == default_in else ""
                logger.info("  [%d] %s (%d ch)%s", i, d['name'], d['max_input_channels'], marker)
        selected = config.audio_input_device if config.audio_input_device is not None else default_in
        logger.info("Using audio input device: [%d] %s", selected, devices[selected]['name'])
        print(f"  [OK] Audio device: {devices[selected]['name']}")
    except Exception:
        logger.exception("Failed to enumerate audio devices")
        print("  [!!] Audio device enumeration failed")

    # 7. TTS + speech queue
    from jarvis.voice.tts_engine import TTSEngine
    from jarvis.voice.speech_queue import SpeechQueue

    tts_engine = TTSEngine(config=config)
    speech_queue = SpeechQueue(tts_engine=tts_engine, event_bus=event_bus)
    await speech_queue.start()
    print(f"  [OK] TTS engine: {tts_engine.backend_name}")

    # 8. Process a single command
    async def process_command(text: str) -> str:
        """Run one command through the full pipeline."""
        if not text.strip():
            return ""

        state_mgr.set_state(JarvisState.PROCESSING)

        try:
            brain = await _get_brain()
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
            headless=headless,
        )


async def _run_text_mode(
    process_command,
    state_mgr,
) -> None:
    """Text-only mode for testing (no mic, no GUI)."""
    from jarvis.shared.types import JarvisState

    print("Jarvis v2.0 -- Text Mode (type commands, Ctrl+C to quit)")
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
    headless=False,
) -> None:
    """Full mode with clap detection, STT, and GUI."""
    from jarvis.shared.types import JarvisState
    from jarvis.activation.mic_manager import MicManager
    from jarvis.activation.clap_detector import ClapDetector
    from jarvis.ears.stt_engine import STTEngine

    device_idx = config.audio_input_device

    # Mic manager
    mic_manager = MicManager(sample_rate=16000, device_index=device_idx)

    # STT
    stt_engine = STTEngine(
        model_size=config.whisper_model_size,
        mic_manager=mic_manager,
        event_bus=event_bus,
        config=config,
    )

    # Clap detector
    clap_detector = ClapDetector(
        on_clap=lambda: None,  # replaced below
        sensitivity=config.clap_sensitivity,
        device_index=device_idx,
    )

    # Command cycle triggered by activation (clap, wake word, or hotkey)
    processing_lock = asyncio.Lock()

    async def on_activate_async():
        if processing_lock.locked():
            return  # already processing a command

        async with processing_lock:
            # Stop all audio-based detectors to release mic before STT
            clap_detector.stop()
            if wake_word_detector is not None:
                wake_word_detector.stop()
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
            finally:
                # Resume audio-based detectors after STT completes
                if "clap" in config.activation_methods:
                    clap_detector.start()
                if wake_word_detector is not None and "wake_word" in config.activation_methods:
                    try:
                        wake_word_detector.start()
                    except Exception:
                        logger.exception("Failed to restart wake word detector")

    def on_activate():
        asyncio.ensure_future(on_activate_async())

    # Wire up the clap callback
    clap_detector._on_clap = on_activate

    # Start IPC listener
    ipc_task = asyncio.create_task(
        _run_ipc_server(config, process_command)
    )

    # Try to set up GUI (optional -- works without it)
    if not headless:
        _try_setup_gui(event_bus, config)
    else:
        logger.info("Headless mode -- skipping GUI")

    # Start clap detection
    if "clap" in config.activation_methods:
        logger.info("Starting clap detection -- double-clap to activate")
        print("  [OK] Clap detection enabled (sensitivity=%.1f)" % config.clap_sensitivity)
        clap_detector.calibrate()
        clap_detector.start()
    else:
        print("  [--] Clap detection disabled")

    # Start wake word detection (if configured)
    wake_word_detector = None
    if "wake_word" in config.activation_methods:
        try:
            from jarvis.activation.wake_word import WakeWordDetector
            wake_word_detector = WakeWordDetector(
                on_wake_word=on_activate,
                access_key=config.porcupine_access_key,
                keyword=config.wake_word_keyword,
                device_index=device_idx,
            )
            wake_word_detector.start()
            print(f'  [OK] Wake word "{config.wake_word_keyword}" enabled')
            logger.info("Wake word detection started (keyword=%s)", config.wake_word_keyword)
        except Exception:
            logger.exception("Wake word detection failed to start")
            print('  [!!] Wake word detection failed (missing porcupine key?)')

    # Start hotkey detection (if configured)
    hotkey_listener = None
    if "hotkey" in config.activation_methods:
        try:
            from jarvis.activation.hotkey import HotkeyListener
            hotkey_listener = HotkeyListener(
                on_hotkey=on_activate,
                hotkey=config.hotkey,
            )
            hotkey_listener.start()
            print(f"  [OK] Hotkey {config.hotkey} enabled")
            logger.info("Hotkey listener started (%s)", config.hotkey)
        except Exception:
            logger.exception("Hotkey listener failed to start")
            print("  [!!] Hotkey listener failed")

    state_mgr.set_state(JarvisState.IDLE)

    # Boot greeting
    hour = datetime.datetime.now().hour
    if hour < 12:
        greeting = "Good morning sir."
    elif hour < 17:
        greeting = "Good afternoon sir."
    else:
        greeting = "Good evening sir."
    boot_msg = f"{greeting} Jarvis online. All systems operational."
    logger.info("Boot greeting: %s", boot_msg)
    print(f"\n  {boot_msg}\n")
    await speech_queue.say(boot_msg)

    # Keep running
    stop_event = asyncio.Event()

    def _handle_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()

    # Signal handling -- platform-aware
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except NotImplementedError:
                pass
    else:
        # Windows: use ctrl handler via signal module
        def _win_handler(signum, frame):
            stop_event.set()

        signal.signal(signal.SIGINT, _win_handler)
        signal.signal(signal.SIGTERM, _win_handler)

    event_bus.on("quit_requested", lambda _: stop_event.set())

    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    clap_detector.stop()
    if wake_word_detector is not None:
        wake_word_detector.stop()
    if hotkey_listener is not None:
        hotkey_listener.stop()
    await speech_queue.stop()
    ipc_task.cancel()

    # Clean up port file
    port_file = Path(config.jarvis_home).expanduser() / "jarvis.port"
    port_file.unlink(missing_ok=True)


async def _run_ipc_server(config, process_command) -> None:
    """TCP localhost server for CLI <-> daemon communication."""
    port_file = Path(config.jarvis_home).expanduser() / "jarvis.port"
    port_file.parent.mkdir(parents=True, exist_ok=True)

    stop_requested = asyncio.Event()

    async def handle_client(reader, writer):
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=30)
            text = data.decode("utf-8").strip()

            if text == "__status__":
                response = "running"
            elif text == "__stop__":
                response = "stopping"
                stop_requested.set()
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
        server = await asyncio.start_server(
            handle_client, "127.0.0.1", 0
        )
        # Write the assigned port so the CLI can find us
        port = server.sockets[0].getsockname()[1]
        port_file.write_text(str(port))
        logger.info("IPC server listening on 127.0.0.1:%d", port)

        async with server:
            # Wait for either server to be cancelled or stop requested
            stop_task = asyncio.create_task(stop_requested.wait())
            serve_task = asyncio.create_task(server.serve_forever())
            done, pending = await asyncio.wait(
                [stop_task, serve_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if stop_requested.is_set():
                # Raise KeyboardInterrupt to trigger main loop shutdown
                raise KeyboardInterrupt("Stop requested via IPC")
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        raise
    finally:
        port_file.unlink(missing_ok=True)


def _try_setup_gui(event_bus, config) -> None:
    """Attempt to set up system tray and overlay. Non-fatal if it fails."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            # No Qt event loop -- skip GUI
            logger.info("No QApplication -- GUI disabled (use daemon mode for GUI)")
            return

        from jarvis.face.tray import SystemTray
        from jarvis.face.overlay import OverlayHUD

        tray = SystemTray(app=app, event_bus=event_bus, config=config)
        tray.setup()

        overlay = OverlayHUD(event_bus=event_bus)
        overlay.setup()

        logger.info("GUI components initialized")
    except ImportError:
        logger.info("PyQt6 not available -- running headless")
    except Exception:
        logger.exception("GUI setup failed -- running headless")


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
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Skip GUI initialization to reduce RAM usage",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Run in foreground with full console output",
    )
    args = parser.parse_args()

    use_gui = not args.test_mode and not args.headless

    if use_gui:
        # Set DPI awareness on Windows before creating QApplication
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                pass

        try:
            from PyQt6.QtWidgets import QApplication
            import qasync

            app = QApplication(sys.argv)
            app.setQuitOnLastWindowClosed(False)  # keep running as tray app
            loop = qasync.QEventLoop(app)
            asyncio.set_event_loop(loop)

            with loop:
                loop.run_until_complete(
                    run_service(test_mode=False, headless=False)
                )
        except ImportError:
            logger.warning("PyQt6/qasync not available — falling back to headless")
            asyncio.run(run_service(test_mode=args.test_mode, headless=True))
    else:
        asyncio.run(run_service(test_mode=args.test_mode, headless=args.headless))


if __name__ == "__main__":
    main()
