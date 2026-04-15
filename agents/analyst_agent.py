"""
analyst_agent.py — Pulls post metrics from X and Instagram every 24 hours,
analyzes performance with Claude, and rewrites the content strategy
to optimize for better engagement over time.
"""

import json
import os
import tweepy
import requests
from datetime import datetime
from utils.logger import get_logger
import anthropic

logger = get_logger("analyst_agent")

STRATEGY_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "content_strategy.json")
METRICS_LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "metrics_history.json")
os.makedirs(os.path.join(os.path.dirname(__file__), "..", "logs"), exist_ok=True)

DEFAULT_STRATEGY = {
    "top_topics": ["AI tools", "job market", "ChatGPT updates", "AI agents", "career impact"],
    "best_hooks": ["career impact", "urgency", "curiosity gap", "numbers and stats"],
    "avoid_topics": [],
    "best_post_type": "daily_brief",
    "tone_notes": "confident, sharp, career-focused. Use numbers. Create urgency.",
    "hashtag_notes": "Use career + AI combination hashtags. #AIcareers performs best.",
    "last_updated": "",
}


def load_strategy() -> dict:
    """Load current content strategy from Redis. Returns default if none exists."""
    try:
        from utils.redis_store import get_strategy
        strategy = get_strategy()
        if strategy:
            return strategy
    except Exception:
        pass
    return DEFAULT_STRATEGY.copy()


def save_strategy(strategy: dict):
    strategy["last_updated"] = datetime.now().isoformat()
    try:
        from utils.redis_store import save_strategy as redis_save
        redis_save(strategy)
    except Exception:
        # Fallback to local file
        with open(STRATEGY_FILE, "w") as f:
            json.dump(strategy, f, indent=2)
    logger.info("Content strategy updated.")


# ─────────────────────────────────────────────
# METRICS FETCHING
# ─────────────────────────────────────────────

def fetch_twitter_metrics(api_key, api_secret, access_token, access_token_secret) -> list[dict]:
    """Fetch recent tweet metrics from X API."""
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        me = client.get_me()
        if not me.data:
            return []

        tweets = client.get_users_tweets(
            me.data.id,
            max_results=10,
            tweet_fields=["public_metrics", "created_at", "text"],
        )

        metrics = []
        for tweet in (tweets.data or []):
            m = tweet.public_metrics or {}
            metrics.append({
                "platform": "twitter",
                "id": tweet.id,
                "text": tweet.text[:200],
                "created_at": str(tweet.created_at),
                "likes": m.get("like_count", 0),
                "retweets": m.get("retweet_count", 0),
                "replies": m.get("reply_count", 0),
                "impressions": m.get("impression_count", 0),
                "engagement": m.get("like_count", 0) + m.get("retweet_count", 0) + m.get("reply_count", 0),
            })

        logger.info(f"Twitter: fetched metrics for {len(metrics)} tweets")
        return metrics
    except Exception as e:
        logger.warning(f"Twitter metrics failed: {e}")
        return []


def fetch_instagram_metrics(access_token: str, business_account_id: str) -> list[dict]:
    """Fetch recent Instagram post metrics."""
    try:
        # Get recent media
        url = f"https://graph.facebook.com/v18.0/{business_account_id}/media"
        params = {
            "fields": "id,caption,timestamp,like_count,comments_count",
            "limit": 10,
            "access_token": access_token,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        posts = resp.json().get("data", [])

        metrics = []
        for post in posts:
            # Get insights for each post
            insights_url = f"https://graph.facebook.com/v18.0/{post['id']}/insights"
            insights_params = {
                "metric": "impressions,reach,engagement",
                "access_token": access_token,
            }
            impressions = reach = engagement = 0
            try:
                ins_resp = requests.get(insights_url, params=insights_params, timeout=8)
                if ins_resp.ok:
                    for item in ins_resp.json().get("data", []):
                        if item["name"] == "impressions":
                            impressions = item["values"][0]["value"] if item.get("values") else 0
                        elif item["name"] == "reach":
                            reach = item["values"][0]["value"] if item.get("values") else 0
                        elif item["name"] == "engagement":
                            engagement = item["values"][0]["value"] if item.get("values") else 0
            except Exception:
                pass

            caption = post.get("caption", "")[:200]
            metrics.append({
                "platform": "instagram",
                "id": post["id"],
                "caption": caption,
                "created_at": post.get("timestamp", ""),
                "likes": post.get("like_count", 0),
                "comments": post.get("comments_count", 0),
                "impressions": impressions,
                "reach": reach,
                "engagement": engagement or post.get("like_count", 0) + post.get("comments_count", 0),
            })

        logger.info(f"Instagram: fetched metrics for {len(metrics)} posts")
        return metrics
    except Exception as e:
        logger.warning(f"Instagram metrics failed: {e}")
        return []


# ─────────────────────────────────────────────
# ANALYSIS
# ─────────────────────────────────────────────

def analyze_and_update_strategy(
    twitter_metrics: list[dict],
    instagram_metrics: list[dict],
    anthropic_api_key: str,
    current_strategy: dict,
) -> dict:
    """Use Claude to analyze metrics and rewrite content strategy."""

    if not twitter_metrics and not instagram_metrics:
        logger.warning("No metrics to analyze.")
        return current_strategy

    # Format metrics for Claude
    def format_metrics(metrics, platform):
        if not metrics:
            return f"No {platform} data available."
        lines = []
        for m in sorted(metrics, key=lambda x: x.get("engagement", 0), reverse=True):
            text = m.get("text") or m.get("caption") or ""
            lines.append(
                f"- Engagement: {m.get('engagement', 0)} | "
                f"Likes: {m.get('likes', 0)} | "
                f"Impressions: {m.get('impressions', 0)} | "
                f"Text: {text[:120]}"
            )
        return "\n".join(lines)

    twitter_summary = format_metrics(twitter_metrics, "Twitter")
    instagram_summary = format_metrics(instagram_metrics, "Instagram")

    prompt = f"""You are analyzing social media performance for an AI news brand (@AI_TECH_NEWSS).

CURRENT STRATEGY:
{json.dumps(current_strategy, indent=2)}

TWITTER PERFORMANCE (last 10 posts, sorted by engagement):
{twitter_summary}

INSTAGRAM PERFORMANCE (last 10 posts, sorted by engagement):
{instagram_summary}

Analyze the data and identify:
1. Which topics/keywords drive the most engagement
2. Which hooks are working (urgency, curiosity, numbers, career impact)
3. Which post types perform best
4. What to avoid
5. Any patterns in high vs low performing posts

Then rewrite the content strategy to maximize engagement.

Return ONLY this JSON (no markdown, no extra text):
{{
  "top_topics": ["list of 5-7 topics that perform best based on data"],
  "best_hooks": ["list of 3-5 hook styles that work best"],
  "avoid_topics": ["list of topics/styles that underperformed"],
  "best_post_type": "daily_brief | learning | differentiator",
  "tone_notes": "specific tone guidance based on what worked",
  "hashtag_notes": "which hashtags/categories performed best on Instagram",
  "analysis_summary": "2-3 sentences on what you found and why you made these changes"
}}"""

    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        full_text = ""
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                full_text += text

        # Parse JSON
        raw = full_text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]

        new_strategy = json.loads(raw.strip())
        logger.info(f"Strategy updated: {new_strategy.get('analysis_summary', '')}")
        return new_strategy

    except Exception as e:
        logger.error(f"Strategy analysis failed: {e}")
        return current_strategy


# ─────────────────────────────────────────────
# SAVE METRICS HISTORY
# ─────────────────────────────────────────────

def _save_metrics(twitter_metrics, instagram_metrics):
    history = []
    if os.path.exists(METRICS_LOG):
        try:
            with open(METRICS_LOG) as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append({
        "timestamp": datetime.now().isoformat(),
        "twitter": twitter_metrics,
        "instagram": instagram_metrics,
    })
    history = history[-30:]  # Keep last 30 days
    with open(METRICS_LOG, "w") as f:
        json.dump(history, f, indent=2)


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def run_analyst(cfg) -> None:
    """Full analyst pipeline — fetch metrics, analyze, update strategy."""
    logger.info("Analyst Agent starting...")

    # Fetch metrics
    twitter_metrics = fetch_twitter_metrics(
        cfg.x_api_key, cfg.x_api_secret,
        cfg.x_access_token, cfg.x_access_token_secret,
    )
    instagram_metrics = fetch_instagram_metrics(
        cfg.instagram_access_token,
        cfg.instagram_business_account_id,
    ) if cfg.instagram_access_token and cfg.instagram_business_account_id else []

    # Save raw metrics history
    _save_metrics(twitter_metrics, instagram_metrics)

    # Analyze and update strategy
    current_strategy = load_strategy()
    new_strategy = analyze_and_update_strategy(
        twitter_metrics, instagram_metrics,
        cfg.anthropic_api_key, current_strategy,
    )
    save_strategy(new_strategy)

    logger.info(f"Analyst Agent complete. Summary: {new_strategy.get('analysis_summary', 'N/A')}")

    # Send daily email report
    if cfg.gmail_user and cfg.gmail_app_password and cfg.report_email:
        try:
            from utils.email_reporter import send_daily_report
            from utils.redis_store import get_today_count
            posts_today = get_today_count()
            latest_metrics = {"twitter": twitter_metrics, "instagram": instagram_metrics}
            send_daily_report(
                gmail_user=cfg.gmail_user,
                gmail_app_password=cfg.gmail_app_password,
                to_email=cfg.report_email,
                metrics=latest_metrics,
                strategy=new_strategy,
                posts_today=posts_today,
            )
        except Exception as e:
            logger.warning(f"Email report failed: {e}")
