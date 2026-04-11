"""Wake word detection using Porcupine (Picovoice).

Listens for the wake word "Jarvis" (or a configured keyword) using
the Porcupine wake word engine.  Requires a free Picovoice access key
from https://console.picovoice.ai/.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np

from jarvis.activation.audio_devices import resolve_input_device, stream_device_kwargs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency
# ---------------------------------------------------------------------------
try:
    import pvporcupine  # type: ignore[import-untyped]

    _HAS_PORCUPINE = True
except ImportError:
    pvporcupine = None  # type: ignore[assignment]
    _HAS_PORCUPINE = False
    logger.warning(
        "pvporcupine is not installed — WakeWordDetector will be unavailable. "
        "Install with: pip install pvporcupine"
    )


class WakeWordDetector:
    """Detect a wake word using Porcupine.

    Parameters
    ----------
    on_wake_word:
        Callback fired (from the audio-processing thread) when the wake
        word is detected.  Keep it fast — offload heavy work elsewhere.
    access_key:
        Picovoice access key (free tier from console.picovoice.ai).
    keyword:
        Built-in keyword name (default ``"jarvis"``).
    device_index:
        Audio input device index (``None`` = system default).
    """

    def __init__(
        self,
        on_wake_word: Callable[[], None],
        access_key: str = "",
        keyword: str = "jarvis",
        device_index: int | None = None,
        preferred_device_name: str = "",
        auto_detect_microphone: bool = True,
    ) -> None:
        self._on_wake_word = on_wake_word
        self._access_key = access_key
        self._keyword = keyword
        self._device_index = device_index
        self._preferred_device_name = preferred_device_name
        self._auto_detect_microphone = auto_detect_microphone
        self._resolved_device_index: int | None = None

        self._porcupine: "pvporcupine.Porcupine | None" = None  # type: ignore[name-defined]
        self._stream: "sounddevice.InputStream | None" = None  # type: ignore[name-defined]
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the mic stream and begin listening for the wake word."""
        import sounddevice  # imported lazily so tests can mock it

        if not _HAS_PORCUPINE:
            logger.error(
                "Cannot start WakeWordDetector — pvporcupine is not installed"
            )
            return

        if not self._access_key:
            logger.warning(
                "Picovoice access_key is empty — WakeWordDetector will not start. "
                "Get a free key at https://console.picovoice.ai/"
            )
            return

        with self._lock:
            if self._running:
                logger.warning("WakeWordDetector already running")
                return

            try:
                self._porcupine = pvporcupine.create(
                    access_key=self._access_key,
                    keywords=[self._keyword],
                )
            except Exception:
                logger.exception("Failed to create Porcupine engine")
                return

            frame_length = self._porcupine.frame_length
            sample_rate = self._porcupine.sample_rate

            self._running = True
            device = resolve_input_device(
                preferred_index=self._device_index,
                preferred_name=self._preferred_device_name,
                auto_detect=self._auto_detect_microphone,
            )
            self._resolved_device_index = device.index

            self._stream = sounddevice.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=frame_length,
                callback=self._audio_callback,
                **stream_device_kwargs(device),
            )
            self._stream.start()
            logger.info(
                "WakeWordDetector started (keyword=%r, rate=%d, frame=%d, device=%s)",
                self._keyword,
                sample_rate,
                frame_length,
                device.name,
            )

    def stop(self) -> None:
        """Stop listening and release all resources."""
        with self._lock:
            self._running = False

            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    logger.exception("Error closing audio stream")
                finally:
                    self._stream = None

            if self._porcupine is not None:
                try:
                    self._porcupine.delete()
                except Exception:
                    logger.exception("Error deleting Porcupine engine")
                finally:
                    self._porcupine = None

            logger.info("WakeWordDetector stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        """Called from the sounddevice portaudio thread for each audio block."""
        if not self._running or self._porcupine is None:
            return

        if status:
            logger.debug("Audio stream status: %s", status)

        # indata is float32 in [-1.0, 1.0]; Porcupine expects int16
        block = indata[:, 0] if indata.ndim == 2 else indata
        pcm = (block * 32767).astype(np.int16)

        try:
            keyword_index = self._porcupine.process(pcm)
        except Exception:
            logger.exception("Porcupine processing error")
            return

        if keyword_index >= 0:
            logger.info("Wake word detected: %r", self._keyword)
            try:
                self._on_wake_word()
            except Exception:
                logger.exception("Error in on_wake_word callback")

    @property
    def resolved_device_index(self) -> int | None:
        return self._resolved_device_index
