"""Windows startup workflow for the first Jarvis initialization clap."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import yaml

from jarvis.shared.config import JarvisConfig
from jarvis.shared.windows_apps import find_chrome_path, find_obsidian_path, find_warp_path

logger = logging.getLogger(__name__)


def boot_greeting() -> str:
    import datetime

    hour = datetime.datetime.now().hour
    if hour < 12:
        greeting = "Good morning sir."
    elif hour < 17:
        greeting = "Good afternoon sir."
    else:
        greeting = "Good evening sir."
    return f"{greeting} Jarvis online. Opening your workspace now."


async def run_startup_sequence(config: JarvisConfig, state_mgr, speech_queue) -> None:
    """Run the one-time initialization workflow after the opening double clap."""
    await _show_phase(state_mgr, "Powering the arc reactor", 0.5)
    await _show_phase(state_mgr, "Bringing mission control online", 0.7)

    greeting = boot_greeting()
    await speech_queue.say(greeting)

    if config.startup_enabled:
        await _show_phase(state_mgr, "Opening Chrome, apps, and coding session", 0.2)
        await _launch_workspace(config)


async def _show_phase(state_mgr, text: str, delay_s: float) -> None:
    from jarvis.shared.types import JarvisState

    state_mgr.set_state(JarvisState.INITIALIZING, {"text": text})
    await asyncio.sleep(delay_s)


async def _launch_workspace(config: JarvisConfig) -> None:
    tasks = [_open_browser_workspace(config)]

    if config.startup_apps:
        tasks.append(_open_named_apps(config.startup_apps))
    if config.launch_warp_with_claude:
        tasks.append(_open_warp_claude_session(config))

    await asyncio.gather(*tasks, return_exceptions=True)


async def _open_browser_workspace(config: JarvisConfig) -> None:
    urls = [url for url in config.startup_urls if url.strip()]
    if not urls:
        return

    if config.startup_browser.lower() == "chrome":
        chrome_path = find_chrome_path()
        if chrome_path is not None:
            subprocess.Popen([str(chrome_path), "--new-window", *urls])
            return

    for url in urls:
        subprocess.Popen(["cmd", "/c", "start", "", url])


async def _open_named_apps(apps: list[str]) -> None:
    for app in apps:
        name = app.strip().lower()
        if not name:
            continue
        if name == "obsidian":
            obsidian_path = find_obsidian_path()
            if obsidian_path is not None:
                subprocess.Popen([str(obsidian_path)])
                continue
        subprocess.Popen(["cmd", "/c", "start", "", app])


async def _open_warp_claude_session(config: JarvisConfig) -> None:
    warp_path = find_warp_path()
    if warp_path is None:
        logger.warning("Warp executable not found; skipping Claude session launch")
        return

    project_dir = Path(config.startup_project_dir or ".").expanduser().resolve()
    if not project_dir.exists():
        logger.warning("Startup project directory does not exist: %s", project_dir)
        return

    claude_command = shutil.which(config.claude_command) or config.claude_command
    launch_config_dir = Path.home() / ".warp" / "launch_configurations"
    launch_config_dir.mkdir(parents=True, exist_ok=True)
    launch_config_path = launch_config_dir / "jarvis-claude.yaml"

    launch_config = {
        "name": "Jarvis Claude Workspace",
        "windows": [
            {
                "tabs": [
                    {
                        "title": "Claude Code",
                        "layout": {
                            "cwd": str(project_dir),
                            "commands": [
                                {"exec": str(claude_command)},
                            ],
                        },
                    }
                ]
            }
        ],
    }
    launch_config_path.write_text(yaml.safe_dump(launch_config, sort_keys=False), encoding="utf-8")

    uri = f"warp://launch/{quote(str(launch_config_path.resolve()), safe=':/\\\\')}"
    subprocess.Popen(["cmd", "/c", "start", "", uri])
