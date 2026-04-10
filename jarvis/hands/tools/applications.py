"""Application launcher tool with fuzzy alias resolution.

Resolves shorthand names (e.g. "code" -> "Visual Studio Code") using
the app_aliases mapping in JarvisConfig, then delegates to Platform.open_app.
"""

import logging
from typing import Any

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)


def _resolve_app_name(name: str, aliases: dict[str, str]) -> str:
    """Resolve an application name using the alias map.

    Matching strategy (in priority order):
    1. Exact match on alias key (case-insensitive).
    2. Substring match on alias key.
    3. Substring match on alias value (the full app name).
    4. Return the original name unchanged (let the OS figure it out).
    """
    name_lower = name.lower().strip()

    # 1. Exact key match
    for alias_key, full_name in aliases.items():
        if alias_key.lower() == name_lower:
            return full_name

    # 2. Substring match on keys
    for alias_key, full_name in aliases.items():
        if name_lower in alias_key.lower() or alias_key.lower() in name_lower:
            return full_name

    # 3. Substring match on values
    for full_name in aliases.values():
        if name_lower in full_name.lower():
            return full_name

    # 4. Nothing matched — return as-is
    return name


async def open_application(
    app_name: str,
    arguments: list[str] | None = None,
    *,
    _platform: Platform,
    _config: JarvisConfig,
) -> ToolResult:
    """Open an application, resolving aliases first.

    Args:
        app_name: Application name or alias (e.g. "code", "chrome").
        arguments: Optional list of command-line arguments.
        _platform: Injected Platform instance.
        _config: Injected JarvisConfig.
    """
    resolved = _resolve_app_name(app_name, _config.app_aliases)
    logger.info("Resolved '%s' -> '%s'", app_name, resolved)

    ok = await _platform.open_app(resolved, args=arguments)
    if ok:
        display = f"Opened {resolved}."
        if resolved != app_name:
            display = f"Opened {resolved} (matched from '{app_name}')."
        return ToolResult(success=True, data={"app": resolved}, display_text=display)

    return ToolResult(
        success=False,
        error=f"Could not open '{resolved}'",
        display_text=f"Failed to open {resolved}.",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(executor: Any, platform: Platform, config: JarvisConfig) -> None:
    """Register application tools with the executor."""
    from functools import partial

    executor.register(
        "open_application",
        partial(open_application, _platform=platform, _config=config),
    )
