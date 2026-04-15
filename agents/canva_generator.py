"""
canva_generator.py — Generates branded images using the Canva Connect API.

Flow:
  1. Find a matching template by post type
  2. Create a design from the template
  3. Fill in the headline text
  4. Export as PNG
  5. Return local file path

Canva Connect API docs: https://www.canva.com/developers/docs/connect/
Requires: Canva Pro + Connect API access token
"""

import os
import time
import requests
from utils.logger import get_logger

logger = get_logger("canva_generator")

CANVA_API_BASE = "https://api.canva.com/rest/v1"

# Map post types to Canva template keywords to search for
TEMPLATE_KEYWORDS = {
    "daily_brief":     "AI news announcement dark",
    "learning":        "education tips carousel blue",
    "differentiator":  "bold opinion quote social media",
}

# Output directory for downloaded images
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class CanvaGenerator:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        resp = requests.get(
            f"{CANVA_API_BASE}{path}",
            headers=self.headers,
            params=params or {},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            f"{CANVA_API_BASE}{path}",
            headers=self.headers,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def search_templates(self, query: str) -> list[dict]:
        """Search Canva templates by keyword. Returns list of template objects."""
        try:
            data = self._get("/designs", params={"query": query, "type": "SOCIAL_MEDIA_SQUARE"})
            return data.get("items", [])
        except Exception as e:
            logger.warning(f"Template search failed for '{query}': {e}")
            return []

    def create_design_from_template(self, template_id: str, title: str) -> str:
        """Create a new design from a template. Returns design_id."""
        body = {
            "design_type": {"type": "SOCIAL_MEDIA_SQUARE"},
            "title": title,
        }
        if template_id:
            body["asset_id"] = template_id

        data = self._post("/designs", body)
        design_id = data.get("design", {}).get("id", "")
        logger.info(f"Created Canva design: {design_id}")
        return design_id

    def update_design_text(self, design_id: str, headline: str) -> bool:
        """
        Update text elements in a design.
        NOTE: Canva Connect API text editing requires knowing element IDs.
        For simplicity we use the autofill API if a brand template is set up.
        """
        try:
            # Canva Autofill: fills a brand template with data
            body = {
                "title": headline,
                "data": [
                    {
                        "type": "text",
                        "name": "headline",
                        "text": headline,
                    }
                ],
            }
            self._post(f"/designs/{design_id}/autofill", body)
            return True
        except Exception as e:
            logger.warning(f"Text update skipped (autofill not configured): {e}")
            return False

    def export_design(self, design_id: str, format: str = "PNG") -> str:
        """
        Export a Canva design and return the download URL.
        Polls until export is ready (Canva exports are async).
        """
        # Start export job
        body = {"design_id": design_id, "format": format}
        data = self._post("/exports", body)
        export_id = data.get("job", {}).get("id", "")

        if not export_id:
            raise ValueError("Canva export job ID not returned")

        # Poll for completion (max 60s)
        for _ in range(20):
            time.sleep(3)
            status_data = self._get(f"/exports/{export_id}")
            job = status_data.get("job", {})
            if job.get("status") == "success":
                urls = job.get("urls", [])
                if urls:
                    return urls[0]
            elif job.get("status") == "failed":
                raise RuntimeError(f"Canva export failed: {job}")

        raise TimeoutError("Canva export timed out after 60s")

    def download_image(self, url: str, filename: str) -> str:
        """Download image from URL and save locally. Returns file path."""
        filepath = os.path.join(OUTPUT_DIR, filename)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(resp.content)
        logger.info(f"Image saved: {filepath}")
        return filepath

    def generate_post_image(
        self,
        post_type: str,
        headline: str,
        filename: str,
    ) -> str:
        """
        Full pipeline: search template → create design → export → download.
        Returns local file path of the generated image.
        """
        logger.info(f"Generating Canva image for [{post_type}]: {headline}")

        # 1. Search for a matching template
        keyword = TEMPLATE_KEYWORDS.get(post_type, "AI social media")
        templates = self.search_templates(keyword)

        template_id = templates[0].get("id", "") if templates else ""

        # 2. Create design
        design_id = self.create_design_from_template(
            template_id=template_id,
            title=f"{post_type.replace('_', ' ').title()} — {headline[:40]}",
        )

        if not design_id:
            raise RuntimeError("Failed to create Canva design")

        # 3. Try to update text (optional — works if autofill is configured)
        self.update_design_text(design_id, headline)

        # 4. Export
        download_url = self.export_design(design_id)

        # 5. Download locally
        filepath = self.download_image(download_url, filename)
        return filepath

    def generate_carousel_slides(
        self,
        post_type: str,
        slides: list[str],
        base_filename: str,
    ) -> list[str]:
        """
        Generate multiple slides for a carousel post.
        Returns list of local file paths.
        """
        paths = []
        for i, slide_text in enumerate(slides):
            filename = f"{base_filename}_slide_{i + 1}.png"
            try:
                path = self.generate_post_image(
                    post_type=post_type,
                    headline=slide_text,
                    filename=filename,
                )
                paths.append(path)
            except Exception as e:
                logger.error(f"Slide {i + 1} generation failed: {e}")
        return paths
