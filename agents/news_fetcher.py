"""
news_fetcher.py — Pulls the latest AI news from RSS feeds and NewsAPI.
Returns a list of article dicts: {title, summary, url, source, published_at}
"""

import feedparser
import requests
from datetime import datetime, timedelta

from utils.logger import get_logger

logger = get_logger("news_fetcher")

# Top AI/Tech RSS feeds
RSS_FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ("Wired AI", "https://www.wired.com/feed/category/artificial-intelligence/latest/rss"),
    ("AI News", "https://artificialintelligence-news.com/feed/"),
    ("ZDNet AI", "https://www.zdnet.com/topic/artificial-intelligence/rss.xml"),
    ("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("The Register AI", "https://www.theregister.com/emergent_tech/AI/headlines.atom"),
    ("InfoQ AI", "https://feed.infoq.com/"),
    ("Analytics Vidhya", "https://www.analyticsvidhya.com/feed/"),
    ("Towards Data Science", "https://towardsdatascience.com/feed"),
]


def fetch_rss_articles(max_per_feed: int = 3) -> list[dict]:
    """Fetch latest articles from all RSS feeds."""
    articles = []
    cutoff = datetime.utcnow() - timedelta(hours=24)

    for source_name, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                # Parse published date if available
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6])
                    except Exception:
                        published = None

                # Skip articles older than 24 hours if date is available
                if published and published < cutoff:
                    continue

                summary = ""
                if hasattr(entry, "summary"):
                    summary = entry.summary[:500]
                elif hasattr(entry, "description"):
                    summary = entry.description[:500]

                # Try to extract image from entry
                image_url = ""
                if hasattr(entry, "media_content") and entry.media_content:
                    image_url = entry.media_content[0].get("url", "")
                elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                    image_url = entry.media_thumbnail[0].get("url", "")
                elif hasattr(entry, "links"):
                    for link in entry.links:
                        if link.get("type", "").startswith("image"):
                            image_url = link.get("href", "")
                            break

                articles.append({
                    "title": entry.get("title", "").strip(),
                    "summary": summary.strip(),
                    "url": entry.get("link", ""),
                    "source": source_name,
                    "published_at": published.isoformat() if published else "",
                    "image_url": image_url,
                })
                count += 1

            logger.info(f"RSS [{source_name}]: fetched {count} articles")
        except Exception as e:
            logger.warning(f"RSS [{source_name}] failed: {e}")

    return articles


def fetch_newsapi_articles(api_key: str, max_articles: int = 10) -> list[dict]:
    """Fetch AI news from NewsAPI."""
    if not api_key:
        return []

    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "artificial intelligence OR AI tools OR machine learning",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": max_articles,
            "from": (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"),
            "apiKey": api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title": (a.get("title") or "").strip(),
                "summary": (a.get("description") or "")[:500].strip(),
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "published_at": a.get("publishedAt", ""),
            })

        logger.info(f"NewsAPI: fetched {len(articles)} articles")
        return articles
    except Exception as e:
        logger.warning(f"NewsAPI failed: {e}")
        return []


def fetch_all_news(news_api_key: str = "") -> list[dict]:
    """
    Fetch news from all sources, deduplicate by title, and return
    sorted by recency. Returns top 15 most relevant articles.
    """
    rss_articles = fetch_rss_articles(max_per_feed=5)
    api_articles = fetch_newsapi_articles(api_key=news_api_key, max_articles=20)

    all_articles = rss_articles + api_articles

    # Deduplicate by title similarity (simple lower-case match)
    seen_titles: set[str] = set()
    unique = []
    for article in all_articles:
        key = article["title"].lower()[:60]
        if key and key not in seen_titles:
            seen_titles.add(key)
            unique.append(article)

    # Filter out articles with no title or summary
    unique = [a for a in unique if a["title"] and (a["summary"] or a["url"])]

    logger.info(f"Total unique articles fetched: {len(unique)}")
    return unique[:80]
