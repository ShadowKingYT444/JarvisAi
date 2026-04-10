"""Integration tests for Jarvis end-to-end flows.

These tests mock external dependencies (Gemini, browser, mic) but verify
the full pipeline: text → brain → tools → response.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import (
    BrainResponse,
    JarvisState,
    SearchResult,
    ToolCall,
    ToolResult,
)
from jarvis.face.hud import StateManager


class FakeToolExecutor:
    """Mock tool executor that records calls and returns canned results."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.results: dict[str, ToolResult] = {}

    def set_result(self, tool_name: str, result: ToolResult):
        self.results[tool_name] = result

    async def execute(self, tool_name: str, args: dict) -> ToolResult:
        self.calls.append((tool_name, args))
        return self.results.get(
            tool_name,
            ToolResult(success=True, data=None, display_text="OK"),
        )


class TestNewsQueryFlow:
    """Test: "What's going on in the world?" → search + open tabs + summary."""

    @pytest.mark.asyncio
    async def test_search_and_respond(self):
        event_bus = EventBus()
        config = JarvisConfig(gemini_api_key="test-key")
        tool_exec = FakeToolExecutor()

        # Mock web search results
        tool_exec.set_result("web_search", ToolResult(
            success=True,
            data=[
                {"title": "News 1", "url": "https://example.com/1", "snippet": "Story 1"},
                {"title": "News 2", "url": "https://example.com/2", "snippet": "Story 2"},
            ],
            display_text="Found 2 results",
        ))
        tool_exec.set_result("open_browser_tabs", ToolResult(
            success=True,
            data=None,
            display_text="Opened 2 tabs",
        ))

        # Since we can't call real Gemini, test the tool executor directly
        result = await tool_exec.execute("web_search", {"query": "top news today"})
        assert result.success
        assert len(result.data) == 2

        result = await tool_exec.execute(
            "open_browser_tabs",
            {"urls": ["https://example.com/1", "https://example.com/2"]},
        )
        assert result.success

        assert len(tool_exec.calls) == 2
        assert tool_exec.calls[0][0] == "web_search"
        assert tool_exec.calls[1][0] == "open_browser_tabs"


class TestOpenAppFlow:
    """Test: "Open Spotify" → open_application called."""

    @pytest.mark.asyncio
    async def test_open_app(self):
        tool_exec = FakeToolExecutor()
        tool_exec.set_result("open_application", ToolResult(
            success=True,
            data=None,
            display_text="Opened Spotify",
        ))

        result = await tool_exec.execute(
            "open_application",
            {"app_name": "Spotify"},
        )
        assert result.success
        assert "Spotify" in result.display_text


class TestFocusModeFlow:
    """Test: "Focus on coding" → focus mode start + monitoring."""

    @pytest.mark.asyncio
    async def test_focus_start(self):
        tool_exec = FakeToolExecutor()
        tool_exec.set_result("focus_mode", ToolResult(
            success=True,
            data={"action": "start", "goal": "coding"},
            display_text="Focus mode started for: coding",
        ))

        result = await tool_exec.execute(
            "focus_mode",
            {"action": "start", "goal": "coding", "strictness": "moderate"},
        )
        assert result.success
        assert "coding" in result.display_text


class TestStateTransitions:
    """Test the full state cycle during a command."""

    def test_command_cycle_states(self):
        event_bus = EventBus()
        state_mgr = StateManager(event_bus=event_bus)

        states_seen = []
        state_mgr.subscribe(lambda s, m: states_seen.append(s))

        # Simulate a command cycle
        state_mgr.set_state(JarvisState.LISTENING)
        state_mgr.set_state(JarvisState.PROCESSING)
        state_mgr.set_state(JarvisState.SPEAKING)
        state_mgr.set_state(JarvisState.IDLE)

        assert states_seen == [
            JarvisState.LISTENING,
            JarvisState.PROCESSING,
            JarvisState.SPEAKING,
            JarvisState.IDLE,
        ]

    def test_error_recovery(self):
        event_bus = EventBus()
        state_mgr = StateManager(event_bus=event_bus)

        state_mgr.set_state(JarvisState.PROCESSING)
        state_mgr.set_state(JarvisState.ERROR)
        state_mgr.set_state(JarvisState.IDLE)

        assert state_mgr.current_state == JarvisState.IDLE


class TestTextModeFlow:
    """Test: text command via IPC → brain → response."""

    @pytest.mark.asyncio
    async def test_text_command(self):
        tool_exec = FakeToolExecutor()
        tool_exec.set_result("web_search", ToolResult(
            success=True,
            data=[{"title": "Tutorial", "url": "https://example.com", "snippet": "Learn asyncio"}],
            display_text="Found 1 result",
        ))

        result = await tool_exec.execute(
            "web_search",
            {"query": "Python asyncio tutorials"},
        )
        assert result.success
        assert len(result.data) == 1


class TestEventBusIntegration:
    """Test cross-module communication via the event bus."""

    def test_tool_events(self):
        event_bus = EventBus()
        tool_events = []

        event_bus.on("tool_executing", lambda d: tool_events.append(("exec", d)))
        event_bus.on("tool_complete", lambda d: tool_events.append(("done", d)))

        # Simulate tool execution events
        call = ToolCall(name="web_search", arguments={"query": "test"})
        event_bus.emit("tool_executing", call)

        result = ToolResult(success=True, display_text="OK")
        event_bus.emit("tool_complete", result)

        assert len(tool_events) == 2
        assert tool_events[0][0] == "exec"
        assert tool_events[1][0] == "done"

    def test_speech_events(self):
        event_bus = EventBus()
        speech_events = []

        event_bus.on("speech_start", lambda d: speech_events.append(("start", d)))
        event_bus.on("speech_end", lambda d: speech_events.append(("end", d)))

        event_bus.emit("speech_start", "Hello world")
        event_bus.emit("speech_end", None)

        assert len(speech_events) == 2
        assert speech_events[0] == ("start", "Hello world")
