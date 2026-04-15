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
from agents.content_writer import ContentWriter, GeneratedPost
from agents.image_generator import generate_post_image
from utils.cloudinary_uploader import init_cloudinary, upload_image
from publishers.twitter import TwitterPublisher
from publishers.linkedin import LinkedInPublisher
from publishers.instagram import InstagramPublisher
from scheduler.scheduler import build_scheduler
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
    articles = fetch_all_news(news_api_key=cfg.news_api_key)
    if not articles:
        logger.warning("No articles found. Skipping this run.")
        return
    logger.info(f"Fetched {len(articles)} articles")

    # 2. Write content with Claude
    logger.info("Generating content with Claude...")
    writer = ContentWriter(
        api_key=cfg.anthropic_api_key,
        brand_name=cfg.brand_name,
        brand_niche=cfg.brand_niche,
        brand_tone=cfg.brand_tone,
    )

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

    try:
        # Use the first article's image as background
        bg_url = next((a.get("image_url", "") for a in articles if a.get("image_url")), "")
        local_image_path = generate_post_image(
            post_type=post.post_type,
            headline=post.key_message,
            brand_name=cfg.brand_name,
            filename=image_filename,
            background_image_url=bg_url,
        )
        logger.info(f"Image saved: {local_image_path}")
    except Exception as e:
        logger.warning(f"Image generation failed: {e}. Posting without image.")

    # 4. Upload to Cloudinary (needed for Instagram)
    if local_image_path:
        try:
            init_cloudinary(
                cloud_name=cfg.cloudinary_cloud_name,
                api_key=cfg.cloudinary_api_key,
                api_secret=cfg.cloudinary_api_secret,
            )
            public_image_url = upload_image(local_image_path, folder="ai-content")
            logger.info(f"Image uploaded to Cloudinary: {public_image_url}")
        except Exception as e:
            logger.warning(f"Cloudinary upload failed: {e}")

    # 5. Publish to all platforms
    results = []

    # — X / Twitter —
    logger.info("Publishing to X (Twitter)...")
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
        logger.info("Publishing to Instagram...")
        try:
            if public_image_url:
                caption = post.instagram_caption + post.instagram_hashtags
                instagram = InstagramPublisher(
                    access_token=cfg.instagram_access_token,
                    business_account_id=cfg.instagram_business_account_id,
                )
                result = instagram.publish(
                    caption=caption,
                    image_urls=[public_image_url],
                )
                results.append(result)
                logger.info(f"Instagram: {'OK' if result['success'] else 'FAILED'}")
            else:
                logger.warning("Instagram skipped — no public image URL available")
        except Exception as e:
            logger.error(f"Instagram error: {e}")
            results.append({"success": False, "platform": "instagram", "error": str(e)})
    else:
        logger.info("Instagram skipped — keys not configured yet")

    # 6. Log results
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
        # Start the scheduler
        logger.info(f"Starting scheduler (timezone: {args.timezone})")
        logger.info("Schedule: 08:00 Daily Brief | 12:00 Learning | 18:00 Differentiator")

        scheduler = build_scheduler(
            run_func=lambda pt: run_post(pt, cfg),
            timezone=args.timezone,
        )

        try:
            logger.info("Scheduler running. Press Ctrl+C to stop.")
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
