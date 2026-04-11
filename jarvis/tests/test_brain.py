"""Tests for the Brain (LLM Orchestrator + Tool Router).

Covers tool declarations, conversation management, and the orchestrator
with a fully mocked Gemini backend so no real API calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import BrainResponse, ToolCall, ToolResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config(tmp_path: Path) -> JarvisConfig:
    """Config with temp directories so tests never touch the real filesystem."""
    return JarvisConfig(
        gemini_api_key="test-key-12345",
        gemini_model="gemini-2.0-flash",
        jarvis_home=str(tmp_path / ".jarvis"),
        log_dir=str(tmp_path / ".jarvis" / "logs"),
        conversation_dir=str(tmp_path / ".jarvis" / "conversations"),
    )


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


# ---------------------------------------------------------------------------
# Helpers for building mock Gemini responses
# ---------------------------------------------------------------------------

def _make_text_response(text: str) -> MagicMock:
    """Build a mock Gemini response that contains only a text part."""
    part = MagicMock()
    part.text = text
    part.function_call = None
    # Ensure function_call attribute check works
    type(part).function_call = PropertyMock(return_value=None)
    # But we actually want .function_call to be falsy and .name to be empty
    fc = MagicMock()
    fc.name = ""
    fc.args = {}
    part.function_call = fc

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _make_function_call_response(
    name: str, args: dict | None = None
) -> MagicMock:
    """Build a mock Gemini response with a single function_call part."""
    fc = MagicMock()
    fc.name = name
    fc.args = args or {}

    part = MagicMock()
    part.function_call = fc
    part.text = ""

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


def _make_multi_function_call_response(
    calls: list[tuple[str, dict]],
) -> MagicMock:
    """Build a mock Gemini response with multiple function_call parts."""
    parts = []
    for name, args in calls:
        fc = MagicMock()
        fc.name = name
        fc.args = args or {}
        part = MagicMock()
        part.function_call = fc
        part.text = ""
        parts.append(part)

    content = MagicMock()
    content.parts = parts

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


# ===================================================================
# Tool Definitions Tests
# ===================================================================

class TestToolDefinitions:
    """Verify that tool declarations are complete and well-formed."""

    def _get_declarations(self):
        """Import and return declarations with mocked google.generativeai."""
        # We need to use the real protos for schema validation, but we can
        # import directly since the module only uses protos/types at import.
        from jarvis.brain.tool_definitions import get_tool_declarations
        return get_tool_declarations()

    def _get_config(self):
        from jarvis.brain.tool_definitions import get_tool_config
        return get_tool_config()

    def test_core_tools_declared(self):
        declarations = self._get_declarations()
        assert len(declarations) >= 11

    def test_tool_names(self):
        declarations = self._get_declarations()
        names = {d.name for d in declarations}
        expected = {
            "web_search",
            "open_browser_tabs",
            "open_application",
            "close_browser_tab",
            "google_search_and_display",
            "system_command",
            "clipboard_read",
            "clipboard_write",
            "focus_mode",
            "set_reminder",
            "get_active_tabs",
        }
        assert expected.issubset(names)

    def test_web_search_has_query_param(self):
        declarations = self._get_declarations()
        ws = [d for d in declarations if d.name == "web_search"][0]
        param_names = set(ws.parameters.properties.keys())
        assert "query" in param_names
        assert "num_results" in param_names
        assert "query" in ws.parameters.required

    def test_system_command_has_action_enum(self):
        declarations = self._get_declarations()
        sc = [d for d in declarations if d.name == "system_command"][0]
        action_schema = sc.parameters.properties["action"]
        assert len(action_schema.enum) == 14
        assert "volume_up" in action_schema.enum
        assert "lock_screen" in action_schema.enum

    def test_focus_mode_params(self):
        declarations = self._get_declarations()
        fm = [d for d in declarations if d.name == "focus_mode"][0]
        action_schema = fm.parameters.properties["action"]
        assert "start" in action_schema.enum
        assert "stop" in action_schema.enum
        assert "status" in action_schema.enum
        assert "goal" in fm.parameters.properties
        assert "strictness" in fm.parameters.properties

    def test_clipboard_read_no_required_params(self):
        declarations = self._get_declarations()
        cr = [d for d in declarations if d.name == "clipboard_read"][0]
        # clipboard_read has an empty properties dict and no required fields
        assert len(cr.parameters.properties) == 0

    def test_get_active_tabs_no_required_params(self):
        declarations = self._get_declarations()
        gat = [d for d in declarations if d.name == "get_active_tabs"][0]
        assert len(gat.parameters.properties) == 0

    def test_open_browser_tabs_urls_is_array(self):
        declarations = self._get_declarations()
        obt = [d for d in declarations if d.name == "open_browser_tabs"][0]
        urls_schema = obt.parameters.properties["urls"]
        # ARRAY type enum value is 4 in protobuf
        from google.generativeai import protos
        assert urls_schema.type == protos.Type.ARRAY

    def test_set_reminder_required_params(self):
        declarations = self._get_declarations()
        sr = [d for d in declarations if d.name == "set_reminder"][0]
        assert "message" in sr.parameters.required
        assert "minutes" in sr.parameters.required

    def test_tool_config_is_auto_mode(self):
        tc = self._get_config()
        from google.generativeai import protos
        assert (
            tc.function_calling_config.mode
            == protos.FunctionCallingConfig.Mode.AUTO
        )

    def test_declarations_are_cached(self):
        """Calling get_tool_declarations() twice returns equal lists."""
        from jarvis.brain.tool_definitions import get_tool_declarations
        first = get_tool_declarations()
        second = get_tool_declarations()
        assert len(first) == len(second)
        for a, b in zip(first, second):
            assert a.name == b.name


# ===================================================================
# Conversation Manager Tests
# ===================================================================

class TestConversationManager:
    """Test in-memory history management and JSONL persistence."""

    def _make_manager(self, config: JarvisConfig, max_turns: int = 20):
        from jarvis.brain.conversation import ConversationManager
        return ConversationManager(config, max_turns=max_turns)

    def test_add_user_message(self, config):
        cm = self._make_manager(config)
        cm.add_user_message("Hello Jarvis")
        history = cm.get_history()
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["text"] == "Hello Jarvis"
        assert history[0]["tools_used"] == []

    def test_add_assistant_message(self, config):
        cm = self._make_manager(config)
        cm.add_assistant_message("Hi there!", tools_used=["web_search"])
        history = cm.get_history()
        assert len(history) == 1
        assert history[0]["role"] == "assistant"
        assert history[0]["text"] == "Hi there!"
        assert history[0]["tools_used"] == ["web_search"]

    def test_assistant_message_default_no_tools(self, config):
        cm = self._make_manager(config)
        cm.add_assistant_message("Just text")
        history = cm.get_history()
        assert history[0]["tools_used"] == []

    def test_history_truncation(self, config):
        cm = self._make_manager(config, max_turns=5)
        for i in range(10):
            cm.add_user_message(f"Message {i}")
        history = cm.get_history()
        assert len(history) == 5
        # Should keep the last 5 messages
        assert history[0]["text"] == "Message 5"
        assert history[-1]["text"] == "Message 9"

    def test_history_truncation_at_20(self, config):
        cm = self._make_manager(config, max_turns=20)
        for i in range(30):
            cm.add_user_message(f"Msg {i}")
        history = cm.get_history()
        assert len(history) == 20
        assert history[0]["text"] == "Msg 10"
        assert history[-1]["text"] == "Msg 29"

    def test_clear_history(self, config):
        cm = self._make_manager(config)
        cm.add_user_message("one")
        cm.add_user_message("two")
        assert len(cm.get_history()) == 2
        cm.clear()
        assert len(cm.get_history()) == 0

    def test_jsonl_persistence(self, config):
        cm = self._make_manager(config)
        cm.add_user_message("persist me")
        cm.add_assistant_message("persisted!", tools_used=["clipboard_read"])

        # Find today's log file
        conv_dir = Path(config.conversation_dir).expanduser()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = conv_dir / f"{today}.jsonl"

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        entry0 = json.loads(lines[0])
        assert entry0["role"] == "user"
        assert entry0["text"] == "persist me"

        entry1 = json.loads(lines[1])
        assert entry1["role"] == "assistant"
        assert entry1["tools_used"] == ["clipboard_read"]

    def test_load_today(self, config):
        conv_dir = Path(config.conversation_dir).expanduser()
        conv_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = conv_dir / f"{today}.jsonl"

        # Write some entries directly
        entries = [
            {
                "timestamp": "2026-04-10T10:00:00+00:00",
                "role": "user",
                "text": "Earlier question",
                "tools_used": [],
            },
            {
                "timestamp": "2026-04-10T10:00:01+00:00",
                "role": "assistant",
                "text": "Earlier answer",
                "tools_used": ["web_search"],
            },
        ]
        with open(log_path, "w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")

        cm = self._make_manager(config)
        cm.load_today()
        history = cm.get_history()
        assert len(history) == 2
        assert history[0]["text"] == "Earlier question"
        assert history[1]["text"] == "Earlier answer"

    def test_load_today_no_file(self, config):
        """load_today with no existing file should not raise."""
        cm = self._make_manager(config)
        cm.load_today()
        assert len(cm.get_history()) == 0

    def test_load_today_with_malformed_lines(self, config):
        """Malformed JSONL lines should be skipped without crashing."""
        conv_dir = Path(config.conversation_dir).expanduser()
        conv_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = conv_dir / f"{today}.jsonl"

        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write('{"role": "user", "text": "good line", "tools_used": [], "timestamp": "2026-04-10T10:00:00+00:00"}\n')
            fh.write("NOT VALID JSON\n")
            fh.write('{"role": "assistant", "text": "also good", "tools_used": [], "timestamp": "2026-04-10T10:00:01+00:00"}\n')

        cm = self._make_manager(config)
        cm.load_today()
        history = cm.get_history()
        assert len(history) == 2

    def test_get_gemini_history(self, config):
        cm = self._make_manager(config)
        cm.add_user_message("Hello")
        cm.add_assistant_message("Hi there")

        gemini_history = cm.get_gemini_history()
        assert len(gemini_history) == 2
        assert gemini_history[0].role == "user"
        assert gemini_history[1].role == "model"
        assert gemini_history[0].parts[0].text == "Hello"
        assert gemini_history[1].parts[0].text == "Hi there"

    def test_entry_has_timestamp(self, config):
        cm = self._make_manager(config)
        cm.add_user_message("timestamped")
        history = cm.get_history()
        assert "timestamp" in history[0]
        # Should be a valid ISO 8601 timestamp
        ts = history[0]["timestamp"]
        datetime.fromisoformat(ts)  # Raises if invalid

    def test_get_history_returns_copy(self, config):
        """get_history should return a copy, not the internal list."""
        cm = self._make_manager(config)
        cm.add_user_message("one")
        h1 = cm.get_history()
        h1.clear()
        # Internal state should be unaffected
        assert len(cm.get_history()) == 1


# ===================================================================
# Brain Orchestrator Tests
# ===================================================================

class TestBrainOrchestrator:
    """Test the BrainOrchestrator with a fully mocked Gemini model."""

    def _make_orchestrator(
        self,
        config: JarvisConfig,
        event_bus: EventBus | None = None,
        mock_model: MagicMock | None = None,
    ):
        """Build a BrainOrchestrator with all Gemini calls mocked."""
        from jarvis.brain.orchestrator import BrainOrchestrator

        mock_executor = MagicMock()
        mock_executor.execute = MagicMock()  # Will be configured per-test

        with patch("jarvis.brain.orchestrator.genai") as mock_genai, \
             patch("jarvis.brain.orchestrator.get_tool_declarations") as mock_decls, \
             patch("jarvis.brain.orchestrator.get_tool_config") as mock_tc:

            mock_decls.return_value = []
            mock_tc.return_value = MagicMock()

            model_instance = mock_model or MagicMock()
            mock_genai.GenerativeModel.return_value = model_instance

            orchestrator = BrainOrchestrator(
                tool_executor=mock_executor,
                config=config,
                event_bus=event_bus,
            )

        # Expose internals for test configuration
        orchestrator._model = model_instance
        orchestrator._executor = mock_executor
        return orchestrator, mock_executor, model_instance

    # ---- Simple text response (no tools) ----

    @pytest.mark.asyncio
    async def test_simple_text_response(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        # Model returns text, no function calls
        model.generate_content.return_value = _make_text_response(
            "The weather in London is 15 degrees."
        )

        result = await orchestrator.process("What's the weather in London?")

        assert isinstance(result, BrainResponse)
        assert "15 degrees" in result.spoken_text
        assert result.tools_invoked == []
        assert result.sources == []
        assert result.error is None

    @pytest.mark.asyncio
    async def test_user_message_recorded_in_history(self, config):
        orchestrator, _, model = self._make_orchestrator(config)
        model.generate_content.return_value = _make_text_response("Sure thing!")

        await orchestrator.process("Remember this")

        history = orchestrator._conversation.get_history()
        assert len(history) == 2  # user + assistant
        assert history[0]["role"] == "user"
        assert history[0]["text"] == "Remember this"
        assert history[1]["role"] == "assistant"

    # ---- Single tool call flow ----

    @pytest.mark.asyncio
    async def test_single_tool_call(self, config, event_bus):
        orchestrator, mock_executor, model = self._make_orchestrator(
            config, event_bus=event_bus
        )

        # First call: model requests web_search
        fc_response = _make_function_call_response(
            "web_search", {"query": "latest AI news"}
        )
        # Second call: model returns text after receiving tool result
        text_response = _make_text_response(
            "Here are the latest AI developments."
        )
        model.generate_content.side_effect = [fc_response, text_response]

        # Tool executor returns a search result
        search_result = ToolResult(
            success=True,
            data=[
                {"title": "AI News", "url": "https://example.com/ai", "snippet": "Latest AI news"},
            ],
            display_text="Found 1 result",
        )

        async def mock_execute(name, args=None):
            return search_result

        mock_executor.execute = mock_execute

        # Track events
        events_received = []
        event_bus.on("tool_executing", lambda d: events_received.append(("executing", d)))
        event_bus.on("tool_complete", lambda d: events_received.append(("complete", d)))

        result = await orchestrator.process("Search for latest AI news")

        assert result.spoken_text == "Here are the latest AI developments."
        assert len(result.tools_invoked) == 1
        assert result.tools_invoked[0].name == "web_search"
        assert result.tools_invoked[0].arguments == {"query": "latest AI news"}
        assert "https://example.com/ai" in result.sources
        assert result.error is None

        # Events should have been emitted
        assert len(events_received) == 2
        assert events_received[0][0] == "executing"
        assert events_received[1][0] == "complete"

    # ---- Multi-step tool chain ----

    @pytest.mark.asyncio
    async def test_multi_step_tool_chain(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        # Step 1: model requests web_search
        step1 = _make_function_call_response(
            "web_search", {"query": "Python tutorials"}
        )
        # Step 2: model requests open_browser_tabs
        step2 = _make_function_call_response(
            "open_browser_tabs",
            {"urls": ["https://python.org", "https://realpython.com"]},
        )
        # Step 3: model returns text
        step3 = _make_text_response(
            "I found some Python tutorials and opened them for you."
        )
        model.generate_content.side_effect = [step1, step2, step3]

        call_count = 0

        async def mock_execute(name, args=None):
            nonlocal call_count
            call_count += 1
            if name == "web_search":
                return ToolResult(
                    success=True,
                    data=[
                        {"title": "Python.org", "url": "https://python.org", "snippet": "Official"},
                        {"title": "Real Python", "url": "https://realpython.com", "snippet": "Tutorials"},
                    ],
                    display_text="Found 2 results",
                )
            return ToolResult(success=True, data=None, display_text="Opened tabs")

        mock_executor.execute = mock_execute

        result = await orchestrator.process("Find Python tutorials and open them")

        assert call_count == 2
        assert len(result.tools_invoked) == 2
        assert result.tools_invoked[0].name == "web_search"
        assert result.tools_invoked[1].name == "open_browser_tabs"
        assert "Python tutorials" in result.spoken_text
        assert "https://python.org" in result.sources

    # ---- Max iteration limit ----

    @pytest.mark.asyncio
    async def test_max_iteration_limit(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        # Model keeps returning function calls every time (never returns text).
        # After 5 iterations the orchestrator should break out.
        infinite_fc = _make_function_call_response(
            "web_search", {"query": "infinite loop"}
        )
        # generate_content is called: 1 initial + 5 follow-ups = 6 total
        # But the loop runs _MAX_TOOL_ITERATIONS times, so we need that many
        # function call responses.
        model.generate_content.return_value = infinite_fc

        async def mock_execute(name, args=None):
            return ToolResult(success=True, data=None, display_text="ok")

        mock_executor.execute = mock_execute

        result = await orchestrator.process("Do something forever")

        # Should have made exactly 5 tool executions (one per iteration)
        assert len(result.tools_invoked) == 5
        for tc in result.tools_invoked:
            assert tc.name == "web_search"

    # ---- Error handling: Gemini API error ----

    @pytest.mark.asyncio
    async def test_gemini_api_error(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        model.generate_content.side_effect = Exception(
            "API quota exceeded"
        )

        result = await orchestrator.process("Hello")

        assert isinstance(result, BrainResponse)
        assert result.error == "API quota exceeded"
        assert "sorry" in result.spoken_text.lower()
        assert result.tools_invoked == []

    # ---- Error handling: tool execution failure ----

    @pytest.mark.asyncio
    async def test_tool_execution_failure_still_returns(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        fc_response = _make_function_call_response(
            "web_search", {"query": "something"}
        )
        text_response = _make_text_response(
            "I couldn't find results, sorry."
        )
        model.generate_content.side_effect = [fc_response, text_response]

        async def mock_execute(name, args=None):
            return ToolResult(
                success=False,
                error="Network timeout",
                display_text="Search failed",
            )

        mock_executor.execute = mock_execute

        result = await orchestrator.process("Search for something")

        assert result.spoken_text == "I couldn't find results, sorry."
        assert len(result.tools_invoked) == 1
        assert result.tools_invoked[0].result.success is False
        assert result.error is None  # orchestrator itself didn't error

    # ---- Source extraction ----

    @pytest.mark.asyncio
    async def test_sources_extracted_from_tool_results(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        fc_response = _make_function_call_response(
            "web_search", {"query": "news"}
        )
        text_response = _make_text_response("Here's the news.")
        model.generate_content.side_effect = [fc_response, text_response]

        async def mock_execute(name, args=None):
            return ToolResult(
                success=True,
                data=[
                    {"title": "A", "url": "https://a.com", "snippet": "a"},
                    {"title": "B", "url": "https://b.com", "snippet": "b"},
                ],
                display_text="Found results",
            )

        mock_executor.execute = mock_execute

        result = await orchestrator.process("News")

        assert "https://a.com" in result.sources
        assert "https://b.com" in result.sources

    # ---- No sources when tool returns no URLs ----

    @pytest.mark.asyncio
    async def test_no_sources_without_urls(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        fc_response = _make_function_call_response(
            "clipboard_read", {}
        )
        text_response = _make_text_response("Your clipboard says: hello")
        model.generate_content.side_effect = [fc_response, text_response]

        async def mock_execute(name, args=None):
            return ToolResult(
                success=True,
                data="hello",
                display_text="Clipboard: hello",
            )

        mock_executor.execute = mock_execute

        result = await orchestrator.process("Read clipboard")

        assert result.sources == []

    # ---- Conversation history passed to model ----

    @pytest.mark.asyncio
    async def test_conversation_context_sent_to_model(self, config):
        orchestrator, _, model = self._make_orchestrator(config)
        model.generate_content.return_value = _make_text_response("Got it!")

        # Add some prior context
        orchestrator._conversation.add_user_message("My name is Alice")
        orchestrator._conversation.add_assistant_message("Nice to meet you, Alice!")

        await orchestrator.process("What is my name?")

        # generate_content should have been called with the history
        call_args = model.generate_content.call_args
        contents = call_args[0][0]  # First positional arg
        # Should have at least 3 content items:
        # prior user, prior assistant, new user
        assert len(contents) >= 3

    # ---- Event bus is optional ----

    @pytest.mark.asyncio
    async def test_no_event_bus_does_not_crash(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(
            config, event_bus=None
        )

        fc_response = _make_function_call_response("clipboard_read", {})
        text_response = _make_text_response("clipboard content")
        model.generate_content.side_effect = [fc_response, text_response]

        async def mock_execute(name, args=None):
            return ToolResult(success=True, data="test", display_text="ok")

        mock_executor.execute = mock_execute

        # Should not raise even without an event bus
        result = await orchestrator.process("Read clipboard")
        assert result.spoken_text == "clipboard content"

    # ---- Assistant message records tools used ----

    @pytest.mark.asyncio
    async def test_tools_used_recorded_in_history(self, config):
        orchestrator, mock_executor, model = self._make_orchestrator(config)

        fc_response = _make_function_call_response(
            "system_command", {"action": "volume_up"}
        )
        text_response = _make_text_response("Volume increased.")
        model.generate_content.side_effect = [fc_response, text_response]

        async def mock_execute(name, args=None):
            return ToolResult(success=True, data=None, display_text="Done")

        mock_executor.execute = mock_execute

        await orchestrator.process("Turn up the volume")

        history = orchestrator._conversation.get_history()
        assistant_entry = [h for h in history if h["role"] == "assistant"][-1]
        assert "system_command" in assistant_entry["tools_used"]


# ===================================================================
# Orchestrator internal helper tests
# ===================================================================

class TestOrchestratorHelpers:
    """Unit tests for static/internal methods on BrainOrchestrator."""

    def test_extract_text_from_response(self):
        from jarvis.brain.orchestrator import BrainOrchestrator
        resp = _make_text_response("Hello world")
        assert BrainOrchestrator._extract_text(resp) == "Hello world"

    def test_extract_text_empty_response(self):
        from jarvis.brain.orchestrator import BrainOrchestrator
        resp = MagicMock()
        resp.candidates = []
        assert BrainOrchestrator._extract_text(resp) == ""

    def test_extract_function_calls_from_response(self):
        from jarvis.brain.orchestrator import BrainOrchestrator
        resp = _make_function_call_response("web_search", {"query": "test"})
        calls = BrainOrchestrator._extract_function_calls(resp)
        assert len(calls) == 1
        assert calls[0] == ("web_search", {"query": "test"})

    def test_extract_function_calls_empty(self):
        from jarvis.brain.orchestrator import BrainOrchestrator
        resp = _make_text_response("Just text")
        calls = BrainOrchestrator._extract_function_calls(resp)
        assert calls == []

    def test_tool_result_to_dict_success(self):
        from jarvis.brain.orchestrator import BrainOrchestrator
        result = ToolResult(
            success=True,
            data={"key": "value"},
            display_text="All good",
        )
        d = BrainOrchestrator._tool_result_to_dict(result)
        assert d["success"] is True
        assert d["data"] == {"key": "value"}
        assert d["display_text"] == "All good"
        assert "error" not in d

    def test_tool_result_to_dict_failure(self):
        from jarvis.brain.orchestrator import BrainOrchestrator
        result = ToolResult(
            success=False,
            error="Something went wrong",
            display_text="Failed",
        )
        d = BrainOrchestrator._tool_result_to_dict(result)
        assert d["success"] is False
        assert d["error"] == "Something went wrong"
        assert "data" not in d

    def test_extract_sources_with_urls(self):
        from jarvis.brain.orchestrator import _extract_sources
        results = [
            ToolResult(
                success=True,
                data=[
                    {"title": "A", "url": "https://a.com"},
                    {"title": "B", "url": "https://b.com"},
                ],
            ),
        ]
        assert _extract_sources(results) == ["https://a.com", "https://b.com"]

    def test_extract_sources_no_urls(self):
        from jarvis.brain.orchestrator import _extract_sources
        results = [
            ToolResult(success=True, data="plain string"),
        ]
        assert _extract_sources(results) == []

    def test_extract_sources_failed_result_skipped(self):
        from jarvis.brain.orchestrator import _extract_sources
        results = [
            ToolResult(
                success=False,
                data=[{"url": "https://should-not-appear.com"}],
                error="failed",
            ),
        ]
        assert _extract_sources(results) == []
