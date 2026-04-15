"""
scheduler.py — APScheduler-based daily content scheduler.

Posts schedule (all times in your local timezone):
  08:00 — Daily Brief (AI news recap)
  12:00 — Learning Post (AI skill in 60s)
  18:00 — Differentiator (bold take / opinion)

Each run:
  1. Fetches latest AI news
  2. Generates post content via Claude
  3. Creates image via Canva
  4. Uploads image to Cloudinary
  5. Posts to X, LinkedIn, Instagram
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from utils.logger import get_logger

logger = get_logger("scheduler")


def build_scheduler(run_func, timezone: str = "Asia/Kolkata") -> BlockingScheduler:
    """
    Build and configure the APScheduler.

    Args:
        run_func: callable(post_type) — function to call for each post
        timezone: timezone string (e.g. "Asia/Kolkata", "America/New_York")
    """
    tz = pytz.timezone(timezone)
    scheduler = BlockingScheduler(timezone=tz)

    # 08:00 — Daily Brief
    scheduler.add_job(
        func=lambda: run_func("daily_brief"),
        trigger=CronTrigger(hour=8, minute=0, timezone=tz),
        id="daily_brief",
        name="AI Daily Brief",
        replace_existing=True,
    )

    # 12:00 — Learning Post
    scheduler.add_job(
        func=lambda: run_func("learning"),
        trigger=CronTrigger(hour=12, minute=0, timezone=tz),
        id="learning",
        name="Learning Post",
        replace_existing=True,
    )

    # 18:00 — Differentiator
    scheduler.add_job(
        func=lambda: run_func("differentiator"),
        trigger=CronTrigger(hour=18, minute=0, timezone=tz),
        id="differentiator",
        name="Differentiator Post",
        replace_existing=True,
    )

    return scheduler
