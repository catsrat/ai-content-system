"""
config.py — Central configuration loader.
Reads all environment variables and exposes them as a typed Config object.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Anthropic
    anthropic_api_key: str

    # News
    news_api_key: str

    # Canva
    canva_client_id: str
    canva_client_secret: str
    canva_access_token: str

    # Cloudinary
    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str

    # X / Twitter
    x_api_key: str
    x_api_secret: str
    x_access_token: str
    x_access_token_secret: str

    # LinkedIn
    linkedin_client_id: str
    linkedin_client_secret: str
    linkedin_access_token: str
    linkedin_organization_id: str

    # Instagram / Meta
    instagram_access_token: str
    instagram_business_account_id: str

    # ElevenLabs
    elevenlabs_api_key: str

    # Brand
    brand_name: str
    brand_niche: str
    brand_tone: str


def load_config() -> Config:
    """Load and validate config. Only core keys are required."""
    missing = []

    def require(key: str) -> str:
        val = os.getenv(key, "")
        if not val:
            missing.append(key)
        return val

    def optional(key: str) -> str:
        return os.getenv(key, "")

    cfg = Config(
        # Required
        anthropic_api_key=require("ANTHROPIC_API_KEY"),
        news_api_key=require("NEWS_API_KEY"),
        x_api_key=require("X_API_KEY"),
        x_api_secret=require("X_API_SECRET"),
        x_access_token=require("X_ACCESS_TOKEN"),
        x_access_token_secret=require("X_ACCESS_TOKEN_SECRET"),

        # Optional — system skips platform if missing
        canva_client_id=optional("CANVA_CLIENT_ID"),
        canva_client_secret=optional("CANVA_CLIENT_SECRET"),
        canva_access_token=optional("CANVA_ACCESS_TOKEN"),
        cloudinary_cloud_name=optional("CLOUDINARY_CLOUD_NAME"),
        cloudinary_api_key=optional("CLOUDINARY_API_KEY"),
        cloudinary_api_secret=optional("CLOUDINARY_API_SECRET"),
        linkedin_client_id=optional("LINKEDIN_CLIENT_ID"),
        linkedin_client_secret=optional("LINKEDIN_CLIENT_SECRET"),
        linkedin_access_token=optional("LINKEDIN_ACCESS_TOKEN"),
        linkedin_organization_id=optional("LINKEDIN_ORGANIZATION_ID"),
        instagram_access_token=optional("INSTAGRAM_ACCESS_TOKEN"),
        instagram_business_account_id=optional("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
        elevenlabs_api_key=optional("ELEVENLABS_API_KEY"),

        brand_name=os.getenv("BRAND_NAME", "AI Career Hub"),
        brand_niche=os.getenv("BRAND_NICHE", "AI Career & Tools"),
        brand_tone=os.getenv("BRAND_TONE", "confident, sharp, career-focused"),
    )

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in your keys."
        )

    return cfg
