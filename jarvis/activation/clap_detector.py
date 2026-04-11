"""Double-clap detector using short-time energy onset detection.

Algorithm:
    1. Stream 16 kHz mono audio via sounddevice.
    2. Compute energy in 20 ms windows (320 samples).
    3. Detect onset when energy exceeds an adaptive threshold.
    4. After first onset, open a 700 ms window for a second onset.
    5. If the second onset arrives 200-600 ms after the first -> clap detected.
    6. Debounce: suppress further detections for 1.5 s after a successful pair.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import numpy as np

from jarvis.activation.audio_devices import resolve_input_device, stream_device_kwargs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16_000
CHANNELS = 1
BLOCK_SIZE = 320  # 20 ms at 16 kHz
CALIBRATION_DURATION_S = 3.0
MIN_GAP_S = 0.200  # minimum gap between two claps
MAX_GAP_S = 0.600  # maximum gap between two claps
WINDOW_S = 0.700  # listening window after first onset
DEBOUNCE_S = 1.5  # ignore new pairs for this long after detection


class ClapDetector:
    """Detect a double-clap pattern on the default microphone.

    Parameters
    ----------
    on_clap:
        Callback fired (from audio thread) when a valid double-clap is
        detected.  Keep it fast — offload heavy work elsewhere.
    sensitivity:
        0.0 (least sensitive / highest threshold) to 1.0 (most sensitive).
        Default 0.7.
    """

    def __init__(
        self,
        on_clap: Callable[[], None],
        sensitivity: float = 0.7,
        device_index: int | None = None,
        preferred_device_name: str = "",
        auto_detect_microphone: bool = True,
        min_gap_ms: int = 200,
        max_gap_ms: int = 600,
    ) -> None:
        if not 0.0 <= sensitivity <= 1.0:
            raise ValueError("sensitivity must be in [0.0, 1.0]")

        self._on_clap = on_clap
        self._sensitivity = sensitivity
        self._device_index = device_index
        self._preferred_device_name = preferred_device_name
        self._auto_detect_microphone = auto_detect_microphone
        self._resolved_device_index: int | None = None
        self._min_gap_s = max(0.05, min_gap_ms / 1000.0)
        self._max_gap_s = max(self._min_gap_s, max_gap_ms / 1000.0)
        self._window_s = max(self._max_gap_s + 0.1, WINDOW_S)

        # Threshold state
        self._ambient_energy: float = 0.0
        self._threshold: float = 0.0
        self._calibrated = threading.Event()

        # Detection state (accessed only from audio callback thread)
        self._first_onset_time: float | None = None
        self._last_detection_time: float = 0.0

        # Stream management
        self._stream: "sounddevice.InputStream | None" = None
        self._running = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the mic stream and begin listening for claps.

        If the detector has not been calibrated yet, the first 3 seconds of
        audio are used for ambient noise calibration before detection begins.
        """
        import sounddevice  # imported lazily so tests can mock it

        with self._lock:
            if self._running:
                logger.warning("ClapDetector already running")
                return

            self._running = True
            self._first_onset_time = None
            self._last_detection_time = 0.0

            if not self._calibrated.is_set():
                self._calibration_frames: list[np.ndarray] = []
                self._calibration_start: float = time.monotonic()

            device = resolve_input_device(
                preferred_index=self._device_index,
                preferred_name=self._preferred_device_name,
                auto_detect=self._auto_detect_microphone,
            )
            self._resolved_device_index = device.index

            self._stream = sounddevice.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
                **stream_device_kwargs(device),
            )
            self._stream.start()
            logger.info(
                "ClapDetector started (sensitivity=%.2f, device=%s)",
                self._sensitivity,
                device.name,
            )

    def stop(self) -> None:
        """Stop listening and release the mic stream."""
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
            logger.info("ClapDetector stopped")

    def calibrate(self) -> None:
        """Block for ~3 seconds while sampling ambient noise.

        Sets the adaptive threshold based on ambient energy.  If the stream
        is already running the calibration happens inline; otherwise a
        temporary stream is opened and closed.
        """
        import sounddevice

        frames: list[np.ndarray] = []
        duration_samples = int(CALIBRATION_DURATION_S * SAMPLE_RATE)
        collected = 0

        def _cal_callback(
            indata: np.ndarray, frames_count: int, time_info: object, status: object
        ) -> None:
            nonlocal collected
            frames.append(indata.copy())
            collected += frames_count

        device = resolve_input_device(
            preferred_index=self._device_index,
            preferred_name=self._preferred_device_name,
            auto_detect=self._auto_detect_microphone,
        )
        self._resolved_device_index = device.index

        stream = sounddevice.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=_cal_callback,
            **stream_device_kwargs(device),
        )
        stream.start()

        # Wait until we have enough samples
        deadline = time.monotonic() + CALIBRATION_DURATION_S + 1.0
        while collected < duration_samples and time.monotonic() < deadline:
            time.sleep(0.05)

        stream.stop()
        stream.close()

        self._finish_calibration(frames)
        logger.info(
            "Calibration complete — ambient_energy=%.6f  threshold=%.6f",
            self._ambient_energy,
            self._threshold,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _finish_calibration(self, frames: list[np.ndarray]) -> None:
        """Compute threshold from collected calibration frames."""
        if not frames:
            # Fallback: use a fixed conservative threshold
            self._ambient_energy = 1e-6
            self._threshold = 0.005
            self._calibrated.set()
            return

        all_audio = np.concatenate(frames, axis=0).flatten()
        # Mean energy per 20 ms window
        n_windows = len(all_audio) // BLOCK_SIZE
        if n_windows == 0:
            self._ambient_energy = float(np.mean(all_audio ** 2))
        else:
            windows = all_audio[: n_windows * BLOCK_SIZE].reshape(n_windows, BLOCK_SIZE)
            energies = np.mean(windows ** 2, axis=1)
            self._ambient_energy = float(np.mean(energies))

        # Threshold: scale above ambient.  Higher sensitivity → lower
        # multiplier (easier to trigger).
        #   sensitivity 1.0 → multiplier  2
        #   sensitivity 0.5 → multiplier  7
        #   sensitivity 0.0 → multiplier 12
        multiplier = 2.0 + (1.0 - self._sensitivity) * 10.0
        self._threshold = max(self._ambient_energy * multiplier, 1e-5)
        self._calibrated.set()

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        """Called from the sounddevice portaudio thread for every 20 ms block."""
        if not self._running:
            return

        # --- inline calibration (first 3 s after start) ---
        if not self._calibrated.is_set():
            self._calibration_frames.append(indata.copy())
            elapsed = time.monotonic() - self._calibration_start
            if elapsed >= CALIBRATION_DURATION_S:
                self._finish_calibration(self._calibration_frames)
                del self._calibration_frames
                logger.info(
                    "Inline calibration done — threshold=%.6f", self._threshold
                )
            return  # skip detection while calibrating

        # --- compute energy for this block ---
        block = indata[:, 0] if indata.ndim == 2 else indata
        energy = float(np.mean(block ** 2))

        now = time.monotonic()

        # --- debounce ---
        if now - self._last_detection_time < DEBOUNCE_S:
            self._first_onset_time = None
            return

        is_onset = energy > self._threshold

        if self._first_onset_time is None:
            # Waiting for first clap
            if is_onset:
                self._first_onset_time = now
        else:
            gap = now - self._first_onset_time

            if gap > self._window_s:
                # Window expired — reset
                self._first_onset_time = None
                # Re-check current frame as potential new first onset
                if is_onset:
                    self._first_onset_time = now
            elif is_onset and self._min_gap_s <= gap <= self._max_gap_s:
                # Valid double-clap!
                self._last_detection_time = now
                self._first_onset_time = None
                logger.info("Double-clap detected (gap=%.3f s)", gap)
                try:
                    self._on_clap()
                except Exception:
                    logger.exception("Error in on_clap callback")

    @property
    def resolved_device_index(self) -> int | None:
        return self._resolved_device_index
