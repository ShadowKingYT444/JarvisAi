"""Media control tool — play/pause, next, previous using native key events."""

import logging
import sys

from jarvis.hands.platform import _run_subprocess
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)

# Windows virtual key codes for media keys
_VK_MEDIA_NEXT = 0xB0       # 176
_VK_MEDIA_PREV = 0xB1       # 177
_VK_MEDIA_STOP = 0xB2       # 178
_VK_MEDIA_PLAY_PAUSE = 0xB3  # 179

# PowerShell snippet that sends a proper virtual key event via user32.dll
_WIN_KEYBD_EVENT_SCRIPT = """
Add-Type -MemberDefinition @'
[DllImport("user32.dll")]
public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
'@ -Name NativeMethods -Namespace Win32
[Win32.NativeMethods]::keybd_event({vk}, 0, 0, [UIntPtr]::Zero)
[Win32.NativeMethods]::keybd_event({vk}, 0, 2, [UIntPtr]::Zero)
"""


async def _send_media_key_windows(vk_code: int) -> bool:
    """Send a media virtual key press on Windows via user32.dll keybd_event."""
    script = _WIN_KEYBD_EVENT_SCRIPT.format(vk=vk_code)
    ok, _ = await _run_subprocess(
        ["powershell", "-NoProfile", "-Command", script]
    )
    return ok


async def media_play_pause(**kwargs) -> ToolResult:
    """Toggle media play/pause."""
    if sys.platform == "win32":
        ok = await _send_media_key_windows(_VK_MEDIA_PLAY_PAUSE)
        return ToolResult(success=ok, display_text="Toggled play/pause.")
    elif sys.platform == "darwin":
        from jarvis.hands.platform import _run_applescript
        ok, _ = await _run_applescript(
            'tell application "System Events" to key code 16 using {command down}'
        )
        return ToolResult(success=ok, display_text="Toggled play/pause.")
    return ToolResult(success=False, error="Not supported on this platform.")


async def media_next(**kwargs) -> ToolResult:
    """Skip to next track."""
    if sys.platform == "win32":
        ok = await _send_media_key_windows(_VK_MEDIA_NEXT)
        return ToolResult(success=ok, display_text="Skipped to next track.")
    return ToolResult(success=False, error="Not supported on this platform.")


async def media_previous(**kwargs) -> ToolResult:
    """Go to previous track."""
    if sys.platform == "win32":
        ok = await _send_media_key_windows(_VK_MEDIA_PREV)
        return ToolResult(success=ok, display_text="Went to previous track.")
    return ToolResult(success=False, error="Not supported on this platform.")


def register(executor, platform, config):
    executor.register("media_play_pause", media_play_pause)
    executor.register("media_next", media_next)
    executor.register("media_previous", media_previous)
