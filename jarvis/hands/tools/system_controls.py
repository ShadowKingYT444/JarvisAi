"""System control tools — volume, dark mode, screenshot, lock, etc.

Thin wrapper that validates the action name and delegates to
Platform.run_system_command.
"""

import logging
from typing import Any

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)

# Canonical action names and their human-readable descriptions
_SUPPORTED_ACTIONS: dict[str, str] = {
    "volume_up": "Increase volume",
    "volume_down": "Decrease volume",
    "volume_mute": "Mute audio",
    "volume_set": "Set volume to a specific level (0-100)",
    "dark_mode_on": "Enable dark mode",
    "dark_mode_off": "Disable dark mode",
    "lock_screen": "Lock the screen",
    "screenshot": "Take a screenshot",
    "empty_trash": "Empty the trash / recycle bin",
    "dnd_on": "Enable Do Not Disturb",
    "dnd_off": "Disable Do Not Disturb",
    "sleep": "Put the computer to sleep",
    "brightness_up": "Increase screen brightness",
    "brightness_down": "Decrease screen brightness",
}


async def system_command(
    action: str,
    value: Any = None,
    *,
    _platform: Platform,
) -> ToolResult:
    """Execute a system-level command.

    Args:
        action: One of the supported action names (e.g. "volume_up", "dark_mode_on").
        value: Optional value for actions that need one (e.g. volume_set needs 0-100).
        _platform: Injected Platform instance.

    Returns:
        ToolResult indicating success or failure.
    """
    normalised = action.lower().strip().replace("-", "_").replace(" ", "_")

    if normalised not in _SUPPORTED_ACTIONS:
        supported = ", ".join(sorted(_SUPPORTED_ACTIONS))
        return ToolResult(
            success=False,
            error=f"Unknown action '{action}'. Supported: {supported}",
            display_text=f"Unknown system command: {action}",
        )

    ok = await _platform.run_system_command(normalised, value)
    desc = _SUPPORTED_ACTIONS[normalised]

    if ok:
        display = f"{desc}."
        if value is not None:
            display = f"{desc} ({value})."
        return ToolResult(success=True, data={"action": normalised, "value": value}, display_text=display)

    return ToolResult(
        success=False,
        error=f"Platform failed to execute '{normalised}'",
        display_text=f"Failed: {desc}.",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(executor: Any, platform: Platform, config: JarvisConfig) -> None:
    """Register system_command tool with the executor."""
    from functools import partial

    executor.register("system_command", partial(system_command, _platform=platform))
