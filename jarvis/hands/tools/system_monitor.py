"""System monitoring tool — CPU, RAM, disk, battery, processes."""

import asyncio
import logging
import os
from pathlib import Path

from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)


async def get_system_stats(**kwargs) -> ToolResult:
    """Get current system resource usage."""
    import psutil

    loop = asyncio.get_event_loop()

    # cpu_percent(interval=1) blocks for 1 second — run in executor
    cpu = await loop.run_in_executor(
        None, lambda: psutil.cpu_percent(interval=1)
    )
    mem = psutil.virtual_memory()

    # Use the system drive root for disk usage (portable across drives)
    disk_path = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    disk = psutil.disk_usage(disk_path)
    battery = psutil.sensors_battery()

    stats = {
        "cpu_percent": cpu,
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "ram_percent": mem.percent,
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_percent": disk.percent,
    }
    display = (
        f"CPU: {cpu}%. "
        f"RAM: {mem.percent}% ({stats['ram_used_gb']}/{stats['ram_total_gb']} GB). "
        f"Disk: {disk.percent}%."
    )

    if battery:
        stats["battery_percent"] = battery.percent
        stats["battery_plugged"] = battery.power_plugged
        plugged = "plugged in" if battery.power_plugged else "on battery"
        display += f" Battery: {battery.percent}% ({plugged})."

    return ToolResult(success=True, data=stats, display_text=display)


async def list_running_apps(**kwargs) -> ToolResult:
    """List notable running applications."""
    import psutil

    # System process names to exclude
    _SYSTEM_PROCS = frozenset({
        "svchost", "System", "Registry", "csrss", "conhost",
        "RuntimeBroker", "dwm", "smss", "lsass", "services",
        "wininit", "winlogon", "fontdrvhost", "sihost",
        "taskhostw", "ctfmon", "dllhost", "WmiPrvSE",
    })

    apps = set()
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            name = proc.info["name"]
            if name and name not in _SYSTEM_PROCS:
                apps.add(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    app_list = sorted(apps)[:30]
    return ToolResult(
        success=True,
        data=app_list,
        display_text=f"{len(app_list)} apps running: {', '.join(app_list[:10])}...",
    )


async def kill_app(app_name: str, **kwargs) -> ToolResult:
    """Kill a running application by name."""
    import psutil

    killed = 0
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if proc.info["name"] and app_name.lower() in proc.info["name"].lower():
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        return ToolResult(
            success=True,
            data={"killed": killed},
            display_text=f"Terminated {killed} process(es) matching '{app_name}'.",
        )
    return ToolResult(
        success=False,
        error=f"No process found matching '{app_name}'.",
        display_text=f"Could not find '{app_name}'.",
    )


def register(executor, platform, config):
    executor.register("get_system_stats", get_system_stats)
    executor.register("list_running_apps", list_running_apps)
    executor.register("kill_app", kill_app)
