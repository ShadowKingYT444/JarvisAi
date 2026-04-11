"""Multi-backend text-to-speech engine.

Supports macOS ``say`` (default), ElevenLabs (premium), and
``pyttsx3`` (cross-platform fallback). Backend is selected via
:attr:`JarvisConfig.tts_engine`.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import subprocess
from abc import ABC, abstractmethod

from jarvis.shared.config import JarvisConfig

logger = logging.getLogger(__name__)


class TTSBackend(ABC):
    """Abstract TTS backend."""

    @abstractmethod
    async def speak(self, text: str) -> None:
        """Speak *text* aloud. Blocks until speech is finished."""

    async def stop(self) -> None:
        """Interrupt any in-progress speech."""

    def is_available(self) -> bool:
        """Return ``True`` if this backend can function on the current system."""
        return True


# ── macOS say ────────────────────────────────────────────────────────


class MacOSSayBackend(TTSBackend):
    """macOS native ``say`` command."""

    def __init__(self, voice: str = "Daniel", rate: int = 180) -> None:
        self._voice = voice
        self._rate = rate
        self._process: subprocess.Popen | None = None

    async def speak(self, text: str) -> None:
        cleaned = _strip_emoji(text)
        if not cleaned.strip():
            return
        loop = asyncio.get_event_loop()
        self._process = await loop.run_in_executor(
            None, self._speak_sync, cleaned
        )

    def _speak_sync(self, text: str) -> subprocess.Popen | None:
        try:
            proc = subprocess.Popen(
                ["say", "-v", self._voice, "-r", str(self._rate), text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.wait()
            return proc
        except FileNotFoundError:
            logger.error("'say' command not found — not on macOS?")
            return None

    async def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process = None

    def is_available(self) -> bool:
        return platform.system() == "Darwin"


# ── ElevenLabs ───────────────────────────────────────────────────────


class ElevenLabsBackend(TTSBackend):
    """ElevenLabs streaming TTS (premium, optional)."""

    def __init__(self, api_key: str, voice_id: str = "") -> None:
        self._api_key = api_key
        self._voice_id = voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel default

    async def speak(self, text: str) -> None:
        cleaned = _strip_emoji(text)
        if not cleaned.strip():
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak_sync, cleaned)

    def _speak_sync(self, text: str) -> None:
        try:
            from elevenlabs import ElevenLabs as ELClient

            client = ELClient(api_key=self._api_key)
            audio = client.text_to_speech.convert(
                text=text,
                voice_id=self._voice_id,
                model_id="eleven_turbo_v2",
                output_format="mp3_44100_128",
            )
            # Play via a temp file and system player
            self._play_audio(audio)
        except Exception:
            logger.exception("ElevenLabs TTS failed")

    def _play_audio(self, audio_iter) -> None:
        """Write streamed audio to temp file and play it."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            for chunk in audio_iter:
                f.write(chunk)
            tmp_path = f.name

        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["afplay", tmp_path], check=True)
            elif system == "Windows":
                subprocess.run(
                    ["powershell", "-c", f'(New-Object Media.SoundPlayer "{tmp_path}").PlaySync()'],
                    check=True,
                )
            else:
                subprocess.run(["aplay", tmp_path], check=True)
        except Exception:
            logger.exception("Failed to play ElevenLabs audio")

    def is_available(self) -> bool:
        return bool(self._api_key)


# ── pyttsx3 fallback ────────────────────────────────────────────────


class Pyttsx3Backend(TTSBackend):
    """Cross-platform fallback using ``pyttsx3``."""

    def __init__(self, rate: int = 180) -> None:
        self._rate = rate
        self._engine = None

    def _ensure_engine(self):
        if self._engine is None:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)

    async def speak(self, text: str) -> None:
        cleaned = _strip_emoji(text)
        if not cleaned.strip():
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._speak_sync, cleaned)

    def _speak_sync(self, text: str) -> None:
        try:
            self._ensure_engine()
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:
            logger.exception("pyttsx3 TTS failed")

    async def stop(self) -> None:
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass


# ── TTSEngine (unified facade) ──────────────────────────────────────


class TTSEngine:
    """Unified TTS engine that delegates to the configured backend.

    Parameters
    ----------
    config:
        Jarvis configuration (selects backend, voice, rate, API keys).
    """

    def __init__(self, config: JarvisConfig | None = None) -> None:
        self._config = config or JarvisConfig()
        self._backend = self._create_backend()

    def _create_backend(self) -> TTSBackend:
        engine = self._config.tts_engine
        if engine == "elevenlabs" and self._config.elevenlabs_api_key:
            return ElevenLabsBackend(
                api_key=self._config.elevenlabs_api_key,
                voice_id=self._config.elevenlabs_voice_id,
            )
        elif engine == "macos_say" and platform.system() == "Darwin":
            return MacOSSayBackend(
                voice=self._config.tts_voice,
                rate=self._config.tts_rate,
            )
        elif engine == "pyttsx3":
            return Pyttsx3Backend(rate=self._config.tts_rate)
        else:
            # Auto-detect best available backend for this platform
            if platform.system() == "Darwin":
                return MacOSSayBackend(
                    voice=self._config.tts_voice,
                    rate=self._config.tts_rate,
                )
            # Windows / Linux: pyttsx3 is the reliable cross-platform fallback
            return Pyttsx3Backend(rate=self._config.tts_rate)

    async def speak(self, text: str) -> None:
        """Speak *text* using the configured backend."""
        await self._backend.speak(text)

    async def stop(self) -> None:
        """Interrupt current speech."""
        await self._backend.stop()

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__


# ── Helpers ──────────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA00-\U0001FAFF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """Remove emoji characters that TTS engines can't pronounce."""
    return _EMOJI_RE.sub("", text)
