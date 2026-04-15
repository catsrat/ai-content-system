"""
email_reporter.py — Sends daily performance report via Gmail.
Includes top posts, engagement stats, and strategy updates from Analyst Agent.
"""

import smtplib
import json
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
from utils.logger import get_logger

logger = get_logger("email_reporter")

METRICS_LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "metrics_history.json")


def send_daily_report(
    gmail_user: str,
    gmail_app_password: str,
    to_email: str,
    metrics: dict = None,
    strategy: dict = None,
    posts_today: int = 0,
):
    """Send daily performance report email."""

    today = date.today().strftime("%B %d, %Y")

    # Build email HTML
    html = f"""
    <html><body style="font-family: Arial, sans-serif; background: #0a0f28; color: #ffffff; padding: 20px;">

    <div style="max-width: 600px; margin: 0 auto;">

        <!-- Header -->
        <div style="background: linear-gradient(135deg, #0a0f28, #1a1f48); border: 1px solid #00b4ff; border-radius: 12px; padding: 24px; margin-bottom: 20px; text-align: center;">
            <h1 style="color: #00b4ff; margin: 0; font-size: 28px;">📊 AI_TECH_NEWSS</h1>
            <p style="color: #aaa; margin: 8px 0 0;">Daily Performance Report — {today}</p>
        </div>

        <!-- Posts Today -->
        <div style="background: #111830; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #00b4ff; margin: 0 0 12px;">📬 Posts Today</h2>
            <p style="font-size: 36px; font-weight: bold; margin: 0; color: #fff;">{posts_today}</p>
            <p style="color: #888; margin: 4px 0 0;">posts published across X + Instagram</p>
        </div>
    """

    # Twitter metrics
    twitter_data = (metrics or {}).get("twitter", [])
    if twitter_data:
        top_tweet = max(twitter_data, key=lambda x: x.get("engagement", 0))
        total_impressions = sum(t.get("impressions", 0) for t in twitter_data)
        total_likes = sum(t.get("likes", 0) for t in twitter_data)
        total_engagement = sum(t.get("engagement", 0) for t in twitter_data)

        html += f"""
        <div style="background: #111830; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #1da1f2; margin: 0 0 16px;">🐦 X (Twitter)</h2>
            <div style="display: flex; gap: 12px; margin-bottom: 16px;">
                <div style="flex: 1; background: #1a2240; border-radius: 8px; padding: 12px; text-align: center;">
                    <p style="font-size: 24px; font-weight: bold; margin: 0; color: #fff;">{total_impressions:,}</p>
                    <p style="color: #888; margin: 4px 0 0; font-size: 12px;">Impressions</p>
                </div>
                <div style="flex: 1; background: #1a2240; border-radius: 8px; padding: 12px; text-align: center;">
                    <p style="font-size: 24px; font-weight: bold; margin: 0; color: #fff;">{total_likes:,}</p>
                    <p style="color: #888; margin: 4px 0 0; font-size: 12px;">Likes</p>
                </div>
                <div style="flex: 1; background: #1a2240; border-radius: 8px; padding: 12px; text-align: center;">
                    <p style="font-size: 24px; font-weight: bold; margin: 0; color: #fff;">{total_engagement:,}</p>
                    <p style="color: #888; margin: 4px 0 0; font-size: 12px;">Engagements</p>
                </div>
            </div>
            <div style="background: #1a2240; border-radius: 8px; padding: 12px;">
                <p style="color: #00b4ff; margin: 0 0 6px; font-size: 12px; text-transform: uppercase;">🏆 Top Tweet</p>
                <p style="margin: 0; font-size: 14px; color: #ddd;">{top_tweet.get('text', '')[:180]}...</p>
                <p style="margin: 6px 0 0; color: #888; font-size: 12px;">{top_tweet.get('engagement', 0)} engagements</p>
            </div>
        </div>
        """

    # Instagram metrics
    instagram_data = (metrics or {}).get("instagram", [])
    if instagram_data:
        top_post = max(instagram_data, key=lambda x: x.get("engagement", 0))
        total_reach = sum(p.get("reach", 0) for p in instagram_data)
        total_likes = sum(p.get("likes", 0) for p in instagram_data)
        total_comments = sum(p.get("comments", 0) for p in instagram_data)

        html += f"""
        <div style="background: #111830; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #e1306c; margin: 0 0 16px;">📸 Instagram</h2>
            <div style="display: flex; gap: 12px; margin-bottom: 16px;">
                <div style="flex: 1; background: #1a2240; border-radius: 8px; padding: 12px; text-align: center;">
                    <p style="font-size: 24px; font-weight: bold; margin: 0; color: #fff;">{total_reach:,}</p>
                    <p style="color: #888; margin: 4px 0 0; font-size: 12px;">Reach</p>
                </div>
                <div style="flex: 1; background: #1a2240; border-radius: 8px; padding: 12px; text-align: center;">
                    <p style="font-size: 24px; font-weight: bold; margin: 0; color: #fff;">{total_likes:,}</p>
                    <p style="color: #888; margin: 4px 0 0; font-size: 12px;">Likes</p>
                </div>
                <div style="flex: 1; background: #1a2240; border-radius: 8px; padding: 12px; text-align: center;">
                    <p style="font-size: 24px; font-weight: bold; margin: 0; color: #fff;">{total_comments:,}</p>
                    <p style="color: #888; margin: 4px 0 0; font-size: 12px;">Comments</p>
                </div>
            </div>
            <div style="background: #1a2240; border-radius: 8px; padding: 12px;">
                <p style="color: #e1306c; margin: 0 0 6px; font-size: 12px; text-transform: uppercase;">🏆 Top Post</p>
                <p style="margin: 0; font-size: 14px; color: #ddd;">{top_post.get('caption', '')[:180]}...</p>
                <p style="margin: 6px 0 0; color: #888; font-size: 12px;">{top_post.get('engagement', 0)} engagements</p>
            </div>
        </div>
        """

    # Strategy update
    if strategy and strategy.get("analysis_summary"):
        top_topics = ", ".join(strategy.get("top_topics", [])[:3])
        avoid = ", ".join(strategy.get("avoid_topics", [])[:3]) or "None yet"
        html += f"""
        <div style="background: #111830; border: 1px solid #00b4ff33; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <h2 style="color: #00b4ff; margin: 0 0 12px;">🧠 Analyst Agent Update</h2>
            <p style="color: #ddd; margin: 0 0 12px;">{strategy.get('analysis_summary', '')}</p>
            <p style="color: #888; margin: 0 0 6px; font-size: 13px;"><strong style="color: #00b4ff;">Top topics:</strong> {top_topics}</p>
            <p style="color: #888; margin: 0; font-size: 13px;"><strong style="color: #ff5020;">Avoid:</strong> {avoid}</p>
        </div>
        """

    # Footer
    html += f"""
        <div style="text-align: center; padding: 16px; color: #555; font-size: 12px;">
            <p>AI_TECH_NEWSS Automation System • {today}</p>
            <p>Next analyst run in 24 hours</p>
        </div>

    </div>
    </body></html>
    """

    # Send email
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 AI_TECH_NEWSS Daily Report — {today}"
        msg["From"] = gmail_user
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_app_password)
            server.sendmail(gmail_user, to_email, msg.as_string())

        logger.info(f"Daily report sent to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Email report failed: {e}")
        return False
