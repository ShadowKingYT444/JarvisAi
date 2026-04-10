"""Speech-to-text engine for the Ears pipeline.

Acquires the microphone from :class:`MicManager`, records audio until
silence or a maximum duration, then transcribes via ``faster-whisper``.
Supports both one-shot transcription (:meth:`listen`) and streaming
partial transcripts (:meth:`listen_stream`).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

import numpy as np

from jarvis.ears.audio_processing import (
    audio_to_wav_bytes,
    compute_rms,
    float_to_int16_bytes,
    is_speech,
    noise_gate,
    normalize,
)
from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import TranscriptResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_SAMPLE_RATE = 16_000
_VAD_FRAME_MS = 30  # webrtcvad frame length in ms
_VAD_FRAME_SAMPLES = _DEFAULT_SAMPLE_RATE * _VAD_FRAME_MS // 1000  # 480
_SILENCE_THRESHOLD_S = 1.5  # seconds of silence to end recording
_PARTIAL_INTERVAL_S = 0.5  # how often to emit partial transcripts
_VAD_MODE = 3  # aggressive


class STTEngine:
    """Record from the microphone and transcribe speech to text.

    Parameters
    ----------
    model_size:
        Whisper model name passed to ``faster-whisper``
        (e.g. ``"base.en"``, ``"small.en"``).
    mic_manager:
        Shared :class:`MicManager` instance for mic acquisition.
    event_bus:
        Shared :class:`EventBus` for emitting transcript events.
    config:
        Jarvis configuration (provides ``max_record_s``, etc.).
    """

    def __init__(
        self,
        model_size: str = "base.en",
        mic_manager: "MicManager | None" = None,  # noqa: F821
        event_bus: EventBus | None = None,
        config: JarvisConfig | None = None,
    ) -> None:
        self._model_size = model_size
        self._mic_manager = mic_manager
        self._event_bus = event_bus or EventBus()
        self._config = config or JarvisConfig()

        self._model: object | None = None  # lazy-loaded WhisperModel
        self._vad: object | None = None  # lazy-loaded webrtcvad.Vad

        self._cancelled = False
        self._recording = False
        self._max_record_s: float = float(self._config.max_record_s)
        self._silence_threshold_s: float = _SILENCE_THRESHOLD_S

    # ------------------------------------------------------------------
    # Lazy model / VAD initialisation
    # ------------------------------------------------------------------

    def _ensure_model(self) -> object:
        """Lazy-load the ``faster-whisper`` model on first use."""
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Loaded faster-whisper model %r", self._model_size)
        return self._model

    def _ensure_vad(self) -> object:
        """Lazy-load a ``webrtcvad.Vad`` instance on first use."""
        if self._vad is None:
            import webrtcvad

            self._vad = webrtcvad.Vad(_VAD_MODE)
            logger.info("Initialized webrtcvad (mode=%d)", _VAD_MODE)
        return self._vad

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def listen(self) -> TranscriptResult:
        """Record from the microphone until silence, then transcribe.

        Returns a :class:`TranscriptResult` with the full transcription.
        On cancel or empty audio an empty-text result is returned.
        """
        audio_buffer = await self._record()
        if audio_buffer is None or len(audio_buffer) == 0:
            return TranscriptResult(text="", confidence=0.0, duration_ms=0)

        duration_ms = int(len(audio_buffer) / _DEFAULT_SAMPLE_RATE * 1000)
        text, confidence = self._transcribe(audio_buffer)

        result = TranscriptResult(
            text=text.strip(),
            confidence=confidence,
            duration_ms=duration_ms,
        )

        self._event_bus.emit("transcript_final", result)
        return result

    async def listen_stream(self) -> AsyncIterator[str]:
        """Yield partial transcript strings as audio is recorded.

        Periodically transcribes the accumulated audio (every ~500 ms)
        and yields the latest partial text.  The final yield is the
        complete transcription.
        """
        self._cancelled = False
        self._recording = True
        vad = self._ensure_vad()

        stream = None
        if self._mic_manager is not None:
            stream = await self._mic_manager.acquire("ears")

        try:
            audio_chunks: list[np.ndarray] = []
            speech_started = False
            consecutive_silent_frames = 0
            frames_per_silence_unit = int(
                _DEFAULT_SAMPLE_RATE * _SILENCE_THRESHOLD_S / _VAD_FRAME_SAMPLES
            )
            start_time = time.monotonic()
            last_partial_time = start_time

            async for chunk in self._iter_stream(stream):
                if self._cancelled:
                    break

                elapsed = time.monotonic() - start_time
                if elapsed >= self._max_record_s:
                    logger.info("Max recording time (%.1f s) reached", self._max_record_s)
                    break

                audio_chunks.append(chunk)

                # VAD on the latest chunk
                pcm_bytes = float_to_int16_bytes(chunk)
                offset = 0
                frame_byte_size = _VAD_FRAME_SAMPLES * 2  # 16-bit
                chunk_has_speech = False

                while offset + frame_byte_size <= len(pcm_bytes):
                    frame = pcm_bytes[offset : offset + frame_byte_size]
                    if is_speech(frame, vad, _DEFAULT_SAMPLE_RATE):
                        chunk_has_speech = True
                        consecutive_silent_frames = 0
                    else:
                        consecutive_silent_frames += 1
                    offset += frame_byte_size

                if chunk_has_speech:
                    speech_started = True

                # Check for end-of-utterance silence
                if speech_started and consecutive_silent_frames >= frames_per_silence_unit:
                    logger.info("Silence detected — stopping recording")
                    break

                # Periodic partial transcription
                now = time.monotonic()
                if speech_started and (now - last_partial_time) >= _PARTIAL_INTERVAL_S:
                    last_partial_time = now
                    combined = np.concatenate(audio_chunks)
                    partial_text, _ = self._transcribe(combined)
                    partial_text = partial_text.strip()
                    if partial_text:
                        self._event_bus.emit("transcript_partial", partial_text)
                        yield partial_text

            # Final transcription
            if audio_chunks and not self._cancelled:
                combined = np.concatenate(audio_chunks)
                final_text, confidence = self._transcribe(combined)
                final_text = final_text.strip()
                duration_ms = int(len(combined) / _DEFAULT_SAMPLE_RATE * 1000)
                result = TranscriptResult(
                    text=final_text,
                    confidence=confidence,
                    duration_ms=duration_ms,
                )
                self._event_bus.emit("transcript_final", result)
                yield final_text

        finally:
            self._recording = False
            if self._mic_manager is not None:
                await self._mic_manager.release("ears")

    def cancel(self) -> None:
        """Cancel an in-progress recording immediately."""
        self._cancelled = True
        logger.info("STTEngine recording cancelled")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _record(self) -> np.ndarray | None:
        """Record audio from the mic until silence / max time / cancel.

        Returns the collected float32 audio buffer, or ``None`` on
        cancel / empty input.
        """
        self._cancelled = False
        self._recording = True
        vad = self._ensure_vad()

        stream = None
        if self._mic_manager is not None:
            stream = await self._mic_manager.acquire("ears")

        try:
            audio_chunks: list[np.ndarray] = []
            speech_started = False
            consecutive_silent_frames = 0
            frames_per_silence_unit = int(
                _DEFAULT_SAMPLE_RATE * _SILENCE_THRESHOLD_S / _VAD_FRAME_SAMPLES
            )
            start_time = time.monotonic()
            last_partial_time = start_time

            async for chunk in self._iter_stream(stream):
                if self._cancelled:
                    logger.info("Recording cancelled")
                    return None

                elapsed = time.monotonic() - start_time
                if elapsed >= self._max_record_s:
                    logger.info("Max recording time (%.1f s) reached", self._max_record_s)
                    break

                audio_chunks.append(chunk)

                # --- VAD: scan the chunk in 30 ms frames ---
                pcm_bytes = float_to_int16_bytes(chunk)
                offset = 0
                frame_byte_size = _VAD_FRAME_SAMPLES * 2  # 16-bit = 2 bytes/sample
                chunk_has_speech = False

                while offset + frame_byte_size <= len(pcm_bytes):
                    frame = pcm_bytes[offset : offset + frame_byte_size]
                    if is_speech(frame, vad, _DEFAULT_SAMPLE_RATE):
                        chunk_has_speech = True
                        consecutive_silent_frames = 0
                    else:
                        consecutive_silent_frames += 1
                    offset += frame_byte_size

                if chunk_has_speech:
                    speech_started = True

                # End-of-utterance silence detection
                if speech_started and consecutive_silent_frames >= frames_per_silence_unit:
                    logger.info("Silence detected after speech — stopping recording")
                    break

                # Emit partial transcripts periodically
                now = time.monotonic()
                if speech_started and (now - last_partial_time) >= _PARTIAL_INTERVAL_S:
                    last_partial_time = now
                    combined = np.concatenate(audio_chunks)
                    partial_text, _ = self._transcribe(combined)
                    partial_text = partial_text.strip()
                    if partial_text:
                        self._event_bus.emit("transcript_partial", partial_text)

            if not audio_chunks:
                return None

            return np.concatenate(audio_chunks)

        finally:
            self._recording = False
            if self._mic_manager is not None:
                await self._mic_manager.release("ears")

    async def _iter_stream(self, stream: object | None) -> AsyncIterator[np.ndarray]:
        """Iterate over audio chunks from an :class:`AudioStream`.

        If *stream* is ``None`` (no mic manager), yields nothing.
        The chunks are squeezed to 1-D.
        """
        if stream is None:
            return
        async for chunk in stream:  # type: ignore[union-attr]
            # AudioStream yields (N, 1) float32 arrays — squeeze to 1-D
            yield chunk.squeeze()

    def _transcribe(self, audio: np.ndarray) -> tuple[str, float]:
        """Run ``faster-whisper`` on *audio* and return (text, confidence).

        *audio* should be a 1-D float32 array at 16 kHz.
        """
        model = self._ensure_model()

        # Apply light preprocessing
        processed = noise_gate(audio, threshold=0.005)
        processed = normalize(processed)

        try:
            segments, info = model.transcribe(  # type: ignore[union-attr]
                processed,
                beam_size=5,
                language="en",
                vad_filter=True,
            )
            texts: list[str] = []
            total_log_prob = 0.0
            count = 0
            for segment in segments:
                texts.append(segment.text)
                total_log_prob += segment.avg_log_prob
                count += 1

            text = " ".join(texts)
            # Convert average log-prob to a rough confidence [0, 1]
            avg_log_prob = total_log_prob / count if count > 0 else -1.0
            confidence = min(1.0, max(0.0, 1.0 + avg_log_prob))
            return text, confidence

        except Exception:
            logger.exception("Transcription failed")
            return "", 0.0
