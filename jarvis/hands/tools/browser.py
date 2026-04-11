"""Browser control tools — open/close/list tabs and combo search-and-display.

Delegates all actual browser interaction to the Platform abstraction.
"""

import logging
from typing import Any

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)


async def open_tabs(
    urls: list[str] | str,
    focus: bool = True,
    *,
    _platform: Platform,
) -> ToolResult:
    """Open one or more URLs in the browser.

    Args:
        urls: A single URL string or a list of URLs.
        focus: Whether to bring the browser to the foreground.
        _platform: Injected Platform instance.
    """
    if isinstance(urls, str):
        urls = [urls]

    opened: list[str] = []
    failed: list[str] = []
    for url in urls:
        ok = await _platform.open_url(url)
        if ok:
            opened.append(url)
        else:
            failed.append(url)

    if not opened:
        return ToolResult(
            success=False,
            error=f"Failed to open any URLs: {failed}",
            display_text="Could not open the requested URLs.",
        )

    display = f"Opened {len(opened)} tab(s)."
    if failed:
        display += f" Failed to open {len(failed)}: {', '.join(failed)}"

    return ToolResult(success=True, data={"opened": opened, "failed": failed}, display_text=display)


async def close_tab(
    match: str,
    all_matching: bool = False,
    *,
    _platform: Platform,
) -> ToolResult:
    """Close browser tab(s) matching a title/URL substring.

    Args:
        match: Substring to match against tab titles and URLs.
        all_matching: If True, close all matching tabs; otherwise just the first.
        _platform: Injected Platform instance.
    """
    closed = await _platform.close_browser_tab(match, all_matching=all_matching)
    if closed == 0:
        return ToolResult(
            success=True,
            data={"closed": 0},
            display_text=f"No tabs matched '{match}'.",
        )
    return ToolResult(
        success=True,
        data={"closed": closed},
        display_text=f"Closed {closed} tab(s) matching '{match}'.",
    )


async def get_active_tabs(*, _platform: Platform) -> ToolResult:
    """Return a list of all open browser tabs.

    Returns:
        ToolResult with data=list[TabInfo].
    """
    tabs = await _platform.get_browser_tabs()
    lines = [f"Found {len(tabs)} open tab(s):"]
    for i, tab in enumerate(tabs, 1):
        lines.append(f"  {i}. [{tab.browser}] {tab.title} — {tab.url}")

    return ToolResult(
        success=True,
        data=tabs,
        display_text="\n".join(lines) if tabs else "No open browser tabs found.",
    )


async def google_search_and_display(
    query: str,
    num_tabs: int = 3,
    *,
    _platform: Platform,
    _executor: Any,
) -> ToolResult:
    """Combo: run a web search, then open the top results as browser tabs.

    Args:
        query: The search query.
        num_tabs: How many top results to open (default 3).
        _platform: Injected Platform instance.
        _executor: The ToolExecutor (used to call web_search).
    """
    search_result = await _executor.execute("web_search", {"query": query, "num_results": num_tabs})
    if not search_result.success:
        return ToolResult(
            success=False,
            error=search_result.error,
            display_text=f"Search failed: {search_result.error}",
        )

    search_items = search_result.data or []
    urls = [item.url for item in search_items[:num_tabs]]
    if not urls:
        return ToolResult(
            success=True,
            data={"opened": [], "search_results": []},
            display_text=f"No results found for '{query}'.",
        )

    open_result = await open_tabs(urls, focus=True, _platform=_platform)

    return ToolResult(
        success=open_result.success,
        data={"opened": open_result.data, "search_results": search_items},
        display_text=f"Searched for '{query}' and opened {len(urls)} tab(s).",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(executor: Any, platform: Platform, config: JarvisConfig) -> None:
    """Register browser tools with the executor."""
    from functools import partial

    open_tabs_handler = partial(open_tabs, _platform=platform)
    close_tab_handler = partial(close_tab, _platform=platform)
    get_tabs_handler = partial(get_active_tabs, _platform=platform)

    executor.register("open_tabs", open_tabs_handler)
    executor.register("open_browser_tabs", open_tabs_handler)
    executor.register("close_tab", close_tab_handler)
    executor.register("close_browser_tab", close_tab_handler)
    executor.register("get_active_tabs", get_tabs_handler)
    executor.register(
        "google_search_and_display",
        partial(google_search_and_display, _platform=platform, _executor=executor),
    )
