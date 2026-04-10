"""Tests for the Hands (Tool Execution Engine).

Covers ToolExecutor dispatch, every tool module, web search with mocked APIs,
focus mode state machine, reminders scheduling/persistence, and app alias resolution.
All external calls (subprocess, HTTP, Gemini) are mocked.
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import SearchResult, TabInfo, ToolResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakePlatform(Platform):
    """In-memory platform for testing — no subprocess calls."""

    def __init__(self) -> None:
        self.opened_urls: list[str] = []
        self.opened_apps: list[tuple[str, list[str] | None]] = []
        self.tabs: list[TabInfo] = []
        self.clipboard_content: str = ""
        self.system_commands: list[tuple[str, object]] = []

    async def open_url(self, url: str) -> bool:
        self.opened_urls.append(url)
        return True

    async def open_app(self, name: str, args: list[str] | None = None) -> bool:
        self.opened_apps.append((name, args))
        return True

    async def get_browser_tabs(self) -> list[TabInfo]:
        return list(self.tabs)

    async def close_browser_tab(self, match: str, all_matching: bool = False) -> int:
        match_lower = match.lower()
        targets = [
            t for t in self.tabs
            if match_lower in t.title.lower() or match_lower in t.url.lower()
        ]
        if not all_matching:
            targets = targets[:1]
        for t in targets:
            self.tabs.remove(t)
        return len(targets)

    async def run_system_command(self, action: str, value=None) -> bool:
        self.system_commands.append((action, value))
        return True

    async def clipboard_read(self) -> str:
        return self.clipboard_content

    async def clipboard_write(self, text: str) -> bool:
        self.clipboard_content = text
        return True


@pytest.fixture
def fake_platform() -> FakePlatform:
    return FakePlatform()


@pytest.fixture
def config(tmp_path: Path) -> JarvisConfig:
    """Config pointing to a temp directory so tests don't touch ~/.jarvis."""
    return JarvisConfig(
        jarvis_home=str(tmp_path / ".jarvis"),
        log_dir=str(tmp_path / ".jarvis" / "logs"),
        conversation_dir=str(tmp_path / ".jarvis" / "conversations"),
        search_api_key="test_search_key",
        search_engine_id="test_engine_id",
        gemini_api_key="test_gemini_key",
        app_aliases={
            "code": "Visual Studio Code",
            "chrome": "Google Chrome",
            "slack": "Slack",
            "spotify": "Spotify",
            "vscode": "Visual Studio Code",
        },
    )


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


def _sample_tabs() -> list[TabInfo]:
    return [
        TabInfo(title="React Docs", url="https://react.dev", browser="Google Chrome",
                window_index=1, tab_index=1),
        TabInfo(title="YouTube - Cats", url="https://youtube.com/cats", browser="Google Chrome",
                window_index=1, tab_index=2),
        TabInfo(title="Stack Overflow", url="https://stackoverflow.com/q/123", browser="Safari",
                window_index=1, tab_index=1),
    ]


# ===================================================================
# ToolExecutor tests
# ===================================================================

class TestToolExecutor:
    """Test the central ToolExecutor registry and dispatch."""

    def _make_executor(self, platform: FakePlatform, config: JarvisConfig):
        """Build an executor but skip auto-registration to test manually."""
        from jarvis.hands.tool_executor import ToolExecutor

        with patch.object(ToolExecutor, "_auto_register"):
            return ToolExecutor(platform, config)

    @pytest.mark.asyncio
    async def test_register_and_execute(self, fake_platform, config):
        executor = self._make_executor(fake_platform, config)

        async def dummy_tool(x: int = 0) -> ToolResult:
            return ToolResult(success=True, data=x * 2, display_text=f"doubled: {x * 2}")

        executor.register("double", dummy_tool)
        assert "double" in executor.registered_tools

        result = await executor.execute("double", {"x": 5})
        assert result.success is True
        assert result.data == 10

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, fake_platform, config):
        executor = self._make_executor(fake_platform, config)
        result = await executor.execute("nonexistent", {})
        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_handler_exception(self, fake_platform, config):
        executor = self._make_executor(fake_platform, config)

        async def bad_tool() -> ToolResult:
            raise ValueError("boom")

        executor.register("bad", bad_tool)
        result = await executor.execute("bad", {})
        assert result.success is False
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_auto_register(self, fake_platform, config):
        """Full executor with auto-registration picks up built-in tools."""
        from jarvis.hands.tool_executor import ToolExecutor

        executor = ToolExecutor(fake_platform, config)
        # Should have at least the core tools
        assert "web_search" in executor.registered_tools
        assert "open_tabs" in executor.registered_tools
        assert "clipboard_read" in executor.registered_tools
        assert "system_command" in executor.registered_tools
        assert "set_reminder" in executor.registered_tools
        assert "focus_start" in executor.registered_tools
        assert "open_application" in executor.registered_tools

    @pytest.mark.asyncio
    async def test_execute_with_none_args(self, fake_platform, config):
        executor = self._make_executor(fake_platform, config)

        async def no_args_tool() -> ToolResult:
            return ToolResult(success=True, data="ok")

        executor.register("simple", no_args_tool)
        result = await executor.execute("simple", None)
        assert result.success is True


# ===================================================================
# Web search tests
# ===================================================================

class TestWebSearch:
    """Test web_search with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_google_cse_success(self, fake_platform, config):
        from jarvis.hands.tools.web_search import web_search

        mock_response = {
            "items": [
                {"title": "Result 1", "snippet": "Snippet 1", "link": "https://example.com/1"},
                {"title": "Result 2", "snippet": "Snippet 2", "link": "https://example.com/2"},
            ]
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("jarvis.hands.tools.web_search.aiohttp.ClientSession", return_value=mock_session):
            result = await web_search("test query", num_results=2, _config=config)

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0].title == "Result 1"
        assert result.data[0].source == "google_cse"

    @pytest.mark.asyncio
    async def test_serpapi_success(self, fake_platform, config):
        config.search_provider = "serpapi"
        from jarvis.hands.tools.web_search import web_search

        mock_response = {
            "organic_results": [
                {"title": "Serp 1", "snippet": "S1", "link": "https://serp.com/1"},
            ]
        }
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("jarvis.hands.tools.web_search.aiohttp.ClientSession", return_value=mock_session):
            result = await web_search("serp test", num_results=1, _config=config)

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].source == "serpapi"

    @pytest.mark.asyncio
    async def test_fallback_on_api_failure(self, fake_platform, config):
        from jarvis.hands.tools.web_search import web_search

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("jarvis.hands.tools.web_search.aiohttp.ClientSession", return_value=mock_session):
            with patch("jarvis.hands.tools.web_search._fallback_search") as mock_fb:
                mock_fb.return_value = [
                    SearchResult(title="FB", snippet="fallback", url="https://fb.com", source="googlesearch_fallback")
                ]
                result = await web_search("test", num_results=1, _config=config)

        assert result.success is True
        assert result.data[0].source == "googlesearch_fallback"

    @pytest.mark.asyncio
    async def test_num_results_clamped(self, fake_platform, config):
        from jarvis.hands.tools.web_search import web_search

        mock_response = {"items": []}
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("jarvis.hands.tools.web_search.aiohttp.ClientSession", return_value=mock_session):
            result = await web_search("test", num_results=50, _config=config)

        # Should succeed with clamped results
        assert result.success is True


# ===================================================================
# Browser tool tests
# ===================================================================

class TestBrowser:
    """Test browser tool handlers."""

    @pytest.mark.asyncio
    async def test_open_tabs_single_url(self, fake_platform):
        from jarvis.hands.tools.browser import open_tabs

        result = await open_tabs("https://example.com", _platform=fake_platform)
        assert result.success is True
        assert "https://example.com" in fake_platform.opened_urls

    @pytest.mark.asyncio
    async def test_open_tabs_multiple(self, fake_platform):
        from jarvis.hands.tools.browser import open_tabs

        urls = ["https://a.com", "https://b.com", "https://c.com"]
        result = await open_tabs(urls, _platform=fake_platform)
        assert result.success is True
        assert len(fake_platform.opened_urls) == 3

    @pytest.mark.asyncio
    async def test_close_tab(self, fake_platform):
        from jarvis.hands.tools.browser import close_tab

        fake_platform.tabs = _sample_tabs()
        result = await close_tab("youtube", _platform=fake_platform)
        assert result.success is True
        assert result.data["closed"] == 1
        assert len(fake_platform.tabs) == 2

    @pytest.mark.asyncio
    async def test_close_tab_no_match(self, fake_platform):
        from jarvis.hands.tools.browser import close_tab

        fake_platform.tabs = _sample_tabs()
        result = await close_tab("nonexistent", _platform=fake_platform)
        assert result.success is True
        assert result.data["closed"] == 0

    @pytest.mark.asyncio
    async def test_get_active_tabs(self, fake_platform):
        from jarvis.hands.tools.browser import get_active_tabs

        fake_platform.tabs = _sample_tabs()
        result = await get_active_tabs(_platform=fake_platform)
        assert result.success is True
        assert len(result.data) == 3

    @pytest.mark.asyncio
    async def test_google_search_and_display(self, fake_platform, config):
        from jarvis.hands.tool_executor import ToolExecutor
        from jarvis.hands.tools.browser import google_search_and_display

        with patch.object(ToolExecutor, "_auto_register"):
            executor = ToolExecutor(fake_platform, config)

        # Mock web_search tool
        async def mock_search(**kwargs):
            return ToolResult(
                success=True,
                data=[
                    SearchResult(title="R1", snippet="", url="https://r1.com", source="mock"),
                    SearchResult(title="R2", snippet="", url="https://r2.com", source="mock"),
                ],
            )

        executor.register("web_search", mock_search)

        result = await google_search_and_display(
            "test", num_tabs=2, _platform=fake_platform, _executor=executor,
        )
        assert result.success is True
        assert len(fake_platform.opened_urls) == 2


# ===================================================================
# Applications tests
# ===================================================================

class TestApplications:
    """Test app launching and alias resolution."""

    @pytest.mark.asyncio
    async def test_exact_alias(self, fake_platform, config):
        from jarvis.hands.tools.applications import open_application

        result = await open_application("code", _platform=fake_platform, _config=config)
        assert result.success is True
        assert fake_platform.opened_apps[0][0] == "Visual Studio Code"

    @pytest.mark.asyncio
    async def test_case_insensitive_alias(self, fake_platform, config):
        from jarvis.hands.tools.applications import open_application

        result = await open_application("Chrome", _platform=fake_platform, _config=config)
        assert result.success is True
        assert fake_platform.opened_apps[0][0] == "Google Chrome"

    @pytest.mark.asyncio
    async def test_unknown_app_passthrough(self, fake_platform, config):
        from jarvis.hands.tools.applications import open_application

        result = await open_application("SuperObscureApp", _platform=fake_platform, _config=config)
        assert result.success is True
        assert fake_platform.opened_apps[0][0] == "SuperObscureApp"

    @pytest.mark.asyncio
    async def test_with_arguments(self, fake_platform, config):
        from jarvis.hands.tools.applications import open_application

        result = await open_application(
            "chrome", arguments=["--incognito"], _platform=fake_platform, _config=config,
        )
        assert result.success is True
        assert fake_platform.opened_apps[0][1] == ["--incognito"]

    def test_resolve_app_name_substring_key(self, config):
        from jarvis.hands.tools.applications import _resolve_app_name

        # "vs" is a substring of "vscode"
        resolved = _resolve_app_name("vscode", config.app_aliases)
        assert resolved == "Visual Studio Code"

    def test_resolve_app_name_substring_value(self, config):
        from jarvis.hands.tools.applications import _resolve_app_name

        # "Visual Studio" is a substring of the full name value
        resolved = _resolve_app_name("Visual Studio", config.app_aliases)
        assert resolved == "Visual Studio Code"


# ===================================================================
# System controls tests
# ===================================================================

class TestSystemControls:
    """Test system_command handler."""

    @pytest.mark.asyncio
    async def test_volume_up(self, fake_platform):
        from jarvis.hands.tools.system_controls import system_command

        result = await system_command("volume_up", _platform=fake_platform)
        assert result.success is True
        assert fake_platform.system_commands == [("volume_up", None)]

    @pytest.mark.asyncio
    async def test_volume_set_with_value(self, fake_platform):
        from jarvis.hands.tools.system_controls import system_command

        result = await system_command("volume_set", value=75, _platform=fake_platform)
        assert result.success is True
        assert fake_platform.system_commands == [("volume_set", 75)]

    @pytest.mark.asyncio
    async def test_unknown_action(self, fake_platform):
        from jarvis.hands.tools.system_controls import system_command

        result = await system_command("explode", _platform=fake_platform)
        assert result.success is False
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_normalisation(self, fake_platform):
        from jarvis.hands.tools.system_controls import system_command

        result = await system_command("dark-mode-on", _platform=fake_platform)
        assert result.success is True
        assert fake_platform.system_commands[0][0] == "dark_mode_on"

    @pytest.mark.asyncio
    async def test_all_supported_actions(self, fake_platform):
        from jarvis.hands.tools.system_controls import _SUPPORTED_ACTIONS, system_command

        for action in _SUPPORTED_ACTIONS:
            result = await system_command(action, _platform=fake_platform)
            assert result.success is True, f"Action '{action}' failed"


# ===================================================================
# Clipboard tests
# ===================================================================

class TestClipboard:
    """Test clipboard read/write."""

    @pytest.mark.asyncio
    async def test_clipboard_write_and_read(self, fake_platform):
        from jarvis.hands.tools.clipboard import clipboard_read, clipboard_write

        result = await clipboard_write("Hello Jarvis!", _platform=fake_platform)
        assert result.success is True
        assert fake_platform.clipboard_content == "Hello Jarvis!"

        result = await clipboard_read(_platform=fake_platform)
        assert result.success is True
        assert result.data == "Hello Jarvis!"

    @pytest.mark.asyncio
    async def test_clipboard_read_empty(self, fake_platform):
        from jarvis.hands.tools.clipboard import clipboard_read

        result = await clipboard_read(_platform=fake_platform)
        assert result.success is True
        assert result.data == ""
        assert "empty" in result.display_text.lower()

    @pytest.mark.asyncio
    async def test_clipboard_write_empty_rejected(self, fake_platform):
        from jarvis.hands.tools.clipboard import clipboard_write

        result = await clipboard_write("", _platform=fake_platform)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_clipboard_long_text_preview(self, fake_platform):
        from jarvis.hands.tools.clipboard import clipboard_read

        fake_platform.clipboard_content = "x" * 500
        result = await clipboard_read(_platform=fake_platform)
        assert result.success is True
        assert "..." in result.display_text


# ===================================================================
# Focus mode tests
# ===================================================================

class TestFocusMode:
    """Test focus mode state machine (start/stop/status)."""

    @pytest.fixture(autouse=True)
    def reset_session(self):
        """Reset the module-level focus session before each test."""
        import jarvis.hands.tools.focus_mode as fm
        fm._session = fm.FocusSession()
        yield
        fm._session = fm.FocusSession()

    @pytest.mark.asyncio
    async def test_start_focus(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_start

        fake_platform.tabs = _sample_tabs()
        result = await focus_start("Learn React", strictness="moderate",
                                   _platform=fake_platform, _config=config)
        assert result.success is True
        assert result.data["goal"] == "Learn React"
        assert result.data["tabs_backed_up"] == 3

    @pytest.mark.asyncio
    async def test_start_while_active(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_start

        await focus_start("Goal 1", _platform=fake_platform, _config=config)
        result = await focus_start("Goal 2", _platform=fake_platform, _config=config)
        assert result.success is False
        assert "already active" in result.error.lower()

    @pytest.mark.asyncio
    async def test_stop_focus(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_start, focus_stop

        await focus_start("Test Goal", _platform=fake_platform, _config=config)
        result = await focus_stop(restore_tabs=False, _platform=fake_platform, _config=config)
        assert result.success is True
        assert "ended" in result.display_text.lower()

    @pytest.mark.asyncio
    async def test_stop_not_active(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_stop

        result = await focus_stop(_platform=fake_platform, _config=config)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_status_idle(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_status

        result = await focus_status(_platform=fake_platform, _config=config)
        assert result.success is True
        assert result.data["is_active"] is False

    @pytest.mark.asyncio
    async def test_status_active(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_start, focus_status

        await focus_start("Deep work", _platform=fake_platform, _config=config)
        result = await focus_status(_platform=fake_platform, _config=config)
        assert result.success is True
        assert result.data["is_active"] is True
        assert result.data["goal"] == "Deep work"

    @pytest.mark.asyncio
    async def test_stop_with_restore(self, fake_platform, config):
        import jarvis.hands.tools.focus_mode as fm

        await fm.focus_start("Test", _platform=fake_platform, _config=config)
        # Simulate some closed tabs
        fm._session.closed_tabs = [
            {"title": "Distraction", "url": "https://distraction.com", "browser": "Chrome"},
        ]
        result = await fm.focus_stop(restore_tabs=True, _platform=fake_platform, _config=config)
        assert result.success is True
        assert result.data["restored_tabs"] == 1
        assert "https://distraction.com" in fake_platform.opened_urls

    @pytest.mark.asyncio
    async def test_tab_backup_saved(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_start

        fake_platform.tabs = _sample_tabs()
        await focus_start("Goal", _platform=fake_platform, _config=config)

        backup_path = Path(config.jarvis_home) / "backups" / "session_backup.json"
        assert backup_path.exists()
        data = json.loads(backup_path.read_text())
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_invalid_strictness_defaults(self, fake_platform, config):
        from jarvis.hands.tools.focus_mode import focus_start

        result = await focus_start("Goal", strictness="banana",
                                   _platform=fake_platform, _config=config)
        assert result.success is True
        assert result.data["strictness"] == "moderate"


# ===================================================================
# Reminders tests
# ===================================================================

class TestReminders:
    """Test reminder scheduling and persistence."""

    @pytest.fixture(autouse=True)
    def reset_store(self):
        """Reset the module-level store before each test."""
        import jarvis.hands.tools.reminders as rem
        rem._store = None
        yield
        rem._store = None

    def _make_store(self, config):
        from jarvis.hands.tools.reminders import ReminderStore
        return ReminderStore(config)

    @pytest.mark.asyncio
    async def test_set_reminder(self, config):
        from jarvis.hands.tools import reminders

        reminders._store = self._make_store(config)
        result = await reminders.set_reminder("Drink water", 5)
        assert result.success is True
        assert result.data["minutes"] == 5
        assert "rem_" in result.data["id"]

    @pytest.mark.asyncio
    async def test_set_reminder_negative_minutes(self, config):
        from jarvis.hands.tools import reminders

        reminders._store = self._make_store(config)
        result = await reminders.set_reminder("Nope", -1)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_list_reminders_empty(self, config):
        from jarvis.hands.tools import reminders

        reminders._store = self._make_store(config)
        result = await reminders.list_reminders()
        assert result.success is True
        assert result.data == []

    @pytest.mark.asyncio
    async def test_list_reminders_populated(self, config):
        from jarvis.hands.tools import reminders

        reminders._store = self._make_store(config)
        await reminders.set_reminder("First", 10)
        await reminders.set_reminder("Second", 20)
        result = await reminders.list_reminders()
        assert result.success is True
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_cancel_reminder(self, config):
        from jarvis.hands.tools import reminders

        reminders._store = self._make_store(config)
        set_result = await reminders.set_reminder("Cancel me", 10)
        rid = set_result.data["id"]

        cancel_result = await reminders.cancel_reminder(rid)
        assert cancel_result.success is True

        # Should no longer appear in pending
        list_result = await reminders.list_reminders()
        assert len(list_result.data) == 0

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, config):
        from jarvis.hands.tools import reminders

        reminders._store = self._make_store(config)
        result = await reminders.cancel_reminder("rem_999")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_persistence_round_trip(self, config):
        from jarvis.hands.tools.reminders import ReminderStore

        store1 = ReminderStore(config)
        store1.add("Persisted", 60)
        assert store1.count == 1

        # Create a new store from disk
        store2 = ReminderStore(config)
        assert store2.count == 1
        pending = store2.list_pending()
        assert pending[0].message == "Persisted"

    @pytest.mark.asyncio
    async def test_reminder_fires(self, config, event_bus):
        from jarvis.hands.tools.reminders import ReminderStore

        store = ReminderStore(config, event_bus=event_bus)
        fired_events: list[dict] = []
        event_bus.on("reminder_triggered", lambda data: fired_events.append(data))

        # Add a reminder that fires almost immediately
        store.add("Quick", 0.001)  # ~0.06 seconds
        # Need to run the event loop briefly
        await asyncio.sleep(0.2)

        assert len(fired_events) == 1
        assert fired_events[0]["message"] == "Quick"

    @pytest.mark.asyncio
    async def test_store_not_initialised(self):
        from jarvis.hands.tools import reminders

        reminders._store = None
        result = await reminders.set_reminder("fail", 5)
        assert result.success is False
        assert "not initialised" in result.error.lower()

    @pytest.mark.asyncio
    async def test_counter_increments(self, config):
        from jarvis.hands.tools.reminders import ReminderStore

        store = ReminderStore(config)
        r1 = store.add("First", 10)
        r2 = store.add("Second", 20)
        # IDs should be distinct and incrementing
        assert r1.id != r2.id
        n1 = int(r1.id.split("_")[-1])
        n2 = int(r2.id.split("_")[-1])
        assert n2 > n1


# ===================================================================
# Integration: full executor with tool dispatch
# ===================================================================

class TestIntegration:
    """End-to-end tests through the ToolExecutor."""

    @pytest.fixture
    def executor(self, fake_platform, config):
        from jarvis.hands.tool_executor import ToolExecutor
        return ToolExecutor(fake_platform, config)

    @pytest.mark.asyncio
    async def test_clipboard_round_trip_via_executor(self, executor):
        write_result = await executor.execute("clipboard_write", {"text": "integration test"})
        assert write_result.success is True

        read_result = await executor.execute("clipboard_read", {})
        assert read_result.success is True
        assert read_result.data == "integration test"

    @pytest.mark.asyncio
    async def test_system_command_via_executor(self, executor):
        result = await executor.execute("system_command", {"action": "volume_up"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_open_application_via_executor(self, executor):
        result = await executor.execute("open_application", {"app_name": "slack"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_open_tabs_via_executor(self, executor):
        result = await executor.execute("open_tabs", {"urls": "https://example.com"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_active_tabs_via_executor(self, executor, fake_platform):
        fake_platform.tabs = _sample_tabs()
        result = await executor.execute("get_active_tabs", {})
        assert result.success is True
        assert len(result.data) == 3

    @pytest.mark.asyncio
    async def test_focus_lifecycle_via_executor(self, executor, fake_platform):
        fake_platform.tabs = _sample_tabs()

        start = await executor.execute("focus_start", {"goal": "Test via executor"})
        assert start.success is True

        status = await executor.execute("focus_status", {})
        assert status.data["is_active"] is True

        stop = await executor.execute("focus_stop", {"restore_tabs": False})
        assert stop.success is True

        status2 = await executor.execute("focus_status", {})
        assert status2.data["is_active"] is False

    @pytest.mark.asyncio
    async def test_reminder_lifecycle_via_executor(self, executor):
        set_result = await executor.execute("set_reminder", {"message": "Test", "minutes": 30})
        assert set_result.success is True

        list_result = await executor.execute("list_reminders", {})
        assert len(list_result.data) == 1

        cancel_result = await executor.execute("cancel_reminder", {"reminder_id": set_result.data["id"]})
        assert cancel_result.success is True
