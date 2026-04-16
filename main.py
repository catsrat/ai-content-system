"""
main.py — Entry point for the AI Content Automation System.

Usage:
  # Run the scheduler (starts posting at scheduled times)
  python main.py

  # Run a single post type immediately (for testing)
  python main.py --now daily_brief
  python main.py --now learning
  python main.py --now differentiator

  # Run all 3 post types immediately
  python main.py --now all
"""

import argparse
import os
import sys
import json
from datetime import datetime

from config import load_config
from agents.news_fetcher import fetch_all_news
from agents.workflow_fetcher import fetch_workflow_ideas
from agents.content_writer import ContentWriter, GeneratedPost
from agents.image_generator import generate_post_image
from agents.reels_generator import generate_reel
from agents.analyst_agent import run_analyst
from utils.cloudinary_uploader import init_cloudinary, upload_image, upload_video
from publishers.twitter import TwitterPublisher
from publishers.linkedin import LinkedInPublisher
from publishers.instagram import InstagramPublisher
from scheduler.scheduler import build_news_triggered_scheduler
from utils.logger import get_logger

logger = get_logger("main")

# ─────────────────────────────────────────────
# OUTPUT LOG — track what was posted each run
# ─────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def log_post_result(post: GeneratedPost, results: list[dict]) -> None:
    """Append post results to a daily JSON log file."""
    log_file = os.path.join(LOG_DIR, f"posts_{datetime.now().strftime('%Y%m%d')}.json")
    entry = {
        "timestamp": datetime.now().isoformat(),
        "post_type": post.post_type,
        "topic": post.topic,
        "results": results,
    }
    existing = []
    if os.path.exists(log_file):
        with open(log_file) as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []
    existing.append(entry)
    with open(log_file, "w") as f:
        json.dump(existing, f, indent=2)


# ─────────────────────────────────────────────
# CORE PIPELINE
# ─────────────────────────────────────────────

def run_post(post_type: str, cfg, dry_run: bool = False) -> None:
    """
    Full pipeline for one post type:
      fetch news → write content → generate image → upload → publish
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting pipeline: {post_type}")

    # 1. Fetch news
    logger.info("Fetching latest AI news...")
    all_articles = fetch_all_news(news_api_key=cfg.news_api_key)
    if not all_articles:
        logger.warning("No articles found. Skipping this run.")
        return

    # Filter out already-seen articles using Redis
    try:
        from utils.redis_store import is_article_seen
        articles = [a for a in all_articles if not is_article_seen(a["title"].lower()[:80])]
        if not articles:
            logger.warning("All articles already posted. Using all articles as fallback.")
            articles = all_articles
        else:
            logger.info(f"Fetched {len(all_articles)} articles, {len(articles)} are new")
        # Note: articles are marked seen by the scheduler before calling run_post
        # to avoid double-marking which drains the article pool too fast
    except Exception:
        articles = all_articles
        logger.info(f"Fetched {len(articles)} articles")

    # 2. Write content with Claude
    logger.info("Generating content with Claude...")
    writer = ContentWriter(
        api_key=cfg.anthropic_api_key,
        brand_name=cfg.brand_name,
        brand_niche=cfg.brand_niche,
        brand_tone=cfg.brand_tone,
    )

    if post_type == "workflow":
        workflow_ideas = fetch_workflow_ideas(max_results=10)
        post = writer.write_workflow_post(workflow_ideas)
    else:
        post_fn = {
            "daily_brief": writer.write_daily_brief,
            "learning": writer.write_learning_post,
            "differentiator": writer.write_differentiator_post,
        }.get(post_type)

        if not post_fn:
            logger.error(f"Unknown post type: {post_type}")
            return

        post = post_fn(articles)
    logger.info(f"Content generated: {post.topic}")

    if dry_run:
        print("\n" + "=" * 60)
        print(f"POST TYPE: {post.post_type.upper()}")
        print(f"TOPIC: {post.topic}")
        print(f"\n[TWITTER]\n{post.twitter_text}")
        print(f"\n[LINKEDIN]\n{post.linkedin_text}")
        print(f"\n[INSTAGRAM]\n{post.instagram_caption}\n{post.instagram_hashtags}")
        print(f"\n[IMAGE PROMPT]\n{post.image_prompt}")
        print("=" * 60 + "\n")
        return

    # 3. Generate image
    logger.info("Generating branded image...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_filename = f"{post_type}_{timestamp}.png"
    local_image_path = None
    public_image_url = None
    local_carousel_paths = []
    public_carousel_urls = []

    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    bg_url = next((a.get("image_url", "") for a in articles if a.get("image_url")), "")

    # 3a. Generate Twitter image (single square)
    try:
        from agents.image_generator import generate_post_image
        local_image_path = generate_post_image(
            post_type=post.post_type,
            headline=post.key_message,
            brand_name=cfg.brand_name,
            filename=image_filename,
            background_image_url=bg_url,
            topic=post.topic,
            unsplash_access_key=unsplash_key,
        )
        logger.info(f"Image saved: {local_image_path}")
    except Exception as e:
        logger.warning(f"Image generation failed: {e}. Posting without image.")

    # 3b. Generate Instagram carousel (4 slides with real Unsplash photos)
    if post.carousel_slides:
        try:
            from agents.image_generator import generate_carousel_images
            local_carousel_paths = generate_carousel_images(
                post_type=post.post_type,
                carousel_texts=post.carousel_slides,
                topic=post.topic,
                brand_name=cfg.brand_name,
                base_filename=f"{post_type}_{timestamp}",
                background_image_url=bg_url,
                unsplash_access_key=unsplash_key,
            )
            logger.info(f"Carousel: {len(local_carousel_paths)} slides generated")
        except Exception as e:
            logger.warning(f"Carousel generation failed: {e}")

    # 3c. Reels disabled — using carousel instead
    local_reel_path = None

    # 4. Upload to Cloudinary
    public_reel_url = None
    has_content = local_image_path or local_reel_path or local_carousel_paths
    if has_content:
        try:
            init_cloudinary(
                cloud_name=cfg.cloudinary_cloud_name,
                api_key=cfg.cloudinary_api_key,
                api_secret=cfg.cloudinary_api_secret,
            )
        except Exception as e:
            logger.warning(f"Cloudinary init failed: {e}")

    if local_image_path:
        try:
            public_image_url = upload_image(local_image_path, folder="ai-content")
            logger.info(f"Image uploaded to Cloudinary: {public_image_url}")
        except Exception as e:
            logger.warning(f"Cloudinary image upload failed: {e}")

    for cp in local_carousel_paths:
        try:
            url = upload_image(cp, folder="ai-content/carousel")
            public_carousel_urls.append(url)
            logger.info(f"Carousel slide uploaded: {url}")
        except Exception as e:
            logger.warning(f"Carousel slide upload failed: {e}")

    if local_reel_path:
        try:
            public_reel_url = upload_video(local_reel_path, folder="ai-content/reels")
            logger.info(f"Reel uploaded to Cloudinary: {public_reel_url}")
        except Exception as e:
            logger.warning(f"Cloudinary reel upload failed: {e}")

    # 5. Publish to all platforms
    results = []

    # — X / Twitter — (max 1500 posts/month)
    TWITTER_MONTHLY_LIMIT = 1500
    try:
        from utils.redis_store import get_monthly_twitter_count, increment_monthly_twitter_count
        twitter_month_count = get_monthly_twitter_count()
    except Exception:
        twitter_month_count = 0

    if twitter_month_count >= TWITTER_MONTHLY_LIMIT:
        logger.info(f"Twitter monthly limit reached ({twitter_month_count}/1500). Skipping Twitter.")
        results.append({"success": False, "platform": "twitter", "error": "monthly limit reached"})
    else:
        logger.info(f"Publishing to X (Twitter)... [{twitter_month_count + 1}/1500 this month]")
        try:
            twitter = TwitterPublisher(
                api_key=cfg.x_api_key,
                api_secret=cfg.x_api_secret,
                access_token=cfg.x_access_token,
                access_token_secret=cfg.x_access_token_secret,
            )
            result = twitter.publish(
                text=post.twitter_text,
                image_path=local_image_path,
            )
            results.append(result)
            if result.get("success"):
                increment_monthly_twitter_count()
            logger.info(f"Twitter: {'OK' if result['success'] else 'FAILED'}")
        except Exception as e:
            logger.error(f"Twitter error: {e}")
            results.append({"success": False, "platform": "twitter", "error": str(e)})

    # — LinkedIn —
    if cfg.linkedin_access_token and cfg.linkedin_organization_id:
        logger.info("Publishing to LinkedIn...")
        try:
            linkedin = LinkedInPublisher(
                access_token=cfg.linkedin_access_token,
                organization_id=cfg.linkedin_organization_id,
            )
            result = linkedin.publish(
                text=post.linkedin_text,
                image_path=local_image_path,
            )
            results.append(result)
            logger.info(f"LinkedIn: {'OK' if result['success'] else 'FAILED'}")
        except Exception as e:
            logger.error(f"LinkedIn error: {e}")
            results.append({"success": False, "platform": "linkedin", "error": str(e)})
    else:
        logger.info("LinkedIn skipped — keys not configured yet")

    # — Instagram —
    if cfg.instagram_access_token and cfg.instagram_business_account_id:
        caption = (post.instagram_caption + post.instagram_hashtags)[:2200]
        instagram = InstagramPublisher(
            access_token=cfg.instagram_access_token,
            business_account_id=cfg.instagram_business_account_id,
        )

        # 1. Post Reel (highest reach)
        if public_reel_url:
            logger.info("Publishing Reel to Instagram...")
            try:
                result = instagram.publish_reel(
                    video_url=public_reel_url,
                    caption=caption,
                )
                results.append(result)
                logger.info(f"Instagram Reel: {'OK' if result['success'] else 'FAILED'}")
            except Exception as e:
                logger.error(f"Instagram Reel error: {e}")
                results.append({"success": False, "platform": "instagram", "error": str(e)})

        # 2. Post carousel (4 swipeable slides)
        if public_carousel_urls:
            logger.info(f"Publishing carousel ({len(public_carousel_urls)} slides) to Instagram...")
            try:
                result = instagram.publish(
                    caption=caption,
                    image_urls=public_carousel_urls,
                )
                results.append(result)
                logger.info(f"Instagram carousel: {'OK' if result['success'] else 'FAILED'}")
            except Exception as e:
                logger.error(f"Instagram carousel error: {e}")
                results.append({"success": False, "platform": "instagram", "error": str(e)})
        elif not public_reel_url and public_image_url:
            # Fallback: single image if no reel and no carousel
            logger.info("Publishing single image to Instagram (fallback)...")
            try:
                result = instagram.publish(
                    caption=caption,
                    image_urls=[public_image_url],
                )
                results.append(result)
                logger.info(f"Instagram image: {'OK' if result['success'] else 'FAILED'}")
            except Exception as e:
                logger.error(f"Instagram image error: {e}")
                results.append({"success": False, "platform": "instagram", "error": str(e)})

        if not public_reel_url and not public_image_url:
            logger.warning("Instagram skipped — no public URL available")
    else:
        logger.info("Instagram skipped — keys not configured yet")

    # 6. Email workflow guide if this is a workflow post
    if post.post_type == "workflow":
        workflow_detail = getattr(post, "workflow_detail", "")
        logger.info(f"Workflow detail length: {len(workflow_detail)} chars")
        if workflow_detail and cfg.gmail_user and cfg.gmail_app_password:
            try:
                from utils.email_reporter import send_workflow_guide
                ok = send_workflow_guide(
                    gmail_user=cfg.gmail_user,
                    gmail_app_password=cfg.gmail_app_password,
                    to_email=cfg.report_email,
                    topic=post.topic,
                    workflow_detail=workflow_detail,
                )
                logger.info(f"Workflow guide email: {'sent' if ok else 'failed'}")
            except Exception as e:
                logger.warning(f"Workflow guide email error: {e}")
        else:
            logger.warning(f"Workflow guide email skipped — detail empty: {not workflow_detail}, gmail configured: {bool(cfg.gmail_user)}")

    # 7. Log results
    log_post_result(post, results)

    # Summary
    ok = sum(1 for r in results if r.get("success"))
    logger.info(f"Run complete: {ok}/{len(results)} platforms succeeded for [{post_type}]")


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Content Automation System")
    parser.add_argument(
        "--now",
        metavar="POST_TYPE",
        help="Run immediately: daily_brief | learning | differentiator | all",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print content without posting",
    )
    parser.add_argument(
        "--timezone",
        default="Asia/Kolkata",
        help="Timezone for scheduler (default: Asia/Kolkata)",
    )
    args = parser.parse_args()

    # Load config
    try:
        cfg = load_config()
    except EnvironmentError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    if args.now:
        # Run immediately
        post_types = (
            ["daily_brief", "learning", "differentiator"]
            if args.now == "all"
            else [args.now]
        )
        for pt in post_types:
            run_post(pt, cfg, dry_run=args.dry_run)
    else:
        # Start the news-triggered scheduler
        logger.info(f"Starting news-triggered scheduler (timezone: {args.timezone})")
        logger.info("Checking for new AI news every 30 minutes. Max 5 posts/day.")

        from apscheduler.triggers.interval import IntervalTrigger
        import pytz

        scheduler = build_news_triggered_scheduler(
            fetch_func=lambda: fetch_all_news(news_api_key=cfg.news_api_key),
            run_func=lambda pt: run_post(pt, cfg),
            timezone=args.timezone,
        )

        # Add Analyst Agent — runs every 24 hours
        tz = pytz.timezone(args.timezone)
        scheduler.add_job(
            func=lambda: run_analyst(cfg),
            trigger=IntervalTrigger(hours=24, timezone=tz),
            id="analyst",
            name="Analyst Agent",
            replace_existing=True,
        )
        logger.info("Analyst Agent scheduled — runs every 24 hours.")

        try:
            logger.info("Scheduler running. Press Ctrl+C to stop.")
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
