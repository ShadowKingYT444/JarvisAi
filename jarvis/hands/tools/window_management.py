"""Window management tool — minimize, switch, snap, list windows."""
import asyncio
import logging
from typing import Any
from jarvis.shared.types import ToolResult
from jarvis.hands.platform import Platform, _run_subprocess
logger = logging.getLogger(__name__)

async def minimize_all_windows(_platform: Platform = None, **kwargs) -> ToolResult:
    """Minimize all open windows (show desktop)."""
    import sys
    if sys.platform == "win32":
        ok, _ = await _run_subprocess(
            ["powershell", "-NoProfile", "-Command",
             '(New-Object -ComObject Shell.Application).MinimizeAll()'],
        )
        return ToolResult(success=ok, display_text="All windows minimized." if ok else "Failed to minimize windows.")
    elif sys.platform == "darwin":
        from jarvis.hands.platform import _run_applescript
        ok, _ = await _run_applescript(
            'tell application "System Events" to key code 103 using {command down, option down}'
        )
        return ToolResult(success=ok, display_text="All windows minimized." if ok else "Failed.")
    return ToolResult(success=False, error="Not supported on this platform.")

async def switch_to_app(app_name: str, _platform: Platform = None, **kwargs) -> ToolResult:
    """Switch to a running application by name."""
    import re
    import sys
    if sys.platform == "win32":
        # Sanitize app_name to prevent PowerShell injection
        safe_name = re.sub(r'[^a-zA-Z0-9 _\-.]', '', app_name)
        script = f'''
$proc = Get-Process | Where-Object {{$_.MainWindowTitle -like "*{safe_name}*"}} | Select-Object -First 1
if ($proc) {{
    $sig = '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);'
    Add-Type -MemberDefinition $sig -Name NativeMethods -Namespace Win32
    [Win32.NativeMethods]::SetForegroundWindow($proc.MainWindowHandle)
    "Switched to $($proc.ProcessName)"
}} else {{
    "NOT_FOUND"
}}
'''
        ok, output = await _run_subprocess(
            ["powershell", "-NoProfile", "-Command", script],
        )
        if "NOT_FOUND" in output:
            return ToolResult(success=False, error=f"No window found matching '{app_name}'.")
        return ToolResult(success=ok, display_text=f"Switched to {app_name}.")
    return ToolResult(success=False, error="Not supported on this platform.")

async def list_open_windows(_platform: Platform = None, **kwargs) -> ToolResult:
    """List all open windows with titles."""
    import sys
    if sys.platform == "win32":
        script = 'Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object ProcessName, MainWindowTitle | ConvertTo-Json'
        ok, output = await _run_subprocess(
            ["powershell", "-NoProfile", "-Command", script],
        )
        if ok:
            import json
            try:
                windows = json.loads(output)
                if isinstance(windows, dict):
                    windows = [windows]
                data = [{"app": w.get("ProcessName", ""), "title": w.get("MainWindowTitle", "")} for w in windows]
                titles = [w["title"][:40] for w in data[:10]]
                return ToolResult(success=True, data=data, display_text=f"{len(data)} windows open: {'; '.join(titles)}")
            except json.JSONDecodeError:
                pass
    return ToolResult(success=False, error="Could not list windows.")

def register(executor, platform, config):
    from functools import partial
    executor.register("minimize_all_windows", partial(minimize_all_windows, _platform=platform))
    executor.register("switch_to_app", partial(switch_to_app, _platform=platform))
    executor.register("list_open_windows", partial(list_open_windows, _platform=platform))
