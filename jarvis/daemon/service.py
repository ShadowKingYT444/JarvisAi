"""Jarvis main daemon service -- persistent background process.

Orchestrates all subsystems: clap detection, STT, brain, tools,
TTS, and GUI. Entry point for both daemon and test modes.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import logging
import os
import signal
import sys
from pathlib import Path

logger = logging.getLogger("jarvis")


def _resolve_audio_device(config) -> tuple[int | None, str]:
    """Return the best current audio input device and its display name."""
    try:
        import sounddevice

        devices = sounddevice.query_devices()
        device_index = config.resolve_audio_input_device()

        if device_index is not None and 0 <= device_index < len(devices):
            device = devices[device_index]
            if device.get("max_input_channels", 0) > 0:
                return device_index, device["name"]

        default_in = None
        try:
            default_in = sounddevice.default.device[0]
        except Exception:
            default_in = None

        if default_in is not None and 0 <= default_in < len(devices):
            device = devices[default_in]
            if device.get("max_input_channels", 0) > 0:
                return default_in, device["name"]

        for idx, device in enumerate(devices):
            if device.get("max_input_channels", 0) > 0:
                return idx, device["name"]
    except Exception:
        logger.debug("Failed to resolve audio input device", exc_info=True)

    return config.audio_input_device, "unknown"

async def _run_boot_sequence(speech_queue, config, state_mgr) -> None:
    """Run the initial Jarvis boot sequence after the first double-clap."""
    from jarvis.daemon.startup_sequence import run_startup_sequence

    try:
        await run_startup_sequence(config, state_mgr, speech_queue)
    except Exception:
        logger.exception("Boot sequence failed")


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
        selected, selected_name = _resolve_audio_device(config)
        if selected is not None and 0 <= selected < len(devices):
            logger.info("Using audio input device: [%d] %s", selected, devices[selected]['name'])
            print(f"  [OK] Audio device: {devices[selected]['name']}")
        else:
            logger.info("Using audio input device: %s", selected_name)
            print(f"  [OK] Audio device: {selected_name}")
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
    from jarvis.activation.clap_detector import ClapDetector
    from jarvis.activation.mic_manager import MicManager
    from jarvis.activation.wake_word import WakeWordDetector
    from jarvis.ears.stt_engine import STTEngine
    loop = asyncio.get_running_loop()
    processing_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    current_device_index, current_device_name = _resolve_audio_device(config)
    startup_complete = bool(
        config.startup_initialized_session
        or not config.startup_enabled
        or not config.require_initialization_clap
    )
    config.startup_initialized_session = startup_complete
    wake_word_enabled = bool(config.porcupine_access_key)
    clap_detector: ClapDetector | None = None
    wake_word_detector: WakeWordDetector | None = None
    hotkey_listener = None
    hotkey_enabled = "hotkey" in config.activation_methods

    def _spawn(coro) -> None:
        """Schedule *coro* safely from PortAudio / hotkey threads."""
        loop.call_soon_threadsafe(lambda: asyncio.create_task(coro))

    def _make_mic_manager(device_index: int | None) -> MicManager:
        timeout_s = max(float(config.max_record_s) + 10.0, 30.0)
        return MicManager(
            sample_rate=16000,
            device_index=device_index,
            inactivity_timeout_s=timeout_s,
            preferred_device_name=config.preferred_microphone_name,
            auto_detect_microphone=config.auto_detect_microphone,
        )

    async def _start_wake_word_detector(device_index: int | None) -> None:
        nonlocal wake_word_detector
        if not wake_word_enabled:
            return
        if wake_word_detector is not None:
            wake_word_detector.stop()

        try:
            wake_word_detector = WakeWordDetector(
                on_wake_word=lambda: _spawn(_handle_wake_word()),
                access_key=config.porcupine_access_key,
                keyword=config.wake_word_keyword,
                device_index=device_index,
                preferred_device_name=config.preferred_microphone_name,
                auto_detect_microphone=config.auto_detect_microphone,
            )
            wake_word_detector.start()
            logger.info(
                'Wake word "%s" armed on device [%s] %s',
                config.wake_word_keyword,
                device_index,
                current_device_name,
            )
        except Exception:
            logger.exception("Wake word detector failed to start")
            wake_word_detector = None

    async def _start_hotkey_listener() -> None:
        nonlocal hotkey_listener
        if not hotkey_enabled or hotkey_listener is not None:
            return
        try:
            from jarvis.activation.hotkey import HotkeyListener

            hotkey_listener = HotkeyListener(
                on_hotkey=lambda: _spawn(_handle_hotkey()),
                hotkey=config.hotkey,
            )
            hotkey_listener.start()
            logger.info("Hotkey listener started (%s)", config.hotkey)
        except Exception:
            logger.exception("Hotkey listener failed to start")
            hotkey_listener = None

    async def _start_clap_detector(device_index: int | None) -> None:
        nonlocal clap_detector
        clap_detector = ClapDetector(
            on_clap=lambda: _spawn(_handle_initial_clap()),
            sensitivity=config.clap_sensitivity,
            device_index=device_index,
            preferred_device_name=config.preferred_microphone_name,
            auto_detect_microphone=config.auto_detect_microphone,
            min_gap_ms=config.clap_min_gap_ms,
            max_gap_ms=config.clap_timeout_ms,
        )
        try:
            await asyncio.to_thread(clap_detector.calibrate)
        except Exception:
            logger.exception("Clap calibration failed; continuing with inline calibration")
        clap_detector.start()
        logger.info(
            "Clap detector armed on device [%s] %s (sensitivity=%.2f)",
            device_index,
            current_device_name,
            config.clap_sensitivity,
        )

    async def _run_command_cycle(trigger: str) -> None:
        nonlocal current_device_index, current_device_name
        if processing_lock.locked():
            return

        async with processing_lock:
            if wake_word_detector is not None:
                wake_word_detector.stop()

            device_index, device_name = _resolve_audio_device(config)
            current_device_index, current_device_name = device_index, device_name
            mic_manager = _make_mic_manager(device_index)
            stt_engine = STTEngine(
                model_size=config.whisper_model_size,
                mic_manager=mic_manager,
                event_bus=event_bus,
                config=config,
            )

            state_mgr.set_state(JarvisState.LISTENING)
            try:
                result = await stt_engine.listen()
                if result.text.strip():
                    await process_command(result.text)
                else:
                    state_mgr.set_state(JarvisState.IDLE)
            except Exception:
                logger.exception("Error in command cycle triggered by %s", trigger)
                state_mgr.set_state(JarvisState.IDLE)
            finally:
                if startup_complete and wake_word_enabled:
                    await _start_wake_word_detector(current_device_index)

    async def _handle_initial_clap() -> None:
        nonlocal startup_complete
        if startup_complete or processing_lock.locked():
            return

        async with processing_lock:
            if startup_complete:
                return

            if clap_detector is not None:
                clap_detector.stop()

            state_mgr.set_state(
                JarvisState.INITIALIZING,
                {"text": "Double clap detected. Initializing Jarvis."},
            )
            await _run_boot_sequence(speech_queue, config, state_mgr)
            config.startup_initialized_session = True
            startup_complete = True
            state_mgr.set_state(JarvisState.IDLE)

            if wake_word_enabled:
                await _start_wake_word_detector(current_device_index)

            if hotkey_enabled:
                await _start_hotkey_listener()

    async def _handle_wake_word() -> None:
        if not startup_complete:
            return
        await _run_command_cycle("wake_word")

    async def _handle_hotkey() -> None:
        if not startup_complete:
            return
        await _run_command_cycle("hotkey")

    # Start IPC listener
    ipc_task = asyncio.create_task(
        _run_ipc_server(config, process_command)
    )

    # Try to set up GUI (optional -- works without it)
    if not headless:
        _try_setup_gui(event_bus, config)
    else:
        logger.info("Headless mode -- skipping GUI")

    if startup_complete:
        print("  [OK] Initialization already completed this session")
        if wake_word_enabled:
            await _start_wake_word_detector(current_device_index)
        if hotkey_enabled:
            await _start_hotkey_listener()
    else:
        if config.startup_enabled and config.require_initialization_clap:
            print("  [OK] Double-clap initialization armed")
            logger.info(
                "Waiting for initial double-clap on device [%s] %s",
                current_device_index,
                current_device_name,
            )
            await _start_clap_detector(current_device_index)
        elif wake_word_enabled:
            print("  [OK] Wake word enabled")
            await _start_wake_word_detector(current_device_index)
            if hotkey_enabled:
                await _start_hotkey_listener()
        elif hotkey_enabled:
            print("  [OK] Hotkey enabled")
            await _start_hotkey_listener()

    state_mgr.set_state(JarvisState.IDLE)

    async def _watch_audio_devices() -> None:
        nonlocal current_device_index, current_device_name
        if not config.auto_detect_microphone:
            return

        poll_s = max(1, int(config.microphone_poll_interval_s))
        while not stop_event.is_set():
            await asyncio.sleep(poll_s)

            if processing_lock.locked():
                continue

            device_index, device_name = _resolve_audio_device(config)
            if device_index == current_device_index:
                continue

            logger.info(
                "Audio input changed from [%s] %s to [%s] %s",
                current_device_index,
                current_device_name,
                device_index,
                device_name,
            )
            current_device_index, current_device_name = device_index, device_name

            if not startup_complete and clap_detector is not None:
                clap_detector.stop()
                await _start_clap_detector(current_device_index)
            elif startup_complete and wake_word_enabled:
                await _start_wake_word_detector(current_device_index)

    audio_watch_task = asyncio.create_task(_watch_audio_devices())

    # Keep running
    def _handle_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

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
    if clap_detector is not None:
        clap_detector.stop()
    if wake_word_detector is not None:
        wake_word_detector.stop()
    if hotkey_listener is not None:
        hotkey_listener.stop()
    if audio_watch_task is not None:
        audio_watch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await audio_watch_task
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
