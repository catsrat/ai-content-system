"""
scheduler.py — News-triggered content scheduler.

Instead of fixed times, checks for new AI news every 30 minutes.
When a new significant article is found, generates and posts content immediately.

Limits:
  - Max 5 posts/day (to stay within X free tier)
  - Rotates post types: daily_brief → learning → differentiator → repeat
  - Skips if article topic was already posted recently
"""

import json
import os
from datetime import datetime, date
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz
from utils.logger import get_logger

logger = get_logger("scheduler")

MAX_POSTS_PER_DAY = 5
SEEN_ARTICLES_LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "seen_articles.json")
DAILY_COUNT_LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "daily_count.json")

os.makedirs(os.path.join(os.path.dirname(__file__), "..", "logs"), exist_ok=True)

# Rotate through post types
POST_TYPE_ROTATION = ["daily_brief", "learning", "differentiator"]


def _load_seen_articles() -> set:
    if os.path.exists(SEEN_ARTICLES_LOG):
        try:
            with open(SEEN_ARTICLES_LOG) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def _save_seen_article(article_key: str):
    seen = _load_seen_articles()
    seen.add(article_key)
    # Keep last 200
    seen_list = list(seen)[-200:]
    with open(SEEN_ARTICLES_LOG, "w") as f:
        json.dump(seen_list, f)


def _get_today_count() -> int:
    if os.path.exists(DAILY_COUNT_LOG):
        try:
            with open(DAILY_COUNT_LOG) as f:
                data = json.load(f)
                if data.get("date") == str(date.today()):
                    return data.get("count", 0)
        except Exception:
            pass
    return 0


def _increment_today_count():
    count = _get_today_count() + 1
    with open(DAILY_COUNT_LOG, "w") as f:
        json.dump({"date": str(date.today()), "count": count}, f)


def _get_next_post_type() -> str:
    count = _get_today_count()
    return POST_TYPE_ROTATION[count % len(POST_TYPE_ROTATION)]


def build_news_triggered_scheduler(fetch_func, run_func, timezone: str = "Asia/Kolkata") -> BlockingScheduler:
    """
    Build a news-triggered scheduler that checks every 30 minutes.

    Args:
        fetch_func: callable() → list of articles
        run_func: callable(post_type) — function to post content
        timezone: timezone string
    """
    tz = pytz.timezone(timezone)
    scheduler = BlockingScheduler(timezone=tz)

    def check_and_post():
        today_count = _get_today_count()
        if today_count >= MAX_POSTS_PER_DAY:
            logger.info(f"Daily limit reached ({MAX_POSTS_PER_DAY} posts). Skipping until tomorrow.")
            return

        logger.info("Checking for new AI news...")
        articles = fetch_func()
        if not articles:
            logger.info("No articles found.")
            return

        seen = _load_seen_articles()

        # Find first unseen article
        new_article = None
        for article in articles:
            key = article["title"].lower()[:80]
            if key not in seen:
                new_article = article
                break

        if not new_article:
            logger.info("No new articles since last check. Skipping.")
            return

        # Mark as seen
        _save_seen_article(new_article["title"].lower()[:80])

        post_type = _get_next_post_type()
        logger.info(f"New article found: '{new_article['title'][:60]}' → posting as [{post_type}]")

        try:
            run_func(post_type)
            _increment_today_count()
            new_count = _get_today_count()
            logger.info(f"Posted successfully. Today's count: {new_count}/{MAX_POSTS_PER_DAY}")
        except Exception as e:
            logger.error(f"Post failed: {e}")

    scheduler.add_job(
        func=check_and_post,
        trigger=IntervalTrigger(minutes=30, timezone=tz),
        id="news_watcher",
        name="News Watcher",
        replace_existing=True,
        next_run_time=datetime.now(tz),  # Run immediately on start
    )

    return scheduler


# Keep old fixed scheduler as fallback
def build_scheduler(run_func, timezone: str = "Asia/Kolkata") -> BlockingScheduler:
    from apscheduler.triggers.cron import CronTrigger
    tz = pytz.timezone(timezone)
    scheduler = BlockingScheduler(timezone=tz)

    scheduler.add_job(
        func=lambda: run_func("daily_brief"),
        trigger=CronTrigger(hour=8, minute=0, timezone=tz),
        id="daily_brief",
        name="AI Daily Brief",
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: run_func("learning"),
        trigger=CronTrigger(hour=12, minute=0, timezone=tz),
        id="learning",
        name="Learning Post",
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: run_func("differentiator"),
        trigger=CronTrigger(hour=18, minute=0, timezone=tz),
        id="differentiator",
        name="Differentiator Post",
        replace_existing=True,
    )
    return scheduler
