"""Web search tool — Google Custom Search API, SerpAPI, or fallback.

Provides structured search results from multiple search providers.
"""

import logging
from typing import Any

import aiohttp

from jarvis.hands.platform import Platform
from jarvis.shared.config import JarvisConfig
from jarvis.shared.types import SearchResult, ToolResult

logger = logging.getLogger(__name__)


async def _google_cse_search(
    query: str,
    num_results: int,
    api_key: str,
    engine_id: str,
) -> list[SearchResult]:
    """Search using Google Custom Search Engine JSON API."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": engine_id,
        "q": query,
        "num": min(num_results, 10),
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Google CSE returned {resp.status}: {body[:200]}")
            data = await resp.json()

    results: list[SearchResult] = []
    for item in data.get("items", [])[:num_results]:
        results.append(SearchResult(
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
            url=item.get("link", ""),
            source="google_cse",
        ))
    return results


async def _serpapi_search(
    query: str,
    num_results: int,
    api_key: str,
) -> list[SearchResult]:
    """Search using SerpAPI."""
    url = "https://serpapi.com/search"
    params = {
        "api_key": api_key,
        "engine": "google",
        "q": query,
        "num": min(num_results, 10),
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"SerpAPI returned {resp.status}: {body[:200]}")
            data = await resp.json()

    results: list[SearchResult] = []
    for item in data.get("organic_results", [])[:num_results]:
        results.append(SearchResult(
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
            url=item.get("link", ""),
            source="serpapi",
        ))
    return results


def _fallback_search(query: str, num_results: int) -> list[SearchResult]:
    """Last-resort fallback using googlesearch-python (synchronous)."""
    try:
        from googlesearch import search as gsearch  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "No search API keys configured and googlesearch-python is not installed. "
            "Install it with: pip install googlesearch-python"
        )

    results: list[SearchResult] = []
    for url in gsearch(query, num_results=num_results, advanced=False):
        results.append(SearchResult(
            title="",
            snippet="",
            url=url,
            source="googlesearch_fallback",
        ))
    return results


async def web_search(
    query: str,
    num_results: int = 5,
    *,
    _config: JarvisConfig,
) -> ToolResult:
    """Execute a web search and return structured results.

    Args:
        query: The search query string.
        num_results: Number of results to return (max 10).
        _config: Injected JarvisConfig (set during registration).

    Returns:
        ToolResult with data=[SearchResult, ...].
    """
    num_results = max(1, min(int(num_results), 10))

    try:
        if _config.search_provider == "serpapi" and _config.search_api_key:
            results = await _serpapi_search(query, num_results, _config.search_api_key)
        elif _config.search_api_key and _config.search_engine_id:
            results = await _google_cse_search(
                query, num_results, _config.search_api_key, _config.search_engine_id,
            )
        else:
            # No API keys — try local fallback
            results = _fallback_search(query, num_results)
    except Exception as exc:
        logger.warning("Primary search failed (%s), trying fallback: %s", _config.search_provider, exc)
        try:
            results = _fallback_search(query, num_results)
        except Exception as fallback_exc:
            return ToolResult(
                success=False,
                error=str(fallback_exc),
                display_text=f"Search failed: {fallback_exc}",
            )

    summary_lines = [f"Found {len(results)} result(s) for '{query}':"]
    for i, r in enumerate(results, 1):
        title_part = f" — {r.title}" if r.title else ""
        summary_lines.append(f"  {i}. {r.url}{title_part}")

    return ToolResult(
        success=True,
        data=[r for r in results],
        display_text="\n".join(summary_lines),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(executor: Any, platform: Platform, config: JarvisConfig) -> None:
    """Register web_search tool with the executor."""
    from functools import partial

    bound = partial(web_search, _config=config)
    # Preserve the signature for introspection
    bound.__doc__ = web_search.__doc__
    executor.register("web_search", bound)
