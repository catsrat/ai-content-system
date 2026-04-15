"""
twitter.py — Posts to X (Twitter) using Tweepy v4.

Supports:
  - Single tweets
  - Threads (auto-splits long content into numbered tweets)
  - Tweets with images

API tier: Free (1,500 tweets/month write access)
Get credentials: developer.twitter.com → Create App
"""

import tweepy
from utils.logger import get_logger

logger = get_logger("twitter")

MAX_TWEET_LENGTH = 280


def _split_into_thread(text: str, max_len: int = 270) -> list[str]:
    """
    Split long text into thread-sized chunks.
    Reserves space for (1/n) numbering.
    """
    # If fits in a single tweet, return as-is
    if len(text) <= MAX_TWEET_LENGTH:
        return [text]

    # Split by newlines first, then by sentences
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    tweets = []
    current = ""

    for para in paragraphs:
        # If adding this paragraph exceeds limit, save current and start new
        if len(current) + len(para) + 2 > max_len:
            if current:
                tweets.append(current.strip())
            current = para
        else:
            current = (current + "\n" + para).strip() if current else para

    if current:
        tweets.append(current.strip())

    # Add thread numbering
    if len(tweets) > 1:
        total = len(tweets)
        tweets = [f"{t}\n\n{i + 1}/{total}" for i, t in enumerate(tweets)]

    return tweets


class TwitterPublisher:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
    ):
        # v2 client for posting
        self.client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )

        # v1.1 API for media uploads (still needed for image uploads)
        auth = tweepy.OAuth1UserHandler(
            api_key, api_secret, access_token, access_token_secret
        )
        self.v1_api = tweepy.API(auth)

    def _upload_media(self, image_path: str) -> str:
        """Upload image via v1.1 API and return media_id."""
        media = self.v1_api.media_upload(image_path)
        logger.info(f"Uploaded media to Twitter: {media.media_id}")
        return str(media.media_id)

    def post_tweet(self, text: str, image_path: str = None) -> str:
        """
        Post a single tweet. Optionally attach an image.
        Returns tweet ID.
        """
        media_ids = None
        if image_path:
            try:
                media_id = self._upload_media(image_path)
                media_ids = [media_id]
            except Exception as e:
                logger.warning(f"Image upload failed, posting without image: {e}")

        params = {"text": text[:MAX_TWEET_LENGTH]}
        if media_ids:
            params["media_ids"] = media_ids

        response = self.client.create_tweet(**params)
        tweet_id = response.data["id"]
        logger.info(f"Tweet posted: https://twitter.com/i/web/status/{tweet_id}")
        return tweet_id

    def post_thread(self, text: str, image_path: str = None) -> list[str]:
        """
        Post a thread. First tweet gets the image (if any).
        Returns list of tweet IDs.
        """
        tweets = _split_into_thread(text)
        tweet_ids = []
        reply_to_id = None

        for i, tweet_text in enumerate(tweets):
            media_ids = None

            # Attach image only to the first tweet
            if i == 0 and image_path:
                try:
                    media_id = self._upload_media(image_path)
                    media_ids = [media_id]
                except Exception as e:
                    logger.warning(f"Image upload failed: {e}")

            params = {"text": tweet_text[:MAX_TWEET_LENGTH]}
            if media_ids:
                params["media_ids"] = media_ids
            if reply_to_id:
                params["in_reply_to_tweet_id"] = reply_to_id

            response = self.client.create_tweet(**params)
            tweet_id = response.data["id"]
            tweet_ids.append(tweet_id)
            reply_to_id = tweet_id

        logger.info(f"Thread posted: {len(tweet_ids)} tweets")
        return tweet_ids

    def publish(self, text: str, image_path: str = None) -> dict:
        """
        Main publish method. Automatically decides single tweet vs thread.
        Returns result dict.
        """
        try:
            if len(text) > MAX_TWEET_LENGTH:
                ids = self.post_thread(text, image_path)
                return {"success": True, "platform": "twitter", "ids": ids, "type": "thread"}
            else:
                tweet_id = self.post_tweet(text, image_path)
                return {"success": True, "platform": "twitter", "id": tweet_id, "type": "tweet"}
        except Exception as e:
            logger.error(f"Twitter publish failed: {e}")
            return {"success": False, "platform": "twitter", "error": str(e)}
