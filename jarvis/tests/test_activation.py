"""Tests for the activation layer — clap detection and mic management.

All tests mock ``sounddevice`` so they run without audio hardware.
The fake sounddevice module is installed once at import time and stays
in ``sys.modules`` for the duration of the test session.
"""

from __future__ import annotations

import asyncio
import sys
import time as _real_time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers to build synthetic audio blocks
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16_000
BLOCK_SIZE = 320  # 20 ms at 16 kHz


def silent_block(energy: float = 1e-7) -> np.ndarray:
    """Return a 20 ms block of near-silent audio (float32, mono)."""
    amplitude = np.sqrt(energy)
    return np.full((BLOCK_SIZE, 1), amplitude, dtype=np.float32)


def loud_block(energy: float = 0.05) -> np.ndarray:
    """Return a 20 ms block simulating a clap (high energy)."""
    amplitude = np.sqrt(energy)
    return np.full((BLOCK_SIZE, 1), amplitude, dtype=np.float32)


# ---------------------------------------------------------------------------
# Fake sounddevice — installed permanently in sys.modules
# ---------------------------------------------------------------------------


class FakeInputStream:
    """A stand-in for ``sounddevice.InputStream`` that lets tests drive the
    audio callback manually."""

    def __init__(self, *, samplerate, channels, dtype, blocksize, callback):
        self.callback = callback
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.blocksize = blocksize
        self._started = False

    def start(self):
        self._started = True

    def stop(self):
        self._started = False

    def close(self):
        self._started = False

    def feed(self, block: np.ndarray) -> None:
        """Deliver *block* to the callback as if it came from PortAudio."""
        self.callback(block, len(block), None, None)


# Create and install the fake sounddevice module BEFORE importing any
# activation code, so the real sounddevice is never needed.
_fake_sd = MagicMock()
_fake_sd.InputStream = FakeInputStream
sys.modules.setdefault("sounddevice", _fake_sd)

# Now it is safe to import the activation modules — they will pick up the fake.
from jarvis.activation.clap_detector import ClapDetector  # noqa: E402
from jarvis.activation.mic_manager import (  # noqa: E402
    AudioStream,
    MicConflictError,
    MicManager,
    MicState,
)
import jarvis.activation.clap_detector as _clap_mod  # noqa: E402
import jarvis.activation.mic_manager as _mic_mod  # noqa: E402


# ===================================================================
# ClapDetector tests
# ===================================================================


class TestClapDetector:
    """Unit tests for ``ClapDetector``."""

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _make_detector(on_clap=None, sensitivity=0.7):
        cb = on_clap or MagicMock()
        det = ClapDetector(on_clap=cb, sensitivity=sensitivity)
        return det, cb

    @staticmethod
    def _start_detector(det):
        """Start the detector, return its internal FakeInputStream."""
        det.start()
        return det._stream

    @staticmethod
    def _precalibrate(det, ambient_energy=1e-6):
        """Pre-calibrate with known ambient energy so detection is
        immediately active (bypasses the time-based inline calibration)."""
        frames = [silent_block(energy=ambient_energy) for _ in range(10)]
        det._finish_calibration(frames)
        assert det._calibrated.is_set()

    @classmethod
    def _start_precalibrated(cls, det, ambient_energy=1e-6):
        cls._precalibrate(det, ambient_energy)
        stream = cls._start_detector(det)
        return stream

    @staticmethod
    def _feed_with_time(stream, blocks_and_types):
        """Feed blocks while controlling ``time.monotonic`` in the clap-
        detector module.

        *blocks_and_types* is ``[(block, count), ...]``.
        Each block advances virtual time by 20 ms.
        """
        base_time = 2000.0
        idx = [0]

        original_monotonic = _clap_mod.time.monotonic

        def fake_monotonic():
            return base_time + idx[0] * 0.020

        _clap_mod.time.monotonic = fake_monotonic
        try:
            for block, count in blocks_and_types:
                for _ in range(count):
                    stream.feed(block)
                    idx[0] += 1
        finally:
            _clap_mod.time.monotonic = original_monotonic

    # -- calibration -------------------------------------------------------

    def test_calibrate_explicit(self):
        """Explicit ``calibrate()`` sets ambient energy and threshold."""
        det, _ = self._make_detector()

        # Temporarily replace InputStream with one that auto-feeds data
        orig_cls = _fake_sd.InputStream

        class AutoFeedInputStream(FakeInputStream):
            def __init__(self_inner, **kw):
                super().__init__(**kw)
                n = int(3.0 * SAMPLE_RATE / BLOCK_SIZE) + 1
                for _ in range(n):
                    self_inner.callback(silent_block(), BLOCK_SIZE, None, None)

        _fake_sd.InputStream = AutoFeedInputStream
        try:
            det.calibrate()
        finally:
            _fake_sd.InputStream = orig_cls

        assert det._calibrated.is_set()
        assert det._ambient_energy > 0
        assert det._threshold > det._ambient_energy

    def test_inline_calibration_on_start(self):
        """When ``start()`` is called without prior calibration the first
        ~3 s of audio are used for inline calibration."""
        det, cb = self._make_detector()
        stream = self._start_detector(det)

        base_time = 5000.0
        idx = [0]
        original_monotonic = _clap_mod.time.monotonic

        def fake_monotonic():
            return base_time + idx[0] * 0.020

        _clap_mod.time.monotonic = fake_monotonic
        try:
            det._calibration_start = base_time
            n = int(3.0 * SAMPLE_RATE / BLOCK_SIZE) + 2
            for i in range(n):
                idx[0] = i  # time before feed
                stream.feed(silent_block())
        finally:
            _clap_mod.time.monotonic = original_monotonic

        assert det._calibrated.is_set()
        assert det._threshold > 0
        cb.assert_not_called()

    # -- double-clap detection --------------------------------------------

    def test_double_clap_detected(self):
        """Two loud blocks ~300 ms apart trigger the callback."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        self._feed_with_time(stream, [
            (loud_block(), 1),     # first clap
            (silent_block(), 15),  # 300 ms gap
            (loud_block(), 1),     # second clap
        ])
        cb.assert_called_once()

    def test_double_clap_at_200ms_boundary(self):
        """Two claps exactly at the 200 ms minimum gap should trigger."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        # first clap at t=0, silence 10 blocks (200ms), second clap at t=220ms
        # gap = 11 * 20ms = 220ms (within [200, 600])
        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 10),
            (loud_block(), 1),
        ])
        cb.assert_called_once()

    def test_double_clap_at_600ms_boundary(self):
        """Two claps near the 600 ms maximum gap should trigger."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        # first clap at block 0 (t=0), 29 silent blocks, second clap at block 30
        # gap = 30 * 20ms = 600ms exactly
        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 29),
            (loud_block(), 1),
        ])
        cb.assert_called_once()

    def test_single_clap_no_detection(self):
        """A single clap followed by long silence should NOT trigger."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 40),  # well past 700 ms window
        ])
        cb.assert_not_called()

    def test_claps_too_close_no_detection(self):
        """Two claps < 200 ms apart (too fast) should NOT trigger."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        # gap = 6 * 20ms = 120ms < 200ms
        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 5),
            (loud_block(), 1),
        ])
        cb.assert_not_called()

    def test_claps_too_far_no_detection(self):
        """Two claps > 700 ms apart (window expired) should NOT trigger."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        # gap = 36 * 20ms = 720ms > 700ms window
        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 36),
            (loud_block(), 1),
        ])
        cb.assert_not_called()

    # -- debounce ----------------------------------------------------------

    def test_debounce_suppresses_second_pair(self):
        """A second clap pair within 1.5 s of the first is ignored."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 15),
            (loud_block(), 1),      # first detection at block 17
            (silent_block(), 10),   # still within 1.5 s debounce
            (loud_block(), 1),
            (silent_block(), 15),
            (loud_block(), 1),      # suppressed
        ])
        assert cb.call_count == 1

    def test_detection_after_debounce_period(self):
        """After the 1.5 s debounce expires, a new pair is detected."""
        det, cb = self._make_detector()
        stream = self._start_precalibrated(det)

        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 15),
            (loud_block(), 1),       # first detection
            (silent_block(), 80),    # 1.6 s — debounce expires
            (loud_block(), 1),
            (silent_block(), 15),
            (loud_block(), 1),       # second detection
        ])
        assert cb.call_count == 2

    # -- sensitivity / threshold -------------------------------------------

    def test_sensitivity_bounds(self):
        """Sensitivity outside [0, 1] should raise ValueError."""
        with pytest.raises(ValueError):
            ClapDetector(on_clap=lambda: None, sensitivity=-0.1)
        with pytest.raises(ValueError):
            ClapDetector(on_clap=lambda: None, sensitivity=1.1)

    def test_high_sensitivity_lower_threshold(self):
        """Higher sensitivity should produce a lower detection threshold."""
        det_high, _ = self._make_detector(sensitivity=0.9)
        det_low, _ = self._make_detector(sensitivity=0.3)

        # Use blocks with enough energy so thresholds stay above the 1e-5 floor.
        frames = [silent_block(energy=0.001) for _ in range(10)]
        det_high._finish_calibration(frames)
        det_low._finish_calibration(frames)

        assert det_high._threshold < det_low._threshold

    # -- lifecycle ---------------------------------------------------------

    def test_stop_clears_stream(self):
        """After ``stop()`` the stream reference is ``None``."""
        det, _ = self._make_detector()
        self._start_detector(det)
        assert det._stream is not None

        det.stop()
        assert det._stream is None
        assert det._running is False

    def test_double_start_is_harmless(self):
        """Calling ``start()`` twice should not crash."""
        det, _ = self._make_detector()
        self._start_detector(det)
        # Second start — should just log a warning
        self._start_detector(det)

    def test_callback_exception_does_not_crash(self):
        """If the on_clap callback raises, the detector keeps running."""
        exploding_cb = MagicMock(side_effect=RuntimeError("boom"))
        det, _ = self._make_detector(on_clap=exploding_cb)
        stream = self._start_precalibrated(det)

        self._feed_with_time(stream, [
            (loud_block(), 1),
            (silent_block(), 15),
            (loud_block(), 1),
        ])

        exploding_cb.assert_called_once()
        assert det._running is True

    def test_finish_calibration_empty_frames(self):
        """``_finish_calibration([])`` uses a conservative fallback."""
        det, _ = self._make_detector()
        det._finish_calibration([])
        assert det._calibrated.is_set()
        assert det._threshold == 0.005


# ===================================================================
# MicManager tests
# ===================================================================


class TestMicManager:
    """Unit tests for ``MicManager``."""

    @staticmethod
    def _make_manager():
        return MicManager(sample_rate=SAMPLE_RATE)

    # -- acquire / release -------------------------------------------------

    @pytest.mark.asyncio
    async def test_acquire_returns_audio_stream(self):
        mgr = self._make_manager()
        stream = await mgr.acquire("ears")
        assert isinstance(stream, AudioStream)
        assert mgr.current_owner == "ears"
        await mgr.release("ears")

    @pytest.mark.asyncio
    async def test_release_clears_owner(self):
        mgr = self._make_manager()
        await mgr.acquire("ears")
        assert mgr.current_owner == "ears"
        await mgr.release("ears")
        assert mgr.current_owner is None

    @pytest.mark.asyncio
    async def test_state_transitions(self):
        mgr = self._make_manager()
        assert mgr.state == MicState.PASSIVE_LISTEN

        await mgr.acquire("ears")
        assert mgr.state == MicState.ACTIVE_LISTEN

        await mgr.release("ears")
        assert mgr.state == MicState.PASSIVE_LISTEN

    # -- conflict detection ------------------------------------------------

    @pytest.mark.asyncio
    async def test_double_acquire_raises(self):
        mgr = self._make_manager()
        await mgr.acquire("ears")
        with pytest.raises(MicConflictError):
            await mgr.acquire("clap_detector")
        await mgr.release("ears")

    @pytest.mark.asyncio
    async def test_release_wrong_owner_raises(self):
        mgr = self._make_manager()
        await mgr.acquire("ears")
        with pytest.raises(MicConflictError):
            await mgr.release("wrong_owner")
        await mgr.release("ears")

    @pytest.mark.asyncio
    async def test_release_when_not_held_raises(self):
        mgr = self._make_manager()
        with pytest.raises(MicConflictError):
            await mgr.release("nobody")

    # -- reacquire ---------------------------------------------------------

    @pytest.mark.asyncio
    async def test_reacquire_after_release(self):
        mgr = self._make_manager()
        await mgr.acquire("ears")
        await mgr.release("ears")

        stream = await mgr.acquire("clap_detector")
        assert mgr.current_owner == "clap_detector"
        await mgr.release("clap_detector")

    # -- inactivity timeout ------------------------------------------------

    @pytest.mark.asyncio
    async def test_inactivity_timeout_releases_mic(self):
        """Mic auto-releases after the inactivity timeout."""
        original = _mic_mod.ACTIVE_LISTEN_TIMEOUT_S
        _mic_mod.ACTIVE_LISTEN_TIMEOUT_S = 0.1
        try:
            mgr = self._make_manager()
            await mgr.acquire("ears")
            assert mgr.current_owner == "ears"

            # Wait for the timeout to fire
            await asyncio.sleep(0.3)

            assert mgr.current_owner is None
            assert mgr.state == MicState.PASSIVE_LISTEN
        finally:
            _mic_mod.ACTIVE_LISTEN_TIMEOUT_S = original

    @pytest.mark.asyncio
    async def test_release_cancels_timeout(self):
        """Explicit release cancels the pending timeout task."""
        original = _mic_mod.ACTIVE_LISTEN_TIMEOUT_S
        _mic_mod.ACTIVE_LISTEN_TIMEOUT_S = 0.1
        try:
            mgr = self._make_manager()
            await mgr.acquire("ears")
            await mgr.release("ears")

            await asyncio.sleep(0.2)
            # No double-release error should have occurred
            assert mgr.current_owner is None
        finally:
            _mic_mod.ACTIVE_LISTEN_TIMEOUT_S = original


# ===================================================================
# AudioStream tests
# ===================================================================


class TestAudioStream:
    """Unit tests for ``AudioStream``."""

    @staticmethod
    def _make_stream():
        return AudioStream(sample_rate=SAMPLE_RATE, block_size=BLOCK_SIZE)

    @pytest.mark.asyncio
    async def test_async_iteration(self):
        stream = self._make_stream()
        stream.open()

        chunk = np.zeros((BLOCK_SIZE, 1), dtype=np.float32)
        await stream._queue.put(chunk)
        await stream._queue.put(None)  # end sentinel

        chunks = []
        async for c in stream:
            chunks.append(c)

        assert len(chunks) == 1
        assert chunks[0].shape == (BLOCK_SIZE, 1)
        stream.close()

    @pytest.mark.asyncio
    async def test_close_unblocks_iteration(self):
        stream = self._make_stream()
        stream.open()

        async def reader():
            result = []
            async for c in stream:
                result.append(c)
            return result

        task = asyncio.create_task(reader())
        await asyncio.sleep(0.05)

        stream.close()
        chunks = await asyncio.wait_for(task, timeout=1.0)
        assert chunks == []

    def test_is_open_property(self):
        stream = self._make_stream()
        assert not stream.is_open

        stream.open()
        assert stream.is_open

        stream.close()
        assert not stream.is_open

    def test_sample_rate_property(self):
        stream = self._make_stream()
        assert stream.sample_rate == SAMPLE_RATE
