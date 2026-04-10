"""Brain orchestrator — routes user text through Gemini and executes tool calls.

Receives natural-language input, sends it to the Gemini model with the full
set of Jarvis tool declarations, executes any function calls the model
requests, feeds results back, and returns a :class:`BrainResponse` containing
the final spoken text, tool invocations, and source URLs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import google.generativeai as genai
from google.generativeai import protos

from jarvis.brain.conversation import ConversationManager
from jarvis.brain.tool_definitions import get_tool_config, get_tool_declarations
from jarvis.hands.tool_executor import ToolExecutor
from jarvis.shared.config import JarvisConfig
from jarvis.shared.events import EventBus
from jarvis.shared.types import BrainResponse, ToolCall, ToolResult

logger = logging.getLogger(__name__)

# Maximum number of tool-call round-trips per user request to prevent
# infinite loops when the model keeps requesting tools.
_MAX_TOOL_ITERATIONS = 5

# Path to the system prompt relative to this file.
_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.txt"


def _load_system_prompt() -> str:
    """Read the system prompt from disk."""
    try:
        return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("Could not load system prompt from %s", _SYSTEM_PROMPT_PATH)
        return "You are Jarvis, a helpful desktop AI assistant."


def _extract_sources(tool_results: list[ToolResult]) -> list[str]:
    """Pull out any URLs found in tool result data (search results, etc.)."""
    sources: list[str] = []
    for result in tool_results:
        if not result.success or result.data is None:
            continue
        data = result.data
        # Handle list of dicts (e.g. search results with 'url' keys)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "url" in item:
                    sources.append(item["url"])
        # Handle a single dict with a 'url' key
        elif isinstance(data, dict) and "url" in data:
            sources.append(data["url"])
    return sources


class BrainOrchestrator:
    """Main LLM orchestrator — translates user intent into actions.

    Parameters
    ----------
    tool_executor:
        The :class:`ToolExecutor` that actually runs tool handlers.
    config:
        Jarvis configuration (API keys, model name, paths, etc.).
    event_bus:
        Optional event bus for publishing ``tool_executing`` /
        ``tool_complete`` events.
    """

    def __init__(
        self,
        tool_executor: ToolExecutor,
        config: JarvisConfig,
        event_bus: EventBus | None = None,
    ) -> None:
        self._executor = tool_executor
        self._config = config
        self._event_bus = event_bus

        # Configure the Gemini SDK with the API key.
        genai.configure(api_key=config.gemini_api_key)

        # Load the system prompt once.
        self._system_prompt = _load_system_prompt()

        # Build the generative model.
        self._model = genai.GenerativeModel(
            model_name=config.gemini_model,
            system_instruction=self._system_prompt,
            tools=[protos.Tool(function_declarations=get_tool_declarations())],
            tool_config=get_tool_config(),
        )

        # Conversation manager for history tracking.
        self._conversation = ConversationManager(config)
        self._conversation.load_today()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, user_text: str) -> BrainResponse:
        """Process a single user utterance end-to-end.

        1. Record the user message in conversation history.
        2. Send the conversation to Gemini with tool declarations.
        3. If Gemini responds with function calls, execute them via
           the tool executor, feed results back, and repeat (up to
           ``_MAX_TOOL_ITERATIONS`` rounds).
        4. When Gemini returns a text response, package it as a
           :class:`BrainResponse` and return.
        """
        self._conversation.add_user_message(user_text)

        all_tool_calls: list[ToolCall] = []
        all_tool_results: list[ToolResult] = []

        try:
            # Build the initial contents list: history + current user turn.
            contents = self._conversation.get_gemini_history()

            response = self._model.generate_content(contents)

            for _iteration in range(_MAX_TOOL_ITERATIONS):
                # Inspect the response for function calls vs. text.
                function_calls = self._extract_function_calls(response)

                if not function_calls:
                    # No more tool calls — model has produced its final text.
                    break

                # Execute every function call the model requested.
                function_response_parts: list[protos.Part] = []

                for fc_name, fc_args in function_calls:
                    tool_call = ToolCall(name=fc_name, arguments=fc_args)

                    # Emit event before execution.
                    self._emit("tool_executing", tool_call)

                    result = await self._executor.execute(fc_name, fc_args)
                    tool_call.result = result

                    all_tool_calls.append(tool_call)
                    all_tool_results.append(result)

                    # Emit event after execution.
                    self._emit("tool_complete", result)

                    # Build the function response part for Gemini.
                    response_payload = self._tool_result_to_dict(result)
                    function_response_parts.append(
                        protos.Part(
                            function_response=protos.FunctionResponse(
                                name=fc_name,
                                response=response_payload,
                            )
                        )
                    )

                # Send the function responses back to Gemini.
                response = self._model.generate_content(
                    contents
                    + [response.candidates[0].content]
                    + [
                        protos.Content(
                            role="user",
                            parts=function_response_parts,
                        )
                    ]
                )
            else:
                # Exhausted max iterations — force a text summary.
                logger.warning(
                    "Reached max tool iterations (%d) for: %s",
                    _MAX_TOOL_ITERATIONS,
                    user_text[:80],
                )

            # Extract the final text from the response.
            spoken_text = self._extract_text(response)
            sources = _extract_sources(all_tool_results)

            # Persist assistant turn.
            tools_used = [tc.name for tc in all_tool_calls]
            self._conversation.add_assistant_message(spoken_text, tools_used)

            return BrainResponse(
                spoken_text=spoken_text,
                tools_invoked=all_tool_calls,
                sources=sources,
            )

        except Exception as exc:
            logger.exception("Brain processing failed for: %s", user_text[:80])
            error_msg = str(exc)
            spoken = "I'm sorry, I ran into a problem processing your request. Please try again."
            self._conversation.add_assistant_message(spoken, [])
            return BrainResponse(
                spoken_text=spoken,
                tools_invoked=all_tool_calls,
                sources=[],
                error=error_msg,
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_function_calls(
        response: Any,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return a list of ``(name, args)`` tuples from a Gemini response."""
        calls: list[tuple[str, dict[str, Any]]] = []
        try:
            parts = response.candidates[0].content.parts
        except (IndexError, AttributeError):
            return calls

        for part in parts:
            fn = getattr(part, "function_call", None)
            if fn is not None and fn.name:
                # fn.args is a proto Struct; convert to plain dict.
                args = dict(fn.args) if fn.args else {}
                calls.append((fn.name, args))
        return calls

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull the concatenated text from a Gemini response."""
        try:
            parts = response.candidates[0].content.parts
        except (IndexError, AttributeError):
            return ""
        texts: list[str] = []
        for part in parts:
            if hasattr(part, "text") and part.text:
                texts.append(part.text)
        return " ".join(texts).strip() if texts else ""

    @staticmethod
    def _tool_result_to_dict(result: ToolResult) -> dict[str, Any]:
        """Convert a :class:`ToolResult` to a plain dict for the Gemini
        function response payload."""
        payload: dict[str, Any] = {"success": result.success}
        if result.data is not None:
            payload["data"] = result.data
        if result.display_text:
            payload["display_text"] = result.display_text
        if result.error:
            payload["error"] = result.error
        return payload

    def _emit(self, event: str, data: Any) -> None:
        """Emit an event if an event bus is configured."""
        if self._event_bus is not None:
            self._event_bus.emit(event, data)
