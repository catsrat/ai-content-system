"""
workflow_fetcher.py — Fetches real AI tool workflows and use cases
from free sources: Reddit, Product Hunt, RSS feeds.
No API key needed.
"""

import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger("workflow_fetcher")

# RSS feeds focused on AI tools and workflows
WORKFLOW_FEEDS = [
    ("Reddit r/ChatGPT", "https://www.reddit.com/r/ChatGPT/top/.rss?t=day"),
    ("Reddit r/ClaudeAI", "https://www.reddit.com/r/ClaudeAI/top/.rss?t=day"),
    ("Reddit r/AITools", "https://www.reddit.com/r/aitools/top/.rss?t=day"),
    ("Reddit r/PromptEngineering", "https://www.reddit.com/r/PromptEngineering/top/.rss?t=day"),
    ("Product Hunt AI", "https://www.producthunt.com/feed?category=artificial-intelligence"),
    ("Futurepedia", "https://www.futurepedia.io/rss"),
]

# Keywords that indicate a workflow/tutorial post
WORKFLOW_KEYWORDS = [
    "how to use", "free", "workflow", "prompt", "automate", "replace",
    "tutorial", "guide", "trick", "hack", "tip", "secret", "hidden",
    "you didn't know", "for free", "without paying", "instead of",
    "chatgpt", "claude", "gemini", "midjourney", "copilot", "perplexity",
    "ai tool", "productivity", "save time", "save money",
]


def fetch_workflow_ideas(max_results: int = 10) -> list[dict]:
    """
    Fetch real AI workflow ideas from Reddit and AI tool sites.
    Returns list of {title, summary, source, url}
    """
    ideas = []
    seen = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AIContentBot/1.0)"
    }

    for source_name, feed_url in WORKFLOW_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0

            for entry in feed.entries:
                if count >= 3:
                    break

                title = entry.get("title", "").strip()
                if not title:
                    continue

                # Check if it's workflow-relevant
                title_lower = title.lower()
                if not any(kw in title_lower for kw in WORKFLOW_KEYWORDS):
                    continue

                # Dedup
                key = title.lower()[:60]
                if key in seen:
                    continue
                seen.add(key)

                summary = ""
                if hasattr(entry, "summary"):
                    # Strip HTML tags
                    soup = BeautifulSoup(entry.summary, "html.parser")
                    summary = soup.get_text()[:400].strip()

                ideas.append({
                    "title": title,
                    "summary": summary,
                    "source": source_name,
                    "url": entry.get("link", ""),
                })
                count += 1

            logger.info(f"[{source_name}]: found {count} workflow ideas")

        except Exception as e:
            logger.warning(f"[{source_name}] failed: {e}")

    # Also add curated AI tool categories for Claude to expand on
    curated_topics = [
        {
            "title": "Use Claude for free to write professional emails in seconds",
            "summary": "Claude's free tier can draft, rewrite and improve any email. Most people don't know you can use it without an account via Claude.ai",
            "source": "curated",
            "url": "",
        },
        {
            "title": "Use ChatGPT to automate your weekly report in 2 minutes",
            "summary": "Paste your raw data and let ChatGPT format it into a professional report with insights",
            "source": "curated",
            "url": "",
        },
        {
            "title": "Use Gemini for free to summarize any YouTube video",
            "summary": "Gemini can read YouTube URLs and give you a full summary with key points",
            "source": "curated",
            "url": "",
        },
        {
            "title": "Use NotebookLM to turn any PDF into a podcast for free",
            "summary": "Google's NotebookLM generates audio overviews from any document — completely free",
            "source": "curated",
            "url": "",
        },
        {
            "title": "Use Claude to replace your $20/month Grammarly subscription",
            "summary": "Claude rewrites, proofreads and improves writing better than Grammarly — and it's free",
            "source": "curated",
            "url": "",
        },
        {
            "title": "Use ChatGPT to build a full Excel formula without knowing Excel",
            "summary": "Describe what you want in plain English, ChatGPT gives you the exact formula",
            "source": "curated",
            "url": "",
        },
        {
            "title": "Use Perplexity for free to research any topic like a PhD student",
            "summary": "Perplexity cites sources and gives deep research answers — free tier is very generous",
            "source": "curated",
            "url": "",
        },
        {
            "title": "Use Claude to prepare for any job interview in 30 minutes",
            "summary": "Paste the job description and ask Claude to generate likely interview questions and model answers",
            "source": "curated",
            "url": "",
        },
    ]

    # Mix curated with fetched
    all_ideas = ideas + curated_topics

    # Shuffle to vary order
    import random
    random.shuffle(all_ideas)

    logger.info(f"Total workflow ideas: {len(all_ideas)}")
    return all_ideas[:max_results]
