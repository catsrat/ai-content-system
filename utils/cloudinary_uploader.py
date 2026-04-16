"""
cloudinary_uploader.py — Uploads images to Cloudinary and returns public URLs.

Instagram requires a public HTTPS URL for images before posting.
Cloudinary free tier is enough for this system.

Get credentials: cloudinary.com → free account → Dashboard
"""

import cloudinary
import cloudinary.uploader
from utils.logger import get_logger

logger = get_logger("cloudinary")


def init_cloudinary(cloud_name: str, api_key: str, api_secret: str) -> None:
    """Initialize Cloudinary with credentials."""
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


def upload_image(
    file_path: str,
    folder: str = "ai-content-system",
    public_id: str = None,
) -> str:
    """
    Upload an image file to Cloudinary.
    Returns the secure public URL of the uploaded image.
    """
    try:
        upload_params = {
            "folder": folder,
            "resource_type": "image",
            "overwrite": True,
        }
        if public_id:
            upload_params["public_id"] = public_id

        result = cloudinary.uploader.upload(file_path, **upload_params)
        url = result.get("secure_url", "")
        logger.info(f"Uploaded to Cloudinary: {url}")
        return url
    except Exception as e:
        logger.error(f"Cloudinary upload failed for {file_path}: {e}")
        raise


def upload_images(file_paths: list[str], folder: str = "ai-content-system") -> list[str]:
    """Upload multiple images. Returns list of public URLs."""
    urls = []
    for path in file_paths:
        try:
            url = upload_image(path, folder=folder)
            urls.append(url)
        except Exception as e:
            logger.error(f"Skipping {path} due to upload error: {e}")
    return urls


def upload_video(
    file_path: str,
    folder: str = "ai-content-system",
    public_id: str = None,
) -> str:
    """
    Upload a video file to Cloudinary.
    Returns the secure public URL of the uploaded video.
    """
    try:
        upload_params = {
            "folder": folder,
            "resource_type": "video",
            "overwrite": True,
        }
        if public_id:
            upload_params["public_id"] = public_id

        result = cloudinary.uploader.upload(file_path, **upload_params)
        url = result.get("secure_url", "")
        logger.info(f"Video uploaded to Cloudinary: {url}")
        return url
    except Exception as e:
        logger.error(f"Cloudinary video upload failed for {file_path}: {e}")
        raise
