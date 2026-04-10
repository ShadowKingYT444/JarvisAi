"""Audio preprocessing utilities for the Ears pipeline.

Provides noise gating, normalization, resampling, RMS computation,
speech detection via webrtcvad, and WAV byte conversion.
"""

from __future__ import annotations

import io
import struct
import wave

import numpy as np


def noise_gate(audio: np.ndarray, threshold: float) -> np.ndarray:
    """Zero out samples whose absolute amplitude is below *threshold*.

    Parameters
    ----------
    audio:
        1-D float array of audio samples (expected range roughly [-1, 1]).
    threshold:
        Amplitude gate threshold.  Samples with ``|sample| < threshold``
        are set to 0.

    Returns
    -------
    np.ndarray
        A copy of *audio* with sub-threshold samples zeroed.
    """
    gated = audio.copy()
    gated[np.abs(gated) < threshold] = 0.0
    return gated


def normalize(audio: np.ndarray) -> np.ndarray:
    """Normalize audio amplitude to the [-1, 1] range.

    If the signal is silent (all zeros), the array is returned unchanged.

    Parameters
    ----------
    audio:
        1-D float array of audio samples.

    Returns
    -------
    np.ndarray
        Amplitude-normalized copy of *audio*.
    """
    peak = np.max(np.abs(audio))
    if peak == 0:
        return audio.copy()
    return audio / peak


def resample(audio: np.ndarray, orig_rate: int, target_rate: int = 16000) -> np.ndarray:
    """Resample *audio* from *orig_rate* to *target_rate* Hz.

    Uses ``scipy.signal.resample_poly`` for high-quality polyphase
    resampling.  If *orig_rate* already equals *target_rate* the input is
    returned as-is (no copy).

    Parameters
    ----------
    audio:
        1-D float array of audio samples at *orig_rate*.
    orig_rate:
        Original sample rate in Hz.
    target_rate:
        Desired sample rate in Hz (default 16 000).

    Returns
    -------
    np.ndarray
        Resampled audio at *target_rate*.
    """
    if orig_rate == target_rate:
        return audio

    from math import gcd

    from scipy.signal import resample_poly

    divisor = gcd(orig_rate, target_rate)
    up = target_rate // divisor
    down = orig_rate // divisor
    return resample_poly(audio, up, down).astype(audio.dtype)


def compute_rms(audio: np.ndarray) -> float:
    """Compute the root-mean-square energy of *audio*.

    Parameters
    ----------
    audio:
        1-D numeric array of audio samples.

    Returns
    -------
    float
        RMS energy level.
    """
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def is_speech(frame: bytes, vad: object, sample_rate: int = 16000) -> bool:
    """Check whether *frame* contains speech using a ``webrtcvad.Vad`` instance.

    Parameters
    ----------
    frame:
        Raw 16-bit little-endian PCM audio frame.  Must be 10, 20, or
        30 ms long (i.e. 320, 640, or 960 bytes at 16 kHz).
    vad:
        A ``webrtcvad.Vad`` instance (any aggressiveness mode).
    sample_rate:
        Sample rate in Hz.  ``webrtcvad`` supports 8000, 16000, 32000,
        and 48000.

    Returns
    -------
    bool
        ``True`` if the VAD considers the frame to contain speech.
    """
    try:
        return vad.is_speech(frame, sample_rate)  # type: ignore[union-attr]
    except Exception:
        # If the frame is malformed or the wrong length, assume no speech.
        return False


def audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Convert a float32 numpy audio array to in-memory WAV bytes.

    The resulting WAV is mono, 16-bit PCM at *sample_rate*.

    Parameters
    ----------
    audio:
        1-D float array of audio samples in [-1, 1].
    sample_rate:
        Sample rate in Hz.

    Returns
    -------
    bytes
        Complete WAV file contents.
    """
    # Clip and convert to int16
    clipped = np.clip(audio, -1.0, 1.0)
    int16_data = (clipped * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(int16_data.tobytes())

    return buf.getvalue()


def float_to_int16_bytes(audio: np.ndarray) -> bytes:
    """Convert float32 audio samples to raw 16-bit little-endian PCM bytes.

    Parameters
    ----------
    audio:
        1-D float array of audio samples in [-1, 1].

    Returns
    -------
    bytes
        Raw PCM bytes (no WAV header).
    """
    clipped = np.clip(audio, -1.0, 1.0)
    int16_data = (clipped * 32767).astype(np.int16)
    return int16_data.tobytes()
