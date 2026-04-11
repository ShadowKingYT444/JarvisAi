"""News and current events tool using RSS feeds."""
import logging
from jarvis.shared.types import ToolResult

logger = logging.getLogger(__name__)

# Default RSS feeds by category
_RSS_FEEDS = {
    "top": "https://feeds.bbci.co.uk/news/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
    "entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
}


async def get_news(topic: str = "top", count: int = 5, **kwargs) -> ToolResult:
    """Get latest news headlines."""
    import asyncio
    import feedparser

    topic_lower = topic.lower().strip()
    feed_url = _RSS_FEEDS.get(topic_lower, _RSS_FEEDS["top"])

    try:
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

        if not feed.entries:
            return ToolResult(success=False, error="No news articles found.", display_text="No news found.")

        articles = []
        for entry in feed.entries[:count]:
            articles.append({
                "title": entry.get("title", "Untitled"),
                "summary": entry.get("summary", "")[:200],
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
            })

        headlines = "; ".join(a["title"] for a in articles[:3])
        display = f"Top {topic} headlines: {headlines}."

        return ToolResult(success=True, data=articles, display_text=display)
    except Exception as e:
        logger.exception("News fetch failed")
        return ToolResult(success=False, error=str(e), display_text="Failed to get news.")


def register(executor, platform, config):
    executor.register("get_news", get_news)
