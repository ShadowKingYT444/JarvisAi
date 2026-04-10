"""Platform abstraction layer for OS-specific operations.

Provides a unified interface for browser control, application launching,
system commands, and clipboard access across macOS and Windows.
"""

import asyncio
import logging
import platform
import subprocess
from abc import ABC, abstractmethod
from typing import Any

from jarvis.shared.types import TabInfo

logger = logging.getLogger(__name__)


class Platform(ABC):
    """Abstract base for platform-specific operations."""

    @abstractmethod
    async def open_url(self, url: str) -> bool:
        """Open a URL in the default or running browser."""
        ...

    @abstractmethod
    async def open_app(self, name: str, args: list[str] | None = None) -> bool:
        """Launch an application by name."""
        ...

    @abstractmethod
    async def get_browser_tabs(self) -> list[TabInfo]:
        """Return all open browser tabs across supported browsers."""
        ...

    @abstractmethod
    async def close_browser_tab(self, match: str, all_matching: bool = False) -> int:
        """Close tab(s) whose title or URL contains *match*.

        Returns the number of tabs closed.
        """
        ...

    @abstractmethod
    async def run_system_command(self, action: str, value: Any = None) -> bool:
        """Execute a system-level command (volume, dark mode, lock, etc.)."""
        ...

    @abstractmethod
    async def clipboard_read(self) -> str:
        """Read current clipboard text content."""
        ...

    @abstractmethod
    async def clipboard_write(self, text: str) -> bool:
        """Write text to the system clipboard."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_subprocess(
    cmd: list[str] | str,
    *,
    shell: bool = False,
    timeout: float = 15,
    input_data: str | None = None,
) -> tuple[bool, str]:
    """Run a subprocess asynchronously and return (success, stdout/stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *(cmd if isinstance(cmd, list) else cmd.split()),
            stdin=asyncio.subprocess.PIPE if input_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        ) if not shell else await asyncio.create_subprocess_shell(
            cmd if isinstance(cmd, str) else " ".join(cmd),
            stdin=asyncio.subprocess.PIPE if input_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_data.encode() if input_data else None),
            timeout=timeout,
        )
        if proc.returncode == 0:
            return True, stdout.decode().strip()
        return False, stderr.decode().strip()
    except asyncio.TimeoutError:
        return False, "Command timed out"
    except Exception as exc:
        return False, str(exc)


async def _run_applescript(script: str, timeout: float = 10) -> tuple[bool, str]:
    """Execute an AppleScript string via osascript."""
    return await _run_subprocess(["osascript", "-e", script], timeout=timeout)


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

# Browsers we know how to query via AppleScript
_MACOS_BROWSERS = {
    "Google Chrome": {
        "tab_count": 'count of tabs of window {w}',
        "tab_title": 'title of tab {t} of window {w}',
        "tab_url": 'URL of tab {t} of window {w}',
        "close_tab": 'close tab {t} of window {w}',
        "open_url": '''
            tell application "Google Chrome"
                activate
                tell window 1
                    make new tab with properties {{URL:"{url}"}}
                end tell
            end tell''',
    },
    "Safari": {
        "tab_count": 'count of tabs of window {w}',
        "tab_title": 'name of tab {t} of window {w}',
        "tab_url": 'URL of tab {t} of window {w}',
        "close_tab": 'close tab {t} of window {w}',
        "open_url": '''
            tell application "Safari"
                activate
                tell window 1
                    set newTab to make new tab
                    set URL of newTab to "{url}"
                end tell
            end tell''',
    },
    "Arc": {
        "tab_count": 'count of tabs of window {w}',
        "tab_title": 'title of tab {t} of window {w}',
        "tab_url": 'URL of tab {t} of window {w}',
        "close_tab": 'close tab {t} of window {w}',
        "open_url": '''
            tell application "Arc"
                activate
                tell window 1
                    make new tab with properties {{URL:"{url}"}}
                end tell
            end tell''',
    },
    "Firefox": {
        # Firefox AppleScript support is limited; we use open location
        "tab_count": None,
        "tab_title": None,
        "tab_url": None,
        "close_tab": None,
        "open_url": '''
            tell application "Firefox"
                activate
                open location "{url}"
            end tell''',
    },
}


class MacOSPlatform(Platform):
    """macOS implementation using AppleScript and system utilities."""

    # ---- helpers ----

    async def _running_browsers(self) -> list[str]:
        """Detect which supported browsers are currently running."""
        script = (
            'tell application "System Events" to get name of every process '
            'whose background only is false'
        )
        ok, output = await _run_applescript(script)
        if not ok:
            return []
        running = {name.strip() for name in output.split(",")}
        return [b for b in _MACOS_BROWSERS if b in running]

    async def _get_tabs_for_browser(self, browser: str) -> list[TabInfo]:
        """Get all tabs for a single browser via AppleScript."""
        meta = _MACOS_BROWSERS.get(browser, {})
        if meta.get("tab_count") is None:
            return []  # browser doesn't support tab enumeration

        # Build a single AppleScript that fetches all tabs with ||| delimiters
        if browser == "Google Chrome":
            script = '''
            set output to ""
            tell application "Google Chrome"
                set windowCount to count of windows
                repeat with w from 1 to windowCount
                    set tabCount to count of tabs of window w
                    repeat with t from 1 to tabCount
                        set tabTitle to title of tab t of window w
                        set tabURL to URL of tab t of window w
                        set output to output & w & "|||" & t & "|||" & tabTitle & "|||" & tabURL & "\\n"
                    end repeat
                end repeat
            end tell
            return output
            '''
        elif browser == "Safari":
            script = '''
            set output to ""
            tell application "Safari"
                set windowCount to count of windows
                repeat with w from 1 to windowCount
                    set tabCount to count of tabs of window w
                    repeat with t from 1 to tabCount
                        set tabTitle to name of tab t of window w
                        set tabURL to URL of tab t of window w
                        set output to output & w & "|||" & t & "|||" & tabTitle & "|||" & tabURL & "\\n"
                    end repeat
                end repeat
            end tell
            return output
            '''
        elif browser == "Arc":
            script = '''
            set output to ""
            tell application "Arc"
                set windowCount to count of windows
                repeat with w from 1 to windowCount
                    set tabCount to count of tabs of window w
                    repeat with t from 1 to tabCount
                        set tabTitle to title of tab t of window w
                        set tabURL to URL of tab t of window w
                        set output to output & w & "|||" & t & "|||" & tabTitle & "|||" & tabURL & "\\n"
                    end repeat
                end repeat
            end tell
            return output
            '''
        else:
            return []

        ok, output = await _run_applescript(script)
        if not ok:
            logger.warning("Failed to get tabs for %s: %s", browser, output)
            return []

        tabs: list[TabInfo] = []
        for line in output.strip().split("\n"):
            if not line or "|||" not in line:
                continue
            parts = line.split("|||")
            if len(parts) >= 4:
                tabs.append(TabInfo(
                    title=parts[2].strip(),
                    url=parts[3].strip(),
                    browser=browser,
                    window_index=int(parts[0].strip()),
                    tab_index=int(parts[1].strip()),
                ))
        return tabs

    # ---- Platform interface ----

    async def open_url(self, url: str) -> bool:
        browsers = await self._running_browsers()
        # Prefer an already-running browser
        for browser in browsers:
            meta = _MACOS_BROWSERS[browser]
            script = meta["open_url"].format(url=url)
            ok, _ = await _run_applescript(script)
            if ok:
                return True
        # Fallback: let the OS decide
        ok, _ = await _run_subprocess(["open", url])
        return ok

    async def open_app(self, name: str, args: list[str] | None = None) -> bool:
        cmd = ["open", "-a", name]
        if args:
            cmd.append("--args")
            cmd.extend(args)
        ok, err = await _run_subprocess(cmd)
        if not ok:
            logger.warning("open_app(%s) failed: %s", name, err)
        return ok

    async def get_browser_tabs(self) -> list[TabInfo]:
        browsers = await self._running_browsers()
        all_tabs: list[TabInfo] = []
        for browser in browsers:
            all_tabs.extend(await self._get_tabs_for_browser(browser))
        return all_tabs

    async def close_browser_tab(self, match: str, all_matching: bool = False) -> int:
        tabs = await self.get_browser_tabs()
        match_lower = match.lower()

        # Filter to matching tabs
        targets = [
            t for t in tabs
            if match_lower in t.title.lower() or match_lower in t.url.lower()
        ]
        if not targets:
            return 0

        if not all_matching:
            targets = targets[:1]

        # Sort by (window, tab) descending so closing doesn't invalidate indices
        targets.sort(key=lambda t: (t.window_index, t.tab_index), reverse=True)

        closed = 0
        for tab in targets:
            meta = _MACOS_BROWSERS.get(tab.browser, {})
            close_tmpl = meta.get("close_tab")
            if not close_tmpl:
                continue
            close_cmd = close_tmpl.format(w=tab.window_index, t=tab.tab_index)
            script = f'tell application "{tab.browser}" to {close_cmd}'
            ok, _ = await _run_applescript(script)
            if ok:
                closed += 1
        return closed

    async def run_system_command(self, action: str, value: Any = None) -> bool:
        action = action.lower().replace("-", "_")
        handlers: dict[str, Any] = {
            "volume_up": self._volume_up,
            "volume_down": self._volume_down,
            "volume_mute": self._volume_mute,
            "volume_set": self._volume_set,
            "dark_mode_on": self._dark_mode_on,
            "dark_mode_off": self._dark_mode_off,
            "lock_screen": self._lock_screen,
            "screenshot": self._screenshot,
            "empty_trash": self._empty_trash,
            "dnd_on": self._dnd_on,
            "dnd_off": self._dnd_off,
            "sleep": self._sleep,
            "brightness_up": self._brightness_up,
            "brightness_down": self._brightness_down,
        }
        handler = handlers.get(action)
        if handler is None:
            logger.warning("Unknown system command: %s", action)
            return False
        return await handler(value)

    # ---- system command helpers ----

    async def _volume_up(self, _: Any) -> bool:
        ok, _ = await _run_applescript('set volume output volume ((output volume of (get volume settings)) + 10)')
        return ok

    async def _volume_down(self, _: Any) -> bool:
        ok, _ = await _run_applescript('set volume output volume ((output volume of (get volume settings)) - 10)')
        return ok

    async def _volume_mute(self, _: Any) -> bool:
        ok, _ = await _run_applescript('set volume output muted true')
        return ok

    async def _volume_set(self, value: Any) -> bool:
        level = int(value) if value is not None else 50
        ok, _ = await _run_applescript(f'set volume output volume {level}')
        return ok

    async def _dark_mode_on(self, _: Any) -> bool:
        script = 'tell application "System Events" to tell appearance preferences to set dark mode to true'
        ok, _ = await _run_applescript(script)
        return ok

    async def _dark_mode_off(self, _: Any) -> bool:
        script = 'tell application "System Events" to tell appearance preferences to set dark mode to false'
        ok, _ = await _run_applescript(script)
        return ok

    async def _lock_screen(self, _: Any) -> bool:
        ok, _ = await _run_subprocess(
            ["pmset", "displaysleepnow"],
        )
        return ok

    async def _screenshot(self, _: Any) -> bool:
        ok, _ = await _run_subprocess(["screencapture", "-i", "-c"])
        return ok

    async def _empty_trash(self, _: Any) -> bool:
        script = 'tell application "Finder" to empty trash'
        ok, _ = await _run_applescript(script)
        return ok

    async def _dnd_on(self, _: Any) -> bool:
        # Toggle Focus/DnD via shortcuts (Monterey+)
        script = '''
        tell application "System Events"
            tell process "ControlCenter"
                click menu bar item "Focus" of menu bar 1
            end tell
        end tell
        '''
        ok, _ = await _run_applescript(script, timeout=5)
        return ok

    async def _dnd_off(self, _: Any) -> bool:
        # Same toggle approach
        return await self._dnd_on(None)

    async def _sleep(self, _: Any) -> bool:
        ok, _ = await _run_subprocess(["pmset", "sleepnow"])
        return ok

    async def _brightness_up(self, _: Any) -> bool:
        # Requires brightness CLI tool or AppleScript workaround
        ok, _ = await _run_applescript(
            'tell application "System Events" to key code 144'  # F15 brightness up
        )
        return ok

    async def _brightness_down(self, _: Any) -> bool:
        ok, _ = await _run_applescript(
            'tell application "System Events" to key code 145'  # F14 brightness down
        )
        return ok

    # ---- clipboard ----

    async def clipboard_read(self) -> str:
        ok, text = await _run_subprocess(["pbpaste"])
        return text if ok else ""

    async def clipboard_write(self, text: str) -> bool:
        ok, _ = await _run_subprocess(["pbcopy"], input_data=text)
        return ok


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

class WindowsPlatform(Platform):
    """Windows implementation using PowerShell and COM objects."""

    async def _powershell(self, script: str, timeout: float = 15) -> tuple[bool, str]:
        return await _run_subprocess(
            ["powershell", "-NoProfile", "-Command", script],
            timeout=timeout,
        )

    async def open_url(self, url: str) -> bool:
        ok, _ = await _run_subprocess(["cmd", "/c", "start", "", url])
        return ok

    async def open_app(self, name: str, args: list[str] | None = None) -> bool:
        cmd = ["cmd", "/c", "start", "", name]
        if args:
            cmd.extend(args)
        ok, err = await _run_subprocess(cmd)
        if not ok:
            logger.warning("open_app(%s) failed: %s", name, err)
        return ok

    async def get_browser_tabs(self) -> list[TabInfo]:
        # Windows tab enumeration requires browser-specific debug protocols.
        # Provide a basic implementation that returns empty when unavailable.
        logger.info("get_browser_tabs not fully implemented on Windows")
        return []

    async def close_browser_tab(self, match: str, all_matching: bool = False) -> int:
        logger.info("close_browser_tab not fully implemented on Windows")
        return 0

    async def run_system_command(self, action: str, value: Any = None) -> bool:
        action = action.lower().replace("-", "_")
        handlers: dict[str, Any] = {
            "volume_up": self._volume_up,
            "volume_down": self._volume_down,
            "volume_mute": self._volume_mute,
            "volume_set": self._volume_set,
            "dark_mode_on": self._dark_mode_on,
            "dark_mode_off": self._dark_mode_off,
            "lock_screen": self._lock_screen,
            "screenshot": self._screenshot,
            "empty_trash": self._empty_trash,
            "sleep": self._sleep,
            "brightness_up": self._brightness_up,
            "brightness_down": self._brightness_down,
        }
        handler = handlers.get(action)
        if handler is None:
            logger.warning("Unknown system command: %s", action)
            return False
        return await handler(value)

    async def _volume_up(self, _: Any) -> bool:
        script = (
            "$wshell = New-Object -ComObject WScript.Shell; "
            "1..5 | ForEach-Object { $wshell.SendKeys([char]175) }"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _volume_down(self, _: Any) -> bool:
        script = (
            "$wshell = New-Object -ComObject WScript.Shell; "
            "1..5 | ForEach-Object { $wshell.SendKeys([char]174) }"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _volume_mute(self, _: Any) -> bool:
        script = (
            "$wshell = New-Object -ComObject WScript.Shell; "
            "$wshell.SendKeys([char]173)"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _volume_set(self, value: Any) -> bool:
        # Requires nircmd or similar; approximate with key presses
        level = int(value) if value is not None else 50
        steps = level // 2  # each key press ~2%
        script = (
            "$wshell = New-Object -ComObject WScript.Shell; "
            f"1..50 | ForEach-Object {{ $wshell.SendKeys([char]174) }}; "
            f"1..{steps} | ForEach-Object {{ $wshell.SendKeys([char]175) }}"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _dark_mode_on(self, _: Any) -> bool:
        script = (
            "Set-ItemProperty -Path "
            "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' "
            "-Name AppsUseLightTheme -Value 0"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _dark_mode_off(self, _: Any) -> bool:
        script = (
            "Set-ItemProperty -Path "
            "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' "
            "-Name AppsUseLightTheme -Value 1"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _lock_screen(self, _: Any) -> bool:
        ok, _ = await _run_subprocess(["rundll32.exe", "user32.dll,LockWorkStation"])
        return ok

    async def _screenshot(self, _: Any) -> bool:
        ok, _ = await self._powershell("& snippingtool /clip")
        return ok

    async def _empty_trash(self, _: Any) -> bool:
        script = (
            "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _sleep(self, _: Any) -> bool:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _brightness_up(self, _: Any) -> bool:
        script = (
            "$brightness = (Get-WmiObject -Namespace root/WMI "
            "-Class WmiMonitorBrightness).CurrentBrightness; "
            "$new = [Math]::Min(100, $brightness + 10); "
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            ".WmiSetBrightness(1, $new)"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def _brightness_down(self, _: Any) -> bool:
        script = (
            "$brightness = (Get-WmiObject -Namespace root/WMI "
            "-Class WmiMonitorBrightness).CurrentBrightness; "
            "$new = [Math]::Max(0, $brightness - 10); "
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            ".WmiSetBrightness(1, $new)"
        )
        ok, _ = await self._powershell(script)
        return ok

    async def clipboard_read(self) -> str:
        ok, text = await self._powershell("Get-Clipboard")
        return text if ok else ""

    async def clipboard_write(self, text: str) -> bool:
        # Escape single quotes for PowerShell
        escaped = text.replace("'", "''")
        ok, _ = await self._powershell(f"Set-Clipboard -Value '{escaped}'")
        return ok


# ---------------------------------------------------------------------------
# Linux (basic stub)
# ---------------------------------------------------------------------------

class LinuxPlatform(Platform):
    """Linux implementation using xdg-open and xclip/xsel."""

    async def open_url(self, url: str) -> bool:
        ok, _ = await _run_subprocess(["xdg-open", url])
        return ok

    async def open_app(self, name: str, args: list[str] | None = None) -> bool:
        cmd = [name] + (args or [])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Don't wait for the process to finish; it's an app launch
            return True
        except Exception as exc:
            logger.warning("open_app(%s) failed: %s", name, exc)
            return False

    async def get_browser_tabs(self) -> list[TabInfo]:
        return []

    async def close_browser_tab(self, match: str, all_matching: bool = False) -> int:
        return 0

    async def run_system_command(self, action: str, value: Any = None) -> bool:
        logger.info("run_system_command not fully implemented on Linux")
        return False

    async def clipboard_read(self) -> str:
        ok, text = await _run_subprocess(["xclip", "-selection", "clipboard", "-o"])
        if ok:
            return text
        ok, text = await _run_subprocess(["xsel", "--clipboard", "--output"])
        return text if ok else ""

    async def clipboard_write(self, text: str) -> bool:
        ok, _ = await _run_subprocess(
            ["xclip", "-selection", "clipboard"],
            input_data=text,
        )
        return ok


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_platform() -> Platform:
    """Detect the current OS and return the appropriate Platform instance."""
    system = platform.system()
    if system == "Darwin":
        return MacOSPlatform()
    elif system == "Windows":
        return WindowsPlatform()
    else:
        return LinuxPlatform()
