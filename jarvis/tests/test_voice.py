"""Tests for the Voice layer (TTS engine + speech queue)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.voice.speech_queue import SpeechQueue, get_interim_phrase
from jarvis.voice.tts_engine import TTSEngine, _strip_emoji


# ── TTSEngine tests ──────────────────────────────────────────────────


class TestStripEmoji:
    def test_removes_emoji(self):
        assert _strip_emoji("Hello \U0001F600 World") == "Hello  World"

    def test_plain_text_unchanged(self):
        assert _strip_emoji("Hello World") == "Hello World"

    def test_empty_string(self):
        assert _strip_emoji("") == ""


class TestTTSEngine:
    def test_creates_with_default_config(self):
        with patch("jarvis.voice.tts_engine.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            engine = TTSEngine(JarvisConfig(tts_engine="pyttsx3"))
            assert engine.backend_name == "Pyttsx3Backend"

    def test_macos_backend_on_darwin(self):
        with patch("jarvis.voice.tts_engine.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            engine = TTSEngine(JarvisConfig(tts_engine="macos_say"))
            assert engine.backend_name == "MacOSSayBackend"

    def test_elevenlabs_backend_with_key(self):
        with patch("jarvis.voice.tts_engine.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            config = JarvisConfig(
                tts_engine="elevenlabs",
                elevenlabs_api_key="test-key",
            )
            engine = TTSEngine(config)
            assert engine.backend_name == "ElevenLabsBackend"

    def test_fallback_to_pyttsx3(self):
        with patch("jarvis.voice.tts_engine.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            engine = TTSEngine(JarvisConfig(tts_engine="macos_say"))
            # On Linux, macos_say falls through to auto-detect → pyttsx3
            assert engine.backend_name == "Pyttsx3Backend"

    @pytest.mark.asyncio
    async def test_speak_delegates(self):
        engine = TTSEngine.__new__(TTSEngine)
        engine._backend = AsyncMock()
        engine._backend.speak = AsyncMock()
        await engine.speak("hello")
        engine._backend.speak.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_stop_delegates(self):
        engine = TTSEngine.__new__(TTSEngine)
        engine._backend = AsyncMock()
        engine._backend.stop = AsyncMock()
        await engine.stop()
        engine._backend.stop.assert_called_once()


# ── SpeechQueue tests ────────────────────────────────────────────────


class TestSpeechQueue:
    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def mock_tts(self):
        tts = AsyncMock(spec=TTSEngine)
        tts.speak = AsyncMock()
        tts.stop = AsyncMock()
        return tts

    @pytest.mark.asyncio
    async def test_say_queues_and_speaks(self, mock_tts, event_bus):
        queue = SpeechQueue(mock_tts, event_bus)
        await queue.start()

        await queue.say("Hello world")
        await asyncio.sleep(0.2)  # let worker process

        mock_tts.speak.assert_called_with("Hello world")
        await queue.stop()

    @pytest.mark.asyncio
    async def test_say_skips_empty(self, mock_tts, event_bus):
        queue = SpeechQueue(mock_tts, event_bus)
        await queue.start()

        await queue.say("")
        await queue.say("   ")
        await asyncio.sleep(0.1)

        mock_tts.speak.assert_not_called()
        await queue.stop()

    @pytest.mark.asyncio
    async def test_cancel_clears_queue(self, mock_tts, event_bus):
        queue = SpeechQueue(mock_tts, event_bus)
        await queue.start()

        await queue.say("First")
        await queue.say("Second")
        queue.cancel()

        await asyncio.sleep(0.2)
        # After cancel, queue should be drained
        assert queue._queue.empty()
        await queue.stop()

    @pytest.mark.asyncio
    async def test_speech_events_emitted(self, mock_tts, event_bus):
        starts = []
        ends = []
        event_bus.on("speech_start", lambda d: starts.append(d))
        event_bus.on("speech_end", lambda d: ends.append(d))

        queue = SpeechQueue(mock_tts, event_bus)
        await queue.start()

        await queue.say("Test speech")
        await asyncio.sleep(0.3)

        assert len(starts) >= 1
        assert starts[0] == "Test speech"
        assert len(ends) >= 1
        await queue.stop()

    @pytest.mark.asyncio
    async def test_interim_has_higher_priority(self, mock_tts, event_bus):
        spoken = []
        original_speak = mock_tts.speak

        async def track_speak(text):
            spoken.append(text)
            await asyncio.sleep(0.01)

        mock_tts.speak = track_speak

        queue = SpeechQueue(mock_tts, event_bus)
        # Don't start worker yet — queue items first
        await queue.say("Normal message", priority=0)
        await queue.say_interim("Urgent interim")

        await queue.start()
        await asyncio.sleep(0.3)

        # Interim (priority -1) should come before normal (priority 0)
        assert len(spoken) >= 2
        assert spoken[0] == "Urgent interim"
        assert spoken[1] == "Normal message"
        await queue.stop()


# ── Interim phrases tests ────────────────────────────────────────────


class TestInterimPhrases:
    def test_search_phrase(self):
        phrase = get_interim_phrase("search")
        assert isinstance(phrase, str)
        assert len(phrase) > 0

    def test_open_app_with_kwargs(self):
        phrase = get_interim_phrase("open_app", app_name="Spotify")
        assert "Spotify" in phrase

    def test_unknown_category_uses_working(self):
        phrase = get_interim_phrase("nonexistent_category")
        assert isinstance(phrase, str)
        assert len(phrase) > 0

    def test_focus_start_with_goal(self):
        phrase = get_interim_phrase("focus_start", goal="writing essay")
        assert "writing essay" in phrase
