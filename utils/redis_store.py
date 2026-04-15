"""
redis_store.py — Persistent storage using Upstash Redis.
Replaces local JSON files for seen_articles, posted_topics,
daily_count, and content_strategy. Survives Railway redeploys.
"""

import os
import json
from datetime import date
from upstash_redis import Redis
from utils.logger import get_logger

logger = get_logger("redis_store")

_redis = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        url = os.environ.get("UPSTASH_REDIS_REST_URL", "")
        token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
        if not url or not token:
            raise EnvironmentError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must be set.")
        _redis = Redis(url=url, token=token)
    return _redis


# ─── Seen Articles ───────────────────────────────────────

def is_article_seen(key: str) -> bool:
    try:
        return bool(get_redis().sismember("seen_articles", key))
    except Exception as e:
        logger.warning(f"Redis seen_articles check failed: {e}")
        return False


def mark_article_seen(key: str):
    try:
        r = get_redis()
        r.sadd("seen_articles", key)
        # Keep set from growing forever — trim to last 500
        size = r.scard("seen_articles")
        if size and size > 500:
            members = r.smembers("seen_articles")
            if members:
                to_remove = list(members)[:len(members) - 500]
                if to_remove:
                    r.srem("seen_articles", *to_remove)
    except Exception as e:
        logger.warning(f"Redis mark_seen failed: {e}")


# ─── Posted Topics ───────────────────────────────────────

def get_posted_topics() -> list[str]:
    try:
        data = get_redis().get("posted_topics")
        if data:
            return json.loads(data)[-50:]
        return []
    except Exception as e:
        logger.warning(f"Redis get_posted_topics failed: {e}")
        return []


def save_posted_topic(topic: str):
    try:
        topics = get_posted_topics()
        topics.append(topic.lower())
        topics = topics[-50:]
        get_redis().set("posted_topics", json.dumps(topics))
    except Exception as e:
        logger.warning(f"Redis save_posted_topic failed: {e}")


# ─── Daily Post Count ────────────────────────────────────

def get_today_count() -> int:
    try:
        key = f"daily_count:{date.today()}"
        val = get_redis().get(key)
        return int(val) if val else 0
    except Exception as e:
        logger.warning(f"Redis get_today_count failed: {e}")
        return 0


def increment_today_count():
    try:
        key = f"daily_count:{date.today()}"
        get_redis().incr(key)
        get_redis().expire(key, 86400 * 2)  # Expire after 2 days
    except Exception as e:
        logger.warning(f"Redis increment_today_count failed: {e}")


# ─── Content Strategy ────────────────────────────────────

def get_strategy() -> dict:
    try:
        data = get_redis().get("content_strategy")
        if data:
            return json.loads(data)
        return {}
    except Exception as e:
        logger.warning(f"Redis get_strategy failed: {e}")
        return {}


def save_strategy(strategy: dict):
    try:
        get_redis().set("content_strategy", json.dumps(strategy))
    except Exception as e:
        logger.warning(f"Redis save_strategy failed: {e}")
