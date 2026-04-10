"""Tool declarations for the Gemini function-calling API.

Each tool that Jarvis can invoke is described here as a
``google.generativeai.protos.FunctionDeclaration`` so the model knows
what tools are available and what parameters they accept.
"""

from __future__ import annotations

import google.generativeai as genai
from google.generativeai import protos


# ── helpers ────────────────────────────────────────────────────────────

def _schema(
    type_: protos.Type,
    description: str = "",
    enum: list[str] | None = None,
    items: protos.Schema | None = None,
    properties: dict[str, protos.Schema] | None = None,
    required: list[str] | None = None,
) -> protos.Schema:
    """Shortcut to build a ``protos.Schema`` with commonly-used fields."""
    kwargs: dict = {"type": type_, "description": description}
    if enum is not None:
        kwargs["enum"] = enum
    if items is not None:
        kwargs["items"] = items
    if properties is not None:
        kwargs["properties"] = properties
    if required is not None:
        kwargs["required"] = required
    return protos.Schema(**kwargs)


def _string(desc: str = "", enum: list[str] | None = None) -> protos.Schema:
    return _schema(protos.Type.STRING, description=desc, enum=enum)


def _number(desc: str = "") -> protos.Schema:
    return _schema(protos.Type.NUMBER, description=desc)


def _integer(desc: str = "") -> protos.Schema:
    return _schema(protos.Type.INTEGER, description=desc)


def _boolean(desc: str = "") -> protos.Schema:
    return _schema(protos.Type.BOOLEAN, description=desc)


def _array(desc: str = "", items: protos.Schema | None = None) -> protos.Schema:
    return _schema(protos.Type.ARRAY, description=desc, items=items)


# ── tool declarations ─────────────────────────────────────────────────

_SYSTEM_COMMAND_ACTIONS = [
    "volume_up",
    "volume_down",
    "volume_set",
    "mute",
    "unmute",
    "brightness_up",
    "brightness_down",
    "brightness_set",
    "sleep",
    "lock_screen",
    "screenshot",
    "toggle_dark_mode",
    "empty_trash",
    "show_desktop",
]


def _build_declarations() -> list[protos.FunctionDeclaration]:
    """Create and return all Jarvis tool declarations."""

    web_search = protos.FunctionDeclaration(
        name="web_search",
        description=(
            "Search the web for a query and return a list of results "
            "with titles, snippets, and URLs."
        ),
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "query": _string("The search query string."),
                "num_results": _integer(
                    "Number of results to return (default 5)."
                ),
            },
            required=["query"],
        ),
    )

    open_browser_tabs = protos.FunctionDeclaration(
        name="open_browser_tabs",
        description="Open one or more URLs in the user's default browser.",
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "urls": _array(
                    "List of URLs to open.",
                    items=_string("A URL"),
                ),
                "focus": _boolean(
                    "Whether to bring the browser to the foreground (default true)."
                ),
            },
            required=["urls"],
        ),
    )

    open_application = protos.FunctionDeclaration(
        name="open_application",
        description="Launch a desktop application by name.",
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "app_name": _string("Name of the application to open."),
                "arguments": _array(
                    "Optional command-line arguments.",
                    items=_string("An argument"),
                ),
            },
            required=["app_name"],
        ),
    )

    close_browser_tab = protos.FunctionDeclaration(
        name="close_browser_tab",
        description=(
            "Close a browser tab whose title or URL matches the given string."
        ),
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "match": _string(
                    "Substring to match against tab titles or URLs."
                ),
                "all_matching": _boolean(
                    "If true, close ALL matching tabs instead of just the first."
                ),
            },
            required=["match"],
        ),
    )

    google_search_and_display = protos.FunctionDeclaration(
        name="google_search_and_display",
        description=(
            "Search Google, open the top results in browser tabs, and "
            "optionally summarize the findings."
        ),
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "query": _string("The search query."),
                "num_tabs": _integer(
                    "Number of result tabs to open (default 3)."
                ),
                "summarize": _boolean(
                    "Whether to return a spoken summary (default true)."
                ),
            },
            required=["query"],
        ),
    )

    system_command = protos.FunctionDeclaration(
        name="system_command",
        description=(
            "Execute a system-level command such as adjusting volume, "
            "brightness, locking the screen, taking a screenshot, etc."
        ),
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "action": _string(
                    "The system action to perform.",
                    enum=_SYSTEM_COMMAND_ACTIONS,
                ),
                "value": _number(
                    "Numeric value for actions that need one "
                    "(e.g. volume_set 0-100, brightness_set 0-100)."
                ),
            },
            required=["action"],
        ),
    )

    clipboard_read = protos.FunctionDeclaration(
        name="clipboard_read",
        description="Read the current contents of the system clipboard.",
        parameters=_schema(
            protos.Type.OBJECT,
            properties={},
        ),
    )

    clipboard_write = protos.FunctionDeclaration(
        name="clipboard_write",
        description="Write text to the system clipboard.",
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "text": _string("The text to copy to the clipboard."),
            },
            required=["text"],
        ),
    )

    focus_mode = protos.FunctionDeclaration(
        name="focus_mode",
        description=(
            "Start, stop, or check the status of a focus session that "
            "blocks distracting websites/apps."
        ),
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "action": _string(
                    "The focus-mode action to perform.",
                    enum=["start", "stop", "status"],
                ),
                "goal": _string(
                    "A short description of what the user wants to focus on "
                    "(used when action is 'start')."
                ),
                "strictness": _string(
                    "How strict the blocking should be.",
                    enum=["low", "medium", "high"],
                ),
            },
            required=["action"],
        ),
    )

    set_reminder = protos.FunctionDeclaration(
        name="set_reminder",
        description="Set a reminder that fires after a given number of minutes.",
        parameters=_schema(
            protos.Type.OBJECT,
            properties={
                "message": _string("The reminder message to speak."),
                "minutes": _integer("Minutes from now to trigger the reminder."),
            },
            required=["message", "minutes"],
        ),
    )

    get_active_tabs = protos.FunctionDeclaration(
        name="get_active_tabs",
        description=(
            "List all currently open browser tabs with their titles and URLs."
        ),
        parameters=_schema(
            protos.Type.OBJECT,
            properties={},
        ),
    )

    return [
        web_search,
        open_browser_tabs,
        open_application,
        close_browser_tab,
        google_search_and_display,
        system_command,
        clipboard_read,
        clipboard_write,
        focus_mode,
        set_reminder,
        get_active_tabs,
    ]


# ── public API ─────────────────────────────────────────────────────────

_DECLARATIONS: list[protos.FunctionDeclaration] | None = None


def get_tool_declarations() -> list[protos.FunctionDeclaration]:
    """Return the list of Gemini ``FunctionDeclaration`` objects for all
    Jarvis tools.  The list is built once and cached."""
    global _DECLARATIONS
    if _DECLARATIONS is None:
        _DECLARATIONS = _build_declarations()
    return list(_DECLARATIONS)


def get_tool_config() -> genai.protos.ToolConfig:
    """Return a Gemini ``ToolConfig`` that allows the model to decide
    when to call functions (AUTO mode)."""
    return genai.protos.ToolConfig(
        function_calling_config=genai.protos.FunctionCallingConfig(
            mode=genai.protos.FunctionCallingConfig.Mode.AUTO,
        ),
    )
