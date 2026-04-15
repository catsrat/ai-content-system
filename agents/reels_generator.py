"""
reels_generator.py — Generates Instagram Reels automatically.

Format:
- 9:16 vertical video (1080x1920)
- Dark background with news photo
- Bold text appears line by line
- AI voiceover (ElevenLabs)
- 15-30 seconds
"""

import os
import io
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from elevenlabs.client import ElevenLabs
from moviepy import (
    ImageClip, AudioFileClip,
    concatenate_videoclips,
)
from utils.logger import get_logger

logger = get_logger("reels_generator")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "reels")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")

W, H = 1080, 1920  # 9:16 vertical

THEME_COLORS = {
    "daily_brief":    {"highlight": (0, 180, 255),  "badge": "AI NEWS"},
    "learning":       {"highlight": (0, 220, 100),  "badge": "LEARN NOW"},
    "differentiator": {"highlight": (255, 80, 30),  "badge": "HOT TAKE"},
}

# ElevenLabs voice ID — Rachel (calm, professional news anchor)
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = [
        os.path.join(ASSETS_DIR, "Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _download_image(url: str):
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        logger.warning(f"Could not download image: {e}")
        return None


def _make_background(bg_img, bg_color=(10, 15, 40)) -> Image.Image:
    """Create 9:16 background from image or solid color."""
    if bg_img:
        iw, ih = bg_img.size
        scale = max(W / iw, H / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        bg_img = bg_img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - W) // 2
        top = (new_h - H) // 2
        bg_img = bg_img.crop((left, top, left + W, top + H))
        bg_img = ImageEnhance.Brightness(bg_img).enhance(0.35)
        bg_img = ImageEnhance.Color(bg_img).enhance(0.6)
        return bg_img
    else:
        return Image.new("RGB", (W, H), bg_color)


def _render_frame(
    text_lines_visible: list,
    all_lines: list,
    post_type: str,
    bg_img,
    badge_text: str,
    highlight_color: tuple,
) -> np.ndarray:
    """Render a single video frame with text overlay."""
    base = _make_background(bg_img)

    # Dark gradient overlay
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    for y in range(H):
        t = y / H
        alpha = int(40 + 180 * (t ** 1.3))
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    base = base.convert("RGBA")
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    # Top badge
    badge_font = _get_font(48, bold=True)
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbox[2] - bbox[0] + 48
    bh = 72
    bx = (W - bw) // 2
    by = 120
    # Rounded pill
    draw.rectangle([bx + 20, by, bx + bw - 20, by + bh], fill=(*highlight_color, 220))
    draw.rectangle([bx, by + 20, bx + bw, by + bh - 20], fill=(*highlight_color, 220))
    draw.ellipse([bx, by, bx + 40, by + 40], fill=(*highlight_color, 220))
    draw.ellipse([bx + bw - 40, by, bx + bw, by + 40], fill=(*highlight_color, 220))
    draw.ellipse([bx, by + bh - 40, bx + 40, by + bh], fill=(*highlight_color, 220))
    draw.ellipse([bx + bw - 40, by + bh - 40, bx + bw, by + bh], fill=(*highlight_color, 220))
    draw.text((bx + 24, by + 14), badge_text, font=badge_font, fill=(255, 255, 255))

    # Text lines — center of screen
    font_size = 88
    font = _get_font(font_size, bold=True)
    line_h = font_size + 28
    total_h = len(all_lines) * line_h
    start_y = (H - total_h) // 2 - 80

    HIGHLIGHT_TRIGGERS = [
        "ai", "openai", "google", "meta", "microsoft", "apple", "nvidia",
        "billion", "million", "%", "$", "fired", "layoffs", "banned",
        "warning", "breaking", "new", "free", "job", "jobs", "chatgpt",
        "gpt", "gemini", "claude", "llm", "agent", "agents", "robot",
    ]

    for i, line in enumerate(all_lines):
        if i >= len(text_lines_visible):
            break  # Only show visible lines
        words = line.split()
        # Calculate line width
        full_text = " ".join(words)
        bbox = draw.textbbox((0, 0), full_text, font=font)
        total_w = bbox[2] - bbox[0]
        x = (W - total_w) // 2
        y = start_y + i * line_h

        for word in words:
            clean = word.lower().strip(".,!?")
            is_highlight = any(t in clean for t in HIGHLIGHT_TRIGGERS)
            color = highlight_color if is_highlight else (255, 255, 255)

            # Shadow
            draw.text((x + 3, y + 3), word, font=font, fill=(0, 0, 0, 180))
            draw.text((x, y), word, font=font, fill=color)

            w_bbox = draw.textbbox((0, 0), word + " ", font=font)
            x += w_bbox[2] - w_bbox[0]

    # Accent line under last visible line
    if text_lines_visible:
        last_y = start_y + (len(text_lines_visible) - 1) * line_h + font_size + 16
        draw.rectangle([(W - 160) // 2, last_y, (W + 160) // 2, last_y + 6], fill=highlight_color)

    # Brand watermark bottom
    wm_font = _get_font(40, bold=True)
    handle = "@AI_TECH_NEWSS"
    bbox = draw.textbbox((0, 0), handle, font=wm_font)
    ww = bbox[2] - bbox[0]
    wh = bbox[3] - bbox[1]
    wx = (W - ww) // 2
    wy = H - wh - 80
    draw.rectangle([wx - 20, wy - 10, wx + ww + 20, wy + wh + 10], fill=(0, 0, 0, 140))
    draw.text((wx, wy), handle, font=wm_font, fill=(255, 255, 255))

    return np.array(base.convert("RGB"))


def _wrap_text(text: str, max_chars: int = 14) -> list:
    """Wrap text into short lines for video display."""
    words = text.split()[:12]  # Max 12 words
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:4]


def generate_voiceover(text: str, api_key: str, output_path: str) -> bool:
    """Generate AI voiceover using ElevenLabs."""
    try:
        client = ElevenLabs(api_key=api_key)
        audio = client.text_to_speech.convert(
            voice_id=VOICE_ID,
            text=text,
            model_id="eleven_turbo_v2",
            output_format="mp3_44100_128",
        )
        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        logger.info(f"Voiceover saved: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Voiceover generation failed: {e}")
        return False


def generate_reel(
    post_type: str,
    headline: str,
    script: str,
    brand_name: str = "AI_TECH_NEWSS",
    filename: str = None,
    background_image_url: str = None,
    elevenlabs_api_key: str = None,
) -> str:
    """
    Generate a complete Instagram Reel.

    Args:
        post_type: daily_brief | learning | differentiator
        headline: Short headline for visual text (max 8 words)
        script: Full voiceover script (15-25 seconds worth)
        filename: Output filename
        background_image_url: News article image URL
        elevenlabs_api_key: ElevenLabs API key
    """
    theme = THEME_COLORS.get(post_type, THEME_COLORS["daily_brief"])
    highlight = theme["highlight"]
    badge = theme["badge"]

    if not filename:
        filename = f"{post_type}_reel.mp4"
    output_path = os.path.join(OUTPUT_DIR, filename)

    # Download background image
    bg_img = _download_image(background_image_url)

    # Wrap headline into lines
    lines = _wrap_text(headline, max_chars=12)
    n_lines = len(lines)

    # Generate voiceover
    audio_path = output_path.replace(".mp4", "_audio.mp3")
    has_audio = False
    if elevenlabs_api_key:
        has_audio = generate_voiceover(script, elevenlabs_api_key, audio_path)

    # Generate unique background music
    import random
    import time
    from utils.music_generator import generate_background_music
    music_seed = int(time.time()) % 999999
    music_duration = 30.0  # Generate 30s, will be trimmed to video length
    music_path = output_path.replace(".mp4", "_music.wav")
    try:
        generate_background_music(post_type, music_duration, music_path, seed=music_seed)
        has_music = True
    except Exception as e:
        logger.warning(f"Music generation failed: {e}")
        has_music = False

    # Build video clips
    # Each line appears one at a time, then full text holds
    clips = []
    seconds_per_line = 1.2
    hold_duration = 2.0

    for i in range(1, n_lines + 1):
        frame = _render_frame(
            text_lines_visible=lines[:i],
            all_lines=lines,
            post_type=post_type,
            bg_img=bg_img,
            badge_text=badge,
            highlight_color=highlight,
        )
        duration = seconds_per_line if i < n_lines else hold_duration
        clip = ImageClip(frame, duration=duration)
        clips.append(clip)

    # Final frame holds for remaining audio duration
    if has_audio:
        try:
            audio_clip = AudioFileClip(audio_path)
            total_video_duration = sum(c.duration for c in clips)
            remaining = max(0, audio_clip.duration - total_video_duration)
            if remaining > 0:
                final_frame = _render_frame(
                    text_lines_visible=lines,
                    all_lines=lines,
                    post_type=post_type,
                    bg_img=bg_img,
                    badge_text=badge,
                    highlight_color=highlight,
                )
                clips.append(ImageClip(final_frame, duration=remaining))
        except Exception as e:
            logger.warning(f"Audio duration check failed: {e}")

    # Concatenate all clips
    video = concatenate_videoclips(clips, method="compose")

    # Mix voiceover + background music
    try:
        from moviepy import CompositeAudioClip
        audio_clips = []

        if has_audio:
            voiceover = AudioFileClip(audio_path).with_effects(
                [lambda c: c.with_volume_scaled(1.0)]
            )
            audio_clips.append(voiceover)

        if has_music and os.path.exists(music_path):
            music = AudioFileClip(music_path)
            # Trim music to video duration
            music = music.subclipped(0, min(music.duration, video.duration))
            # Lower music volume (20% so voiceover is clear)
            music = music.with_effects(
                [lambda c: c.with_volume_scaled(0.20)]
            )
            audio_clips.append(music)

        if audio_clips:
            mixed = CompositeAudioClip(audio_clips)
            video = video.with_audio(mixed)

    except Exception as e:
        logger.warning(f"Audio mixing failed: {e}")
        # Fallback: just add voiceover without music
        if has_audio:
            try:
                video = video.with_audio(AudioFileClip(audio_path))
            except Exception:
                pass

    # Export
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    # Cleanup temp files
    for path in [audio_path, music_path]:
        if os.path.exists(path):
            os.remove(path)

    logger.info(f"Reel saved: {output_path}")
    return output_path
