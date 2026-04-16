"""
instagram.py — Posts to Instagram via the Meta Graph API.

Supports:
  - Single image posts
  - Carousel posts (multiple images)

Requirements:
  - Instagram Business or Creator account
  - Connected to a Facebook Page
  - Meta Developer App with instagram_basic + instagram_content_publish permissions
  - Images must be hosted at a public HTTPS URL (use Cloudinary)

Get credentials: developers.facebook.com → Create App → Instagram Graph API
"""

import time
import requests
from utils.logger import get_logger

logger = get_logger("instagram")

GRAPH_API_BASE = "https://graph.facebook.com/v18.0"


class InstagramPublisher:
    def __init__(self, access_token: str, business_account_id: str):
        # Use token manager to get a valid long-lived token
        try:
            from utils.instagram_token_manager import get_valid_token
            self.access_token = get_valid_token() or access_token
        except Exception:
            self.access_token = access_token
        self.account_id = business_account_id

    def _api_post(self, endpoint: str, params: dict) -> dict:
        """Make a POST request to the Graph API."""
        params["access_token"] = self.access_token
        resp = requests.post(
            f"{GRAPH_API_BASE}/{endpoint}",
            params=params,
            timeout=30,
        )
        if not resp.ok:
            logger.error(f"Instagram API {resp.status_code} — {resp.text}")
            resp.raise_for_status()
        return resp.json()

    def _api_get(self, endpoint: str, params: dict = None) -> dict:
        """Make a GET request to the Graph API."""
        p = params or {}
        p["access_token"] = self.access_token
        resp = requests.get(
            f"{GRAPH_API_BASE}/{endpoint}",
            params=p,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _wait_for_container(self, container_id: str, max_wait: int = 60) -> bool:
        """
        Poll until a media container is ready for publishing.
        Instagram processes images asynchronously before they can be published.
        """
        for _ in range(max_wait // 5):
            time.sleep(5)
            data = self._api_get(
                container_id,
                params={"fields": "status_code"},
            )
            status = data.get("status_code", "")
            if status == "FINISHED":
                return True
            if status == "ERROR":
                raise RuntimeError(f"Instagram container error: {data}")
        raise TimeoutError(f"Instagram container {container_id} not ready after {max_wait}s")

    def create_single_image_container(
        self, image_url: str, caption: str
    ) -> str:
        """
        Step 1 of Instagram publish: create a media container.
        Returns container_id.
        """
        data = self._api_post(
            f"{self.account_id}/media",
            params={
                "image_url": image_url,
                "caption": caption,
                "media_type": "IMAGE",
            },
        )
        container_id = data.get("id", "")
        logger.info(f"Instagram container created: {container_id}")
        return container_id

    def create_carousel_item_container(self, image_url: str) -> str:
        """Create a single carousel item container. Returns container_id."""
        data = self._api_post(
            f"{self.account_id}/media",
            params={
                "image_url": image_url,
                "is_carousel_item": True,
            },
        )
        return data.get("id", "")

    def create_carousel_container(
        self, item_ids: list[str], caption: str
    ) -> str:
        """Create the main carousel container. Returns container_id."""
        data = self._api_post(
            f"{self.account_id}/media",
            params={
                "media_type": "CAROUSEL",
                "children": ",".join(item_ids),
                "caption": caption,
            },
        )
        container_id = data.get("id", "")
        logger.info(f"Instagram carousel container created: {container_id}")
        return container_id

    def publish_container(self, container_id: str) -> str:
        """
        Step 2 of Instagram publish: publish a ready container.
        Returns the published media ID.
        """
        data = self._api_post(
            f"{self.account_id}/media_publish",
            params={"creation_id": container_id},
        )
        media_id = data.get("id", "")
        logger.info(f"Instagram post published: {media_id}")
        return media_id

    def post_single_image(
        self, image_url: str, caption: str
    ) -> str:
        """
        Publish a single image post to Instagram.
        image_url must be a public HTTPS URL (use Cloudinary).
        Returns published media ID.
        """
        container_id = self.create_single_image_container(image_url, caption)
        self._wait_for_container(container_id)
        return self.publish_container(container_id)

    def post_carousel(
        self, image_urls: list[str], caption: str
    ) -> str:
        """
        Publish a carousel post to Instagram.
        image_urls must all be public HTTPS URLs.
        Returns published media ID.
        """
        # Create item containers
        item_ids = []
        for url in image_urls[:10]:  # Instagram max 10 carousel items
            item_id = self.create_carousel_item_container(url)
            self._wait_for_container(item_id, max_wait=30)
            item_ids.append(item_id)

        if not item_ids:
            raise ValueError("No carousel items created")

        # Create and publish carousel container
        container_id = self.create_carousel_container(item_ids, caption)
        self._wait_for_container(container_id)
        return self.publish_container(container_id)

    def post_reel(self, video_url: str, caption: str) -> str:
        """
        Publish a Reel to Instagram.
        video_url must be a public HTTPS URL (use Cloudinary).
        Returns published media ID.
        """
        # Step 1: Create reel container
        data = self._api_post(
            f"{self.account_id}/media",
            params={
                "video_url": video_url,
                "caption": caption,
                "media_type": "REELS",
            },
        )
        container_id = data.get("id", "")
        logger.info(f"Instagram Reel container created: {container_id}")

        # Step 2: Wait for video processing (videos take longer — up to 5 min)
        self._wait_for_container(container_id, max_wait=300)

        # Step 3: Publish
        return self.publish_container(container_id)

    def publish(
        self,
        caption: str,
        image_urls: list[str],
    ) -> dict:
        """
        Main publish method.
        - Single URL → image post
        - Multiple URLs → carousel post
        Returns result dict.
        """
        try:
            if not image_urls:
                raise ValueError("Instagram requires at least one image URL")

            if len(image_urls) == 1:
                media_id = self.post_single_image(image_urls[0], caption)
                return {"success": True, "platform": "instagram", "id": media_id, "type": "image"}
            else:
                media_id = self.post_carousel(image_urls, caption)
                return {"success": True, "platform": "instagram", "id": media_id, "type": "carousel"}
        except Exception as e:
            logger.error(f"Instagram publish failed: {e}")
            return {"success": False, "platform": "instagram", "error": str(e)}

    def publish_reel(self, video_url: str, caption: str) -> dict:
        """Publish a Reel. Returns result dict."""
        try:
            media_id = self.post_reel(video_url, caption)
            return {"success": True, "platform": "instagram", "id": media_id, "type": "reel"}
        except Exception as e:
            logger.error(f"Instagram Reel publish failed: {e}")
            return {"success": False, "platform": "instagram", "error": str(e)}
