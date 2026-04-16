"""
instagram_token_manager.py — Manages Instagram access token lifecycle.

- On first run: exchanges short-lived token for 60-day long-lived token
- Stores long-lived token in Redis so it survives Railway redeploys
- Auto-refreshes every 50 days (before the 60-day expiry)
- Falls back to INSTAGRAM_ACCESS_TOKEN env var if Redis unavailable
"""

import os
import requests
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger("instagram_token")

GRAPH_API = "https://graph.facebook.com/v18.0"
REDIS_KEY_TOKEN = "instagram:access_token"
REDIS_KEY_EXPIRY = "instagram:token_expiry"


def _get_redis():
    try:
        from utils.redis_store import get_redis
        return get_redis()
    except Exception:
        return None


def exchange_for_long_lived(short_token: str, app_id: str, app_secret: str) -> str:
    """Exchange a short-lived token for a 60-day long-lived token."""
    resp = requests.get(
        f"{GRAPH_API}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Token exchange failed: {resp.text}")
    data = resp.json()
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError(f"No access_token in response: {data}")
    return token


def get_page_access_token(user_token: str, page_id: str) -> str:
    """
    Get a Page Access Token from a long-lived user token.
    Page tokens from long-lived user tokens never expire.
    """
    resp = requests.get(
        f"{GRAPH_API}/me/accounts",
        params={"access_token": user_token},
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Failed to get page token: {resp.text}")
    accounts = resp.json().get("data", [])
    for account in accounts:
        # Match by page ID or just return the first Instagram-connected page
        page_token = account.get("access_token", "")
        if page_token:
            logger.info(f"Got page access token for: {account.get('name', 'unknown')}")
            return page_token
    raise RuntimeError("No page access token found — make sure Instagram is connected to a Facebook Page")


def save_token_to_redis(token: str, expiry_days: int = 60):
    """Save token and expiry date to Redis."""
    r = _get_redis()
    if not r:
        return
    try:
        expiry = (datetime.now() + timedelta(days=expiry_days)).isoformat()
        r.set(REDIS_KEY_TOKEN, token)
        r.set(REDIS_KEY_EXPIRY, expiry)
        logger.info(f"Token saved to Redis, expires in {expiry_days} days")
    except Exception as e:
        logger.warning(f"Failed to save token to Redis: {e}")


def get_token_from_redis() -> tuple[str, datetime | None]:
    """Get token and expiry from Redis. Returns (token, expiry) or ('', None)."""
    r = _get_redis()
    if not r:
        return "", None
    try:
        token = r.get(REDIS_KEY_TOKEN) or ""
        expiry_str = r.get(REDIS_KEY_EXPIRY) or ""
        expiry = datetime.fromisoformat(expiry_str) if expiry_str else None
        return token, expiry
    except Exception as e:
        logger.warning(f"Failed to get token from Redis: {e}")
        return "", None


def get_valid_token() -> str:
    """
    Returns a valid Instagram access token.

    Logic:
    1. Check Redis for stored long-lived token
    2. If expiring within 10 days, auto-refresh it
    3. If no Redis token, try to exchange the env var token for long-lived
    4. Fall back to env var token as-is
    """
    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")
    env_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")

    # 1. Check Redis
    stored_token, expiry = get_token_from_redis()

    if stored_token and expiry:
        days_left = (expiry - datetime.now()).days
        logger.info(f"Instagram token from Redis — {days_left} days until expiry")

        # 2. Auto-refresh if expiring within 10 days
        if days_left <= 10 and app_id and app_secret:
            logger.info("Token expiring soon — refreshing...")
            try:
                new_token = exchange_for_long_lived(stored_token, app_id, app_secret)
                save_token_to_redis(new_token, expiry_days=60)
                logger.info("Token auto-refreshed successfully")
                return new_token
            except Exception as e:
                logger.warning(f"Auto-refresh failed: {e} — using existing token")

        return stored_token

    # 3. No Redis token — try to exchange env token for long-lived
    if env_token and app_id and app_secret:
        logger.info("No stored token — exchanging env token for long-lived...")
        try:
            long_token = exchange_for_long_lived(env_token, app_id, app_secret)
            save_token_to_redis(long_token, expiry_days=60)
            logger.info("Long-lived token obtained and saved to Redis")
            return long_token
        except Exception as e:
            logger.warning(f"Token exchange failed: {e} — using short-lived env token")

    # 4. Fall back to env var
    if env_token:
        logger.warning("Using short-lived env token — add META_APP_ID + META_APP_SECRET to Railway for auto-refresh")
    return env_token
