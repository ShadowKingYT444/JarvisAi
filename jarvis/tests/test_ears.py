"""Tests for the Ears (Speech-to-Text) pipeline.

All tests mock hardware dependencies (sounddevice, faster-whisper, webrtcvad)
so they run without audio hardware or ML models.
"""

from __future__ import annotations

import asyncio
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from jarvis.ears.audio_processing import (
    audio_to_wav_bytes,
    compute_rms,
    float_to_int16_bytes,
    is_speech,
    noise_gate,
    normalize,
    resample,
)
from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import TranscriptResult


# ── audio_processing tests ───────────────────────────────────────────


class TestNoiseGate:
    def test_zeros_below_threshold(self):
        audio = np.array([0.01, 0.5, -0.02, 0.8, -0.005], dtype=np.float32)
        result = noise_gate(audio, threshold=0.05)
        assert result[0] == 0.0
        assert result[1] == 0.5
        assert result[2] == 0.0
        assert result[3] == 0.8
        assert result[4] == 0.0

    def test_does_not_modify_original(self):
        audio = np.array([0.01, 0.5], dtype=np.float32)
        noise_gate(audio, threshold=0.05)
        assert audio[0] == pytest.approx(0.01)

    def test_zero_threshold_keeps_all(self):
        audio = np.array([0.01, 0.5, -0.02], dtype=np.float32)
        result = noise_gate(audio, threshold=0.0)
        np.testing.assert_array_equal(result, audio)


class TestNormalize:
    def test_scales_to_unit_range(self):
        audio = np.array([0.25, -0.5, 0.1], dtype=np.float32)
        result = normalize(audio)
        assert np.max(np.abs(result)) == pytest.approx(1.0)
        assert result[1] == pytest.approx(-1.0)

    def test_silent_audio_unchanged(self):
        audio = np.zeros(100, dtype=np.float32)
        result = normalize(audio)
        np.testing.assert_array_equal(result, audio)

    def test_already_normalized(self):
        audio = np.array([1.0, -1.0, 0.5], dtype=np.float32)
        result = normalize(audio)
        np.testing.assert_array_almost_equal(result, audio)


class TestResample:
    def test_same_rate_returns_input(self):
        audio = np.ones(100, dtype=np.float32)
        result = resample(audio, 16000, 16000)
        assert result is audio  # no copy

    def test_downsample(self):
        # 48kHz -> 16kHz should produce ~1/3 the samples
        audio = np.random.randn(4800).astype(np.float32)
        result = resample(audio, 48000, 16000)
        assert len(result) == pytest.approx(1600, abs=5)

    def test_upsample(self):
        audio = np.random.randn(1600).astype(np.float32)
        result = resample(audio, 16000, 48000)
        assert len(result) == pytest.approx(4800, abs=5)


class TestComputeRMS:
    def test_silence_is_zero(self):
        audio = np.zeros(100, dtype=np.float32)
        assert compute_rms(audio) == 0.0

    def test_constant_signal(self):
        audio = np.full(100, 0.5, dtype=np.float32)
        assert compute_rms(audio) == pytest.approx(0.5, abs=1e-6)

    def test_known_sine(self):
        # RMS of a sine wave = amplitude / sqrt(2)
        t = np.linspace(0, 1, 16000, endpoint=False, dtype=np.float32)
        audio = np.sin(2 * np.pi * 440 * t)
        assert compute_rms(audio) == pytest.approx(1.0 / np.sqrt(2), abs=0.01)


class TestIsSpeech:
    def test_delegates_to_vad(self):
        vad = MagicMock()
        vad.is_speech.return_value = True
        assert is_speech(b"\x00" * 960, vad, 16000) is True
        vad.is_speech.assert_called_once()

    def test_returns_false_on_exception(self):
        vad = MagicMock()
        vad.is_speech.side_effect = RuntimeError("bad frame")
        assert is_speech(b"\x00" * 10, vad, 16000) is False


class TestAudioToWavBytes:
    def test_produces_valid_wav(self):
        import io
        import wave

        audio = np.random.randn(16000).astype(np.float32) * 0.5
        wav_bytes = audio_to_wav_bytes(audio, sample_rate=16000)
        assert wav_bytes[:4] == b"RIFF"

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 16000


class TestFloatToInt16Bytes:
    def test_correct_length(self):
        audio = np.zeros(100, dtype=np.float32)
        result = float_to_int16_bytes(audio)
        assert len(result) == 200  # 100 samples * 2 bytes each

    def test_clips_values(self):
        audio = np.array([2.0, -2.0], dtype=np.float32)
        result = float_to_int16_bytes(audio)
        assert len(result) == 4


# ── STTEngine tests ──────────────────────────────────────────────────


class FakeAudioStream:
    """Mock AudioStream that yields pre-defined chunks."""

    def __init__(self, chunks: list[np.ndarray], delay: float = 0.0):
        self._chunks = chunks
        self._delay = delay
        self.is_open = True
        self.sample_rate = 16000

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for chunk in self._chunks:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield chunk.reshape(-1, 1)  # AudioStream yields (N, 1) arrays

    async def close(self):
        self.is_open = False


class FakeMicManager:
    """Mock MicManager for testing."""

    def __init__(self, stream: FakeAudioStream):
        self._stream = stream
        self.acquired = False
        self.released = False

    async def acquire(self, requester: str):
        self.acquired = True
        return self._stream

    async def release(self, requester: str):
        self.released = True


FakeSegment = namedtuple("FakeSegment", ["text", "avg_log_prob"])
FakeInfo = namedtuple("FakeInfo", ["language"])


def make_speech_chunk(n_samples=480, amplitude=0.5):
    """Create a chunk that could register as speech."""
    t = np.arange(n_samples, dtype=np.float32) / 16000
    return (np.sin(2 * np.pi * 300 * t) * amplitude).astype(np.float32)


def make_silent_chunk(n_samples=480):
    """Create a silent chunk."""
    return np.zeros(n_samples, dtype=np.float32)


class TestSTTEngine:
    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def config(self):
        return JarvisConfig(max_record_s=5)

    def _make_engine(self, mic_manager=None, event_bus=None, config=None):
        from jarvis.ears.stt_engine import STTEngine

        engine = STTEngine(
            model_size="base.en",
            mic_manager=mic_manager,
            event_bus=event_bus or EventBus(),
            config=config or JarvisConfig(max_record_s=5),
        )
        return engine

    def _mock_whisper(self):
        """Create a mock WhisperModel."""
        model = MagicMock()
        model.transcribe.return_value = (
            [FakeSegment(text="hello world", avg_log_prob=-0.2)],
            FakeInfo(language="en"),
        )
        return model

    def _mock_vad(self, speech_frames=5):
        """Create a mock VAD that says first N frames are speech, rest silent."""
        vad = MagicMock()
        call_count = 0

        def is_speech_side_effect(frame, sample_rate):
            nonlocal call_count
            call_count += 1
            return call_count <= speech_frames

        vad.is_speech = MagicMock(side_effect=is_speech_side_effect)
        return vad

    @pytest.mark.asyncio
    async def test_listen_returns_transcript(self, event_bus, config):
        # Build chunks: some speech then lots of silence
        chunks = [make_speech_chunk() for _ in range(5)]
        chunks += [make_silent_chunk() for _ in range(100)]  # enough silence to trigger stop
        stream = FakeAudioStream(chunks)
        mic = FakeMicManager(stream)
        engine = self._make_engine(mic_manager=mic, event_bus=event_bus, config=config)

        # Mock the model and VAD
        engine._model = self._mock_whisper()
        engine._vad = self._mock_vad(speech_frames=5)

        result = await engine.listen()

        assert isinstance(result, TranscriptResult)
        assert result.text == "hello world"
        assert result.confidence > 0.0
        assert mic.acquired
        assert mic.released

    @pytest.mark.asyncio
    async def test_listen_cancel(self, event_bus, config):
        chunks = [make_speech_chunk() for _ in range(50)]
        stream = FakeAudioStream(chunks, delay=0.01)
        mic = FakeMicManager(stream)
        engine = self._make_engine(mic_manager=mic, event_bus=event_bus, config=config)
        engine._vad = self._mock_vad(speech_frames=999)

        async def cancel_soon():
            await asyncio.sleep(0.05)
            engine.cancel()

        asyncio.get_event_loop().create_task(cancel_soon())
        result = await engine.listen()

        assert result.text == ""
        assert result.duration_ms == 0
        assert mic.released

    @pytest.mark.asyncio
    async def test_listen_no_mic_manager(self, event_bus, config):
        engine = self._make_engine(mic_manager=None, event_bus=event_bus, config=config)
        engine._vad = MagicMock()

        result = await engine.listen()
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_listen_emits_final_event(self, event_bus, config):
        chunks = [make_speech_chunk() for _ in range(3)]
        chunks += [make_silent_chunk() for _ in range(100)]
        stream = FakeAudioStream(chunks)
        mic = FakeMicManager(stream)
        engine = self._make_engine(mic_manager=mic, event_bus=event_bus, config=config)
        engine._model = self._mock_whisper()
        engine._vad = self._mock_vad(speech_frames=3)

        received = []
        event_bus.on("transcript_final", lambda data: received.append(data))

        await engine.listen()
        assert len(received) == 1
        assert received[0].text == "hello world"

    @pytest.mark.asyncio
    async def test_max_record_time(self, event_bus):
        """Engine should stop after max_record_s even with continuous speech."""
        config = JarvisConfig(max_record_s=1)  # 1 second limit
        # Provide a lot of speech chunks
        chunks = [make_speech_chunk() for _ in range(1000)]
        stream = FakeAudioStream(chunks)
        mic = FakeMicManager(stream)
        engine = self._make_engine(mic_manager=mic, event_bus=event_bus, config=config)
        engine._model = self._mock_whisper()
        # VAD always says speech
        vad = MagicMock()
        vad.is_speech.return_value = True
        engine._vad = vad

        result = await engine.listen()
        # Should have gotten a result (not hung forever)
        assert isinstance(result, TranscriptResult)
        assert mic.released

    def test_lazy_model_loading(self):
        engine = self._make_engine()
        assert engine._model is None
        # We don't call _ensure_model since it would try to import faster_whisper

    def test_cancel_flag(self):
        engine = self._make_engine()
        assert engine._cancelled is False
        engine.cancel()
        assert engine._cancelled is True

    @pytest.mark.asyncio
    async def test_transcribe_error_returns_empty(self, event_bus, config):
        chunks = [make_speech_chunk() for _ in range(3)]
        chunks += [make_silent_chunk() for _ in range(100)]
        stream = FakeAudioStream(chunks)
        mic = FakeMicManager(stream)
        engine = self._make_engine(mic_manager=mic, event_bus=event_bus, config=config)
        engine._vad = self._mock_vad(speech_frames=3)

        # Make transcribe raise an error
        bad_model = MagicMock()
        bad_model.transcribe.side_effect = RuntimeError("model error")
        engine._model = bad_model

        result = await engine.listen()
        assert result.text == ""
        assert result.confidence == 0.0
        assert mic.released
