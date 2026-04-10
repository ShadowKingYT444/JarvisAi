"""Clipboard read/write tools.

Thin wrappers around Platform.clipboard_read and Platform.clipboard_write.
"""

import logging
from typing import Any

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)


async def clipboard_read(*, _platform: Platform) -> ToolResult:
    """Read the current text content of the system clipboard.

    Returns:
        ToolResult with data=<clipboard text>.
    """
    text = await _platform.clipboard_read()
    if text:
        preview = text[:200] + ("..." if len(text) > 200 else "")
        return ToolResult(
            success=True,
            data=text,
            display_text=f"Clipboard contents: {preview}",
        )
    return ToolResult(
        success=True,
        data="",
        display_text="Clipboard is empty.",
    )


async def clipboard_write(text: str, *, _platform: Platform) -> ToolResult:
    """Write text to the system clipboard.

    Args:
        text: The text to copy to the clipboard.

    Returns:
        ToolResult indicating success or failure.
    """
    if not text:
        return ToolResult(
            success=False,
            error="Cannot write empty text to clipboard",
            display_text="Nothing to copy — text was empty.",
        )

    ok = await _platform.clipboard_write(text)
    if ok:
        preview = text[:100] + ("..." if len(text) > 100 else "")
        return ToolResult(
            success=True,
            data={"length": len(text)},
            display_text=f"Copied to clipboard: {preview}",
        )
    return ToolResult(
        success=False,
        error="Platform clipboard write failed",
        display_text="Failed to write to clipboard.",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(executor: Any, platform: Platform, config: JarvisConfig) -> None:
    """Register clipboard tools with the executor."""
    from functools import partial

    executor.register("clipboard_read", partial(clipboard_read, _platform=platform))
    executor.register("clipboard_write", partial(clipboard_write, _platform=platform))
