"""
scheduler.py — News-triggered content scheduler.

Instead of fixed times, checks for new AI news every 30 minutes.
When a new significant article is found, generates and posts content immediately.

Limits:
  - Max 5 posts/day (to stay within X free tier)
  - Rotates post types: daily_brief → learning → differentiator → repeat
  - Skips if article topic was already posted recently
"""

from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz
from utils.logger import get_logger
from utils.redis_store import (
    is_article_seen, mark_article_seen,
    get_today_count, increment_today_count,
)

logger = get_logger("scheduler")

MAX_POSTS_PER_DAY = 5
POST_TYPE_ROTATION = ["daily_brief", "workflow", "learning", "differentiator", "workflow"]


def _get_next_post_type() -> str:
    count = get_today_count()
    return POST_TYPE_ROTATION[count % len(POST_TYPE_ROTATION)]


def build_news_triggered_scheduler(fetch_func, run_func, timezone: str = "Asia/Kolkata") -> BlockingScheduler:
    """
    Build a news-triggered scheduler:
    - Checks for new AI news every 10 minutes → posts news content
    - Posts a workflow post every 4 hours regardless of news
    """
    tz = pytz.timezone(timezone)
    scheduler = BlockingScheduler(timezone=tz)

    NEWS_POST_TYPES = ["daily_brief", "learning", "differentiator"]

    def check_and_post_news():
        today_count = get_today_count()
        if today_count >= MAX_POSTS_PER_DAY:
            logger.info(f"Daily limit reached ({MAX_POSTS_PER_DAY} posts). Skipping.")
            return

        logger.info("Checking for new AI news...")
        articles = fetch_func()
        if not articles:
            logger.info("No articles found.")
            return

        # Find first unseen article
        new_article = None
        for article in articles:
            key = article["title"].lower()[:80]
            if not is_article_seen(key):
                new_article = article
                break

        if not new_article:
            logger.info("No new articles since last check. Skipping.")
            return

        # Mark as seen BEFORE posting
        mark_article_seen(new_article["title"].lower()[:80])

        count = get_today_count()
        post_type = NEWS_POST_TYPES[count % len(NEWS_POST_TYPES)]
        logger.info(f"New article: '{new_article['title'][:60]}' → [{post_type}]")

        try:
            run_func(post_type)
            increment_today_count()
            logger.info(f"Posted. Today: {get_today_count()}/{MAX_POSTS_PER_DAY}")
        except Exception as e:
            logger.error(f"Post failed: {e}")

    def post_workflow():
        today_count = get_today_count()
        if today_count >= MAX_POSTS_PER_DAY:
            logger.info(f"Daily limit reached. Skipping workflow post.")
            return
        logger.info("Posting scheduled workflow content...")
        try:
            run_func("workflow")
            increment_today_count()
            logger.info(f"Workflow posted. Today: {get_today_count()}/{MAX_POSTS_PER_DAY}")
        except Exception as e:
            logger.error(f"Workflow post failed: {e}")

    # News-triggered: every 10 minutes
    scheduler.add_job(
        func=check_and_post_news,
        trigger=IntervalTrigger(minutes=10, timezone=tz),
        id="news_watcher",
        name="News Watcher",
        replace_existing=True,
        next_run_time=datetime.now(tz),
    )

    # Workflow post: every 4 hours regardless of news
    scheduler.add_job(
        func=post_workflow,
        trigger=IntervalTrigger(hours=4, timezone=tz),
        id="workflow_poster",
        name="Workflow Poster",
        replace_existing=True,
        next_run_time=datetime.now(tz),
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
