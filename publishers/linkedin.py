"""
linkedin.py — Posts to LinkedIn via the LinkedIn Marketing API.

Supports:
  - Text posts to a Company Page
  - Posts with images (via asset upload)

Requirements:
  - LinkedIn Developer App with r_organization_social + w_organization_social
  - Company Page (Organization)
  - Access token with appropriate scopes

Get credentials: linkedin.com/developers → Create App
"""

import requests
from utils.logger import get_logger

logger = get_logger("linkedin")

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"


class LinkedInPublisher:
    def __init__(self, access_token: str, organization_id: str):
        self.access_token = access_token
        self.organization_id = organization_id
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        self.org_urn = f"urn:li:organization:{organization_id}"

    def _register_image_upload(self) -> tuple[str, str]:
        """
        Register an image upload with LinkedIn.
        Returns (upload_url, asset_urn).
        """
        body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.org_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }

        resp = requests.post(
            f"{LINKEDIN_API_BASE}/assets?action=registerUpload",
            headers=self.headers,
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        upload_url = (
            data["value"]["uploadMechanism"]
            ["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
            ["uploadUrl"]
        )
        asset_urn = data["value"]["asset"]
        return upload_url, asset_urn

    def _upload_image(self, image_path: str) -> str:
        """Upload an image to LinkedIn and return the asset URN."""
        upload_url, asset_urn = self._register_image_upload()

        with open(image_path, "rb") as f:
            upload_headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream",
            }
            resp = requests.put(upload_url, headers=upload_headers, data=f, timeout=30)
            resp.raise_for_status()

        logger.info(f"LinkedIn image uploaded: {asset_urn}")
        return asset_urn

    def post_text(self, text: str) -> str:
        """Post a text-only update to the company page. Returns post URN."""
        body = {
            "author": self.org_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        resp = requests.post(
            f"{LINKEDIN_API_BASE}/ugcPosts",
            headers=self.headers,
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        post_id = resp.headers.get("x-restli-id", resp.json().get("id", ""))
        logger.info(f"LinkedIn post published: {post_id}")
        return post_id

    def post_with_image(self, text: str, image_path: str) -> str:
        """Post a text + image update to the company page. Returns post URN."""
        asset_urn = self._upload_image(image_path)

        body = {
            "author": self.org_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [
                        {
                            "status": "READY",
                            "media": asset_urn,
                        }
                    ],
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        resp = requests.post(
            f"{LINKEDIN_API_BASE}/ugcPosts",
            headers=self.headers,
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        post_id = resp.headers.get("x-restli-id", resp.json().get("id", ""))
        logger.info(f"LinkedIn post with image published: {post_id}")
        return post_id

    def publish(self, text: str, image_path: str = None) -> dict:
        """Main publish method. Returns result dict."""
        try:
            if image_path:
                post_id = self.post_with_image(text, image_path)
            else:
                post_id = self.post_text(text)
            return {"success": True, "platform": "linkedin", "id": post_id}
        except Exception as e:
            logger.error(f"LinkedIn publish failed: {e}")
            return {"success": False, "platform": "linkedin", "error": str(e)}
