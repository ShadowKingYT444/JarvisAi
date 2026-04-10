"""Focus mode tool — deep work session manager.

Saves current tabs on start, periodically evaluates tab relevance using
Gemini, warns about distracting tabs, and optionally closes them.
Offers to restore closed tabs when focus mode ends.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.types import TabInfo, ToolResult

logger = logging.getLogger(__name__)

# Relevance threshold: tabs scoring above this are kept (0-10 scale)
RELEVANCE_THRESHOLD = 6

# Gemini evaluation prompt template
_EVAL_PROMPT = """You are a focus assistant helping someone stay on task.

The user's current goal is: "{goal}"

Here are their open browser tabs:
{tab_list}

For EACH tab, rate its relevance to the user's goal on a scale of 0-10:
- 0-3: Complete distraction (social media, entertainment, unrelated content)
- 4-6: Marginally related or neutral (might be useful later, but not for current task)
- 7-10: Directly relevant to the goal (documentation, research, tools for the task)

Respond with ONLY a JSON array containing an object for each tab:
[
  {{"id": 0, "score": 8, "reason": "React documentation directly supports learning goal"}},
  {{"id": 1, "score": 2, "reason": "Cat videos are entertainment, not related to React"}}
]

Output ONLY the JSON array, no markdown code blocks, no other text."""


@dataclass
class FocusSession:
    """State for an active focus session."""

    goal: str = ""
    strictness: str = "moderate"  # lenient | moderate | strict
    is_active: bool = False
    warned_tabs: dict[str, float] = field(default_factory=dict)  # url -> timestamp warned
    closed_tabs: list[dict[str, str]] = field(default_factory=list)  # [{title, url, browser}, ...]
    backup_tabs: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = 0.0
    _monitor_task: asyncio.Task | None = field(default=None, repr=False)


# Module-level session singleton
_session = FocusSession()


def _strictness_threshold(strictness: str) -> int:
    """Return relevance threshold based on strictness level."""
    return {"lenient": 4, "moderate": 6, "strict": 8}.get(strictness, RELEVANCE_THRESHOLD)


def _backup_path(config: JarvisConfig) -> Path:
    return Path(config.jarvis_home).expanduser() / "backups" / "session_backup.json"


async def _save_tab_backup(tabs: list[TabInfo], config: JarvisConfig) -> None:
    """Persist current tabs to disk for later restoration."""
    backup_file = _backup_path(config)
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {"title": t.title, "url": t.url, "browser": t.browser,
         "window_index": t.window_index, "tab_index": t.tab_index}
        for t in tabs
    ]
    backup_file.write_text(json.dumps(data, indent=2))
    logger.info("Saved %d tabs to %s", len(data), backup_file)


async def _evaluate_tabs_with_gemini(
    tabs: list[TabInfo],
    goal: str,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    """Call Gemini to evaluate tab relevance. Returns list of {id, score, reason}."""
    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError:
        logger.error("google-generativeai not installed; cannot evaluate tabs")
        return []

    if not api_key:
        logger.warning("No Gemini API key configured; skipping tab evaluation")
        return []

    tab_list = "\n".join(
        f"- Tab {i}: \"{t.title}\" ({t.url})"
        for i, t in enumerate(tabs)
    )
    prompt = _EVAL_PROMPT.format(goal=goal, tab_list=tab_list)

    genai.configure(api_key=api_key)
    model_obj = genai.GenerativeModel(model)

    try:
        response = await asyncio.to_thread(
            model_obj.generate_content,
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.1),
        )
        content = response.text.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = parsed.get("tabs") or parsed.get("evaluations") or list(parsed.values())[0]
        return parsed  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("Gemini tab evaluation failed: %s", exc)
        return []


async def _monitor_loop(platform: Platform, config: JarvisConfig) -> None:
    """Background loop that checks tabs periodically during focus mode."""
    global _session
    interval = config.focus_check_interval_s
    warn_delay = config.focus_warn_before_close_s
    threshold = _strictness_threshold(_session.strictness)

    while _session.is_active:
        await asyncio.sleep(interval)
        if not _session.is_active:
            break

        tabs = await platform.get_browser_tabs()
        if not tabs:
            continue

        evals = await _evaluate_tabs_with_gemini(
            tabs, _session.goal, config.gemini_api_key, config.gemini_model,
        )
        if not evals:
            continue

        # Map evaluation results back to tabs
        for ev in evals:
            tab_idx = ev.get("id", -1)
            score = ev.get("score", 10)
            if tab_idx < 0 or tab_idx >= len(tabs):
                continue

            tab = tabs[tab_idx]
            if score > threshold:
                # Relevant tab — clear any pending warning
                _session.warned_tabs.pop(tab.url, None)
                continue

            # Distracting tab
            now = time.time()
            warned_at = _session.warned_tabs.get(tab.url)

            if warned_at is None:
                # First offense: warn
                _session.warned_tabs[tab.url] = now
                logger.info(
                    "Focus warning: '%s' scored %d (threshold %d) — warned",
                    tab.title[:40], score, threshold,
                )
            elif now - warned_at >= warn_delay:
                # Already warned and grace period elapsed: close
                meta = {
                    "title": tab.title,
                    "url": tab.url,
                    "browser": tab.browser,
                }
                closed = await platform.close_browser_tab(tab.url, all_matching=False)
                if closed:
                    _session.closed_tabs.append(meta)
                    _session.warned_tabs.pop(tab.url, None)
                    logger.info("Focus mode closed distracting tab: %s", tab.title[:40])


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def focus_start(
    goal: str,
    strictness: str = "moderate",
    *,
    _platform: Platform,
    _config: JarvisConfig,
) -> ToolResult:
    """Start a focus session.

    Args:
        goal: What the user is working on (e.g. "Learning React Hooks").
        strictness: "lenient", "moderate", or "strict".
        _platform: Injected Platform.
        _config: Injected JarvisConfig.
    """
    global _session

    if _session.is_active:
        return ToolResult(
            success=False,
            error="Focus mode is already active",
            display_text=f"Focus mode is already running (goal: {_session.goal}).",
        )

    if strictness not in ("lenient", "moderate", "strict"):
        strictness = "moderate"

    # Save current tabs as backup
    tabs = await _platform.get_browser_tabs()
    await _save_tab_backup(tabs, _config)

    _session = FocusSession(
        goal=goal,
        strictness=strictness,
        is_active=True,
        started_at=time.time(),
        backup_tabs=[
            {"title": t.title, "url": t.url, "browser": t.browser,
             "window_index": t.window_index, "tab_index": t.tab_index}
            for t in tabs
        ],
    )

    # Start the monitoring loop
    _session._monitor_task = asyncio.ensure_future(_monitor_loop(_platform, _config))

    return ToolResult(
        success=True,
        data={"goal": goal, "strictness": strictness, "tabs_backed_up": len(tabs)},
        display_text=(
            f"Focus mode started. Goal: '{goal}' (strictness: {strictness}). "
            f"Backed up {len(tabs)} tabs. Monitoring every {_config.focus_check_interval_s}s."
        ),
    )


async def focus_stop(
    restore_tabs: bool = False,
    *,
    _platform: Platform,
    _config: JarvisConfig,
) -> ToolResult:
    """Stop the current focus session.

    Args:
        restore_tabs: If True, re-open tabs that were closed during the session.
        _platform: Injected Platform.
        _config: Injected JarvisConfig.
    """
    global _session

    if not _session.is_active:
        return ToolResult(
            success=False,
            error="No active focus session",
            display_text="Focus mode is not running.",
        )

    _session.is_active = False
    if _session._monitor_task and not _session._monitor_task.done():
        _session._monitor_task.cancel()
        try:
            await _session._monitor_task
        except asyncio.CancelledError:
            pass

    duration = time.time() - _session.started_at
    minutes = int(duration // 60)
    closed_count = len(_session.closed_tabs)

    restored = 0
    if restore_tabs and _session.closed_tabs:
        for tab_meta in _session.closed_tabs:
            ok = await _platform.open_url(tab_meta["url"])
            if ok:
                restored += 1

    result_data = {
        "duration_minutes": minutes,
        "closed_tabs": closed_count,
        "restored_tabs": restored,
        "goal": _session.goal,
    }

    display = f"Focus mode ended after {minutes}m. Closed {closed_count} distracting tab(s)."
    if restored:
        display += f" Restored {restored} tab(s)."

    # Reset session
    _session = FocusSession()

    return ToolResult(success=True, data=result_data, display_text=display)


async def focus_status(
    *,
    _platform: Platform,
    _config: JarvisConfig,
) -> ToolResult:
    """Get the current focus mode status.

    Returns information about the active session or indicates idle.
    """
    if not _session.is_active:
        return ToolResult(
            success=True,
            data={"is_active": False},
            display_text="Focus mode is not active.",
        )

    duration = time.time() - _session.started_at
    minutes = int(duration // 60)

    return ToolResult(
        success=True,
        data={
            "is_active": True,
            "goal": _session.goal,
            "strictness": _session.strictness,
            "duration_minutes": minutes,
            "warned_tabs": len(_session.warned_tabs),
            "closed_tabs": len(_session.closed_tabs),
        },
        display_text=(
            f"Focus mode active for {minutes}m. Goal: '{_session.goal}' "
            f"({_session.strictness}). "
            f"Warned: {len(_session.warned_tabs)}, Closed: {len(_session.closed_tabs)}."
        ),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(executor: Any, platform: Platform, config: JarvisConfig) -> None:
    """Register focus mode tools with the executor."""
    from functools import partial

    executor.register("focus_start", partial(focus_start, _platform=platform, _config=config))
    executor.register("focus_stop", partial(focus_stop, _platform=platform, _config=config))
    executor.register("focus_status", partial(focus_status, _platform=platform, _config=config))
