"""
email_reporter.py — Sends emails via Resend API (HTTP, works on Railway).
Includes workflow guides and daily performance reports.

Setup:
  1. Sign up at resend.com (free: 3000 emails/month)
  2. Add a Resend API key to Railway as RESEND_API_KEY
  3. Verify your sender domain OR use onboarding@resend.dev for testing
"""

import json
import os
import requests
from datetime import date
from utils.logger import get_logger

logger = get_logger("email_reporter")

RESEND_API_URL = "https://api.resend.com/emails"
METRICS_LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "metrics_history.json")


def _send_via_resend(api_key: str, from_email: str, to_email: str, subject: str, html: str) -> bool:
    """Send an email using Resend API (HTTP — works on Railway)."""
    try:
        resp = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=30,
        )
        if resp.ok:
            logger.info(f"Email sent via Resend: {resp.json().get('id', '')}")
            return True
        else:
            logger.error(f"Resend API error {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Resend send failed: {e}")
        return False


def send_daily_report(
    gmail_user: str,
    gmail_app_password: str,
    to_email: str,
    metrics: dict = None,
    strategy: dict = None,
    posts_today: int = 0,
):
    """Send daily performance report email via Resend."""

    # Get Resend API key from env
    resend_api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_api_key:
        logger.warning("RESEND_API_KEY not set — skipping daily report email")
        return False

    # Use verified domain or Resend's onboarding address for testing
    from_email = os.environ.get("RESEND_FROM_EMAIL", "AI_TECH_NEWSS <onboarding@resend.dev>")

    today = date.today().strftime("%B %d, %Y")

    html = f"""
    <html><body style="font-family: Arial, sans-serif; background: #0a0f28; color: #ffffff; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto;">

        <div style="background: linear-gradient(135deg, #0a0f28, #1a1f48); border: 1px solid #00b4ff; border-radius: 12px; padding: 24px; margin-bottom: 20px; text-align: center;">
            <h1 style="color: #00b4ff; margin: 0; font-size: 28px;">AI_TECH_NEWSS</h1>
            <p style="color: #aaa; margin: 8px 0 0;">Daily Performance Report — {today}</p>
        </div>

        <div style="background: #111830; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #00b4ff; margin: 0 0 12px;">Posts Today</h2>
            <p style="font-size: 36px; font-weight: bold; margin: 0; color: #fff;">{posts_today}</p>
            <p style="color: #888; margin: 4px 0 0;">posts published across X + Instagram</p>
        </div>
    """

    twitter_data = (metrics or {}).get("twitter", [])
    if twitter_data:
        top_tweet = max(twitter_data, key=lambda x: x.get("engagement", 0))
        total_impressions = sum(t.get("impressions", 0) for t in twitter_data)
        total_likes = sum(t.get("likes", 0) for t in twitter_data)
        total_engagement = sum(t.get("engagement", 0) for t in twitter_data)

        html += f"""
        <div style="background: #111830; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #1da1f2; margin: 0 0 16px;">X (Twitter)</h2>
            <p style="color: #fff;"><strong>{total_impressions:,}</strong> impressions &nbsp;|&nbsp; <strong>{total_likes:,}</strong> likes &nbsp;|&nbsp; <strong>{total_engagement:,}</strong> engagements</p>
            <div style="background: #1a2240; border-radius: 8px; padding: 12px; margin-top: 12px;">
                <p style="color: #00b4ff; margin: 0 0 6px; font-size: 12px;">TOP TWEET</p>
                <p style="margin: 0; font-size: 14px; color: #ddd;">{top_tweet.get('text', '')[:180]}...</p>
                <p style="margin: 6px 0 0; color: #888; font-size: 12px;">{top_tweet.get('engagement', 0)} engagements</p>
            </div>
        </div>
        """

    instagram_data = (metrics or {}).get("instagram", [])
    if instagram_data:
        top_post = max(instagram_data, key=lambda x: x.get("engagement", 0))
        total_reach = sum(p.get("reach", 0) for p in instagram_data)
        total_likes = sum(p.get("likes", 0) for p in instagram_data)
        total_comments = sum(p.get("comments", 0) for p in instagram_data)

        html += f"""
        <div style="background: #111830; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #e1306c; margin: 0 0 16px;">Instagram</h2>
            <p style="color: #fff;"><strong>{total_reach:,}</strong> reach &nbsp;|&nbsp; <strong>{total_likes:,}</strong> likes &nbsp;|&nbsp; <strong>{total_comments:,}</strong> comments</p>
            <div style="background: #1a2240; border-radius: 8px; padding: 12px; margin-top: 12px;">
                <p style="color: #e1306c; margin: 0 0 6px; font-size: 12px;">TOP POST</p>
                <p style="margin: 0; font-size: 14px; color: #ddd;">{top_post.get('caption', '')[:180]}...</p>
                <p style="margin: 6px 0 0; color: #888; font-size: 12px;">{top_post.get('engagement', 0)} engagements</p>
            </div>
        </div>
        """

    if strategy and strategy.get("analysis_summary"):
        top_topics = ", ".join(strategy.get("top_topics", [])[:3])
        avoid = ", ".join(strategy.get("avoid_topics", [])[:3]) or "None yet"
        html += f"""
        <div style="background: #111830; border: 1px solid #00b4ff33; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #00b4ff; margin: 0 0 12px;">Analyst Agent Update</h2>
            <p style="color: #ddd; margin: 0 0 12px;">{strategy.get('analysis_summary', '')}</p>
            <p style="color: #888; margin: 0 0 6px; font-size: 13px;"><strong style="color: #00b4ff;">Top topics:</strong> {top_topics}</p>
            <p style="color: #888; margin: 0; font-size: 13px;"><strong style="color: #ff5020;">Avoid:</strong> {avoid}</p>
        </div>
        """

    html += f"""
        <div style="text-align: center; padding: 16px; color: #555; font-size: 12px;">
            <p>AI_TECH_NEWSS Automation System • {today}</p>
        </div>
    </div>
    </body></html>
    """

    return _send_via_resend(
        api_key=resend_api_key,
        from_email=from_email,
        to_email=to_email,
        subject=f"AI_TECH_NEWSS Daily Report — {today}",
        html=html,
    )


def send_workflow_guide(
    gmail_user: str,
    gmail_app_password: str,
    to_email: str,
    topic: str,
    workflow_detail: str,
):
    """
    Email the full workflow guide whenever a workflow post is published.
    Uses Resend API (HTTP — works on Railway, no SMTP needed).
    """
    resend_api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_api_key:
        logger.warning("RESEND_API_KEY not set — skipping workflow guide email")
        return False

    from_email = os.environ.get("RESEND_FROM_EMAIL", "AI_TECH_NEWSS <onboarding@resend.dev>")
    today = date.today().strftime("%B %d, %Y")

    lines = workflow_detail.strip().split("\n")
    steps_html = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        steps_html += f'<p style="margin: 8px 0; color: #ddd; font-size: 15px;">{line}</p>\n'

    html = f"""
    <html><body style="font-family: Arial, sans-serif; background: #0a0f28; color: #ffffff; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto;">

        <div style="background: linear-gradient(135deg, #1a0a35, #2a1060); border: 1px solid #b450ff; border-radius: 12px; padding: 24px; margin-bottom: 20px; text-align: center;">
            <h1 style="color: #b450ff; margin: 0; font-size: 26px;">New Workflow Post Published</h1>
            <p style="color: #aaa; margin: 8px 0 0;">{today}</p>
        </div>

        <div style="background: #111830; border-radius: 10px; padding: 24px; margin-bottom: 16px;">
            <h2 style="color: #b450ff; margin: 0 0 8px; font-size: 20px;">{topic}</h2>
            <p style="color: #888; margin: 0 0 20px; font-size: 13px;">Full step-by-step guide — paste into Notion or Google Docs, then put that link in ManyChat</p>
            <div style="background: #0a0f28; border-left: 4px solid #b450ff; border-radius: 4px; padding: 16px;">
                {steps_html}
            </div>
        </div>

        <div style="background: #111830; border-radius: 10px; padding: 16px; margin-bottom: 16px;">
            <h3 style="color: #00b4ff; margin: 0 0 10px;">Next steps:</h3>
            <p style="color: #ddd; margin: 6px 0;">1. Copy the workflow above</p>
            <p style="color: #ddd; margin: 6px 0;">2. Paste into a <strong>Notion page</strong> or <strong>Google Doc</strong></p>
            <p style="color: #ddd; margin: 6px 0;">3. Get the shareable link</p>
            <p style="color: #ddd; margin: 6px 0;">4. Update your <strong>ManyChat</strong> flow with this link</p>
        </div>

        <div style="text-align: center; padding: 16px; color: #555; font-size: 12px;">
            <p>AI_TECH_NEWSS Automation System</p>
        </div>
    </div>
    </body></html>
    """

    return _send_via_resend(
        api_key=resend_api_key,
        from_email=from_email,
        to_email=to_email,
        subject=f"New Workflow Guide: {topic}",
        html=html,
    )
