"""
reels_generator.py — Generates Instagram Reels automatically.

Format:
- 9:16 vertical video (1080x1920)
- Ken Burns zoom effect on background image
- Text fades in line by line (smooth, not hard cuts)
- Animated progress bar
- AI voiceover (ElevenLabs → Edge TTS fallback)
- 15-30 seconds
"""

import os
import io
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from elevenlabs.client import ElevenLabs
from moviepy import ImageClip, ImageSequenceClip, AudioFileClip, concatenate_videoclips
from utils.logger import get_logger

logger = get_logger("reels_generator")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "reels")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")

W, H = 1080, 1920  # 9:16 vertical
FPS = 15
FADE_FRAMES = 12  # 0.8s fade-in for each new text line

THEME_COLORS = {
    "daily_brief":    {"highlight": (0, 180, 255),  "badge": "AI NEWS",    "bg": (5, 10, 30)},
    "learning":       {"highlight": (0, 220, 100),  "badge": "LEARN NOW",  "bg": (5, 20, 10)},
    "differentiator": {"highlight": (255, 80, 30),  "badge": "HOT TAKE",   "bg": (30, 8, 5)},
    "workflow":       {"highlight": (180, 80, 255), "badge": "FREE TOOL",  "bg": (15, 5, 30)},
}

VOICE_ID = "pNInz6obpgDQGcFmaJgB"


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


def _make_background(bg_img, bg_color=(10, 15, 40), zoom: float = 1.0) -> Image.Image:
    """Create 9:16 background with Ken Burns zoom applied."""
    if bg_img:
        iw, ih = bg_img.size
        # Zoom by cropping a smaller region then scaling up to full size
        crop_w = int(W / zoom)
        crop_h = int(H / zoom)
        scale = max(crop_w / iw, crop_h / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        resized = bg_img.resize((new_w, new_h), Image.BILINEAR)
        left = (new_w - crop_w) // 2
        top = (new_h - crop_h) // 2
        cropped = resized.crop((left, top, left + crop_w, top + crop_h))
        result = cropped.resize((W, H), Image.BILINEAR)
        result = ImageEnhance.Brightness(result).enhance(0.32)
        result = ImageEnhance.Color(result).enhance(0.55)
        return result
    else:
        return Image.new("RGB", (W, H), bg_color)


def _ease_in_out(t: float) -> float:
    """Smooth ease-in-out curve for animations."""
    return t * t * (3 - 2 * t)


def _render_frame(
    text_lines_visible: list,
    all_lines: list,
    post_type: str,
    bg_img,
    badge_text: str,
    highlight_color: tuple,
    zoom: float = 1.0,
    newest_line_alpha: float = 1.0,   # 0.0–1.0 fade-in for the last revealed line
    progress: float = 0.0,            # 0.0–1.0 for progress bar
    bg_color: tuple = (10, 15, 40),
) -> np.ndarray:
    """Render one video frame with Ken Burns zoom and text fade-in."""
    base = _make_background(bg_img, bg_color=bg_color, zoom=zoom)

    # Dark gradient overlay — stronger at bottom for text readability
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    for y in range(H):
        t = y / H
        alpha = int(30 + 200 * (t ** 1.2))
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    # Extra dark band in center for text
    for y in range(H // 3, 2 * H // 3):
        ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, 60))
    base = base.convert("RGBA")
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    # ── Top badge ───────────────────────────────────────────────
    badge_font = _get_font(44, bold=True)
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbox[2] - bbox[0] + 48
    bh = 68
    bx = (W - bw) // 2
    by = 110
    r = min(34, bw // 2, bh // 2)  # guard: r must not exceed half the pill size
    hc = highlight_color
    # Rounded pill background
    if bx + r < bx + bw - r:
        draw.rectangle([bx + r, by, bx + bw - r, by + bh], fill=(*hc, 230))
    if by + r < by + bh - r:
        draw.rectangle([bx, by + r, bx + bw, by + bh - r], fill=(*hc, 230))
    draw.ellipse([bx, by, bx + r*2, by + r*2], fill=(*hc, 230))
    draw.ellipse([bx + bw - r*2, by, bx + bw, by + r*2], fill=(*hc, 230))
    draw.ellipse([bx, by + bh - r*2, bx + r*2, by + bh], fill=(*hc, 230))
    draw.ellipse([bx + bw - r*2, by + bh - r*2, bx + bw, by + bh], fill=(*hc, 230))
    draw.text((bx + 24, by + 12), badge_text, font=badge_font, fill=(255, 255, 255))

    # ── Headline text — center of screen ────────────────────────
    HIGHLIGHT_TRIGGERS = [
        "ai", "openai", "google", "meta", "microsoft", "apple", "nvidia",
        "billion", "million", "%", "$", "fired", "layoffs", "banned",
        "warning", "breaking", "new", "free", "job", "jobs", "chatgpt",
        "gpt", "gemini", "claude", "llm", "agent", "agents", "robot",
    ]

    font_size = 96
    font = _get_font(font_size, bold=True)
    line_h = font_size + 32
    total_h = len(all_lines) * line_h
    start_y = (H - total_h) // 2 - 60

    for i, line in enumerate(all_lines):
        if i >= len(text_lines_visible):
            break

        # Determine alpha for this line
        is_newest = (i == len(text_lines_visible) - 1)
        line_alpha = newest_line_alpha if is_newest else 1.0

        # Slide-up offset for newest line (fades in from 60px below)
        slide_offset = int(60 * (1.0 - line_alpha)) if is_newest else 0

        words = line.split()
        full_text = " ".join(words)
        bbox = draw.textbbox((0, 0), full_text, font=font)
        total_w = bbox[2] - bbox[0]
        x = (W - total_w) // 2
        y = start_y + i * line_h + slide_offset

        for word in words:
            clean = word.lower().strip(".,!?")
            is_highlight = any(t in clean for t in HIGHLIGHT_TRIGGERS)

            if is_highlight:
                color = tuple(int(c * line_alpha) for c in highlight_color)
            else:
                v = int(255 * line_alpha)
                color = (v, v, v)

            shadow_alpha = int(180 * line_alpha)
            # Shadow
            draw.text((x + 3, y + 3), word, font=font, fill=(0, 0, 0, shadow_alpha))
            draw.text((x, y), word, font=font, fill=color)

            w_bbox = draw.textbbox((0, 0), word + " ", font=font)
            x += w_bbox[2] - w_bbox[0]

    # ── Accent line under last visible text ─────────────────────
    if text_lines_visible:
        last_y = start_y + (len(text_lines_visible) - 1) * line_h + font_size + 20
        bar_w = int(200 * newest_line_alpha)
        if bar_w > 1:
            draw.rectangle(
                [(W - bar_w) // 2, last_y, (W + bar_w) // 2, last_y + 5],
                fill=(*highlight_color, int(220 * newest_line_alpha))
            )

    # ── Progress bar at bottom ───────────────────────────────────
    bar_y = H - 140
    # Track (background)
    draw.rectangle([60, bar_y, W - 60, bar_y + 6], fill=(255, 255, 255, 40))
    # Fill
    fill_w = int((W - 120) * progress)
    if fill_w > 0:
        draw.rectangle([60, bar_y, 60 + fill_w, bar_y + 6], fill=(*highlight_color, 200))
        # Glow dot at end
        dot_x = 60 + fill_w
        draw.ellipse([dot_x - 8, bar_y - 5, dot_x + 8, bar_y + 11], fill=(*highlight_color, 255))

    # ── Brand watermark ──────────────────────────────────────────
    wm_font = _get_font(38, bold=True)
    handle = "@AI_TECH_NEWSS"
    bbox = draw.textbbox((0, 0), handle, font=wm_font)
    ww = bbox[2] - bbox[0]
    wh = bbox[3] - bbox[1]
    wx = (W - ww) // 2
    wy = H - wh - 52
    draw.rectangle([wx - 20, wy - 8, wx + ww + 20, wy + wh + 8], fill=(0, 0, 0, 150))
    draw.text((wx, wy), handle, font=wm_font, fill=(255, 255, 255))

    return np.array(base.convert("RGB"))


def _wrap_text(text: str, max_chars: int = 14) -> list:
    """Wrap text into short lines for video display."""
    words = text.split()[:12]
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


def _make_animated_clip(
    text_lines_visible: list,
    all_lines: list,
    post_type: str,
    bg_img,
    badge_text: str,
    highlight_color: tuple,
    duration: float,
    time_start: float,
    total_duration: float,
    bg_color: tuple,
    fade_in: bool = True,
):
    """
    Generate an animated clip with Ken Burns zoom + text fade-in.
    Uses ImageSequenceClip — requires Railway Hobby plan (8GB RAM).
    """
    n_frames = max(1, int(duration * FPS))
    frames = []

    for i in range(n_frames):
        global_t = min((time_start + i / FPS) / max(total_duration, 1), 1.0)

        # Ken Burns: background zooms 1.0 → 1.18 across full reel (clearly visible)
        zoom = 1.0 + 0.18 * _ease_in_out(global_t)

        # Progress bar
        prog = global_t

        # Text fade-in for newest line (first FADE_FRAMES frames)
        if fade_in and i < FADE_FRAMES:
            newest_alpha = min(1.0, _ease_in_out(i / max(FADE_FRAMES - 1, 1)))
        else:
            newest_alpha = 1.0

        frame = _render_frame(
            text_lines_visible=text_lines_visible,
            all_lines=all_lines,
            post_type=post_type,
            bg_img=bg_img,
            badge_text=badge_text,
            highlight_color=highlight_color,
            zoom=zoom,
            newest_line_alpha=newest_alpha,
            progress=prog,
            bg_color=bg_color,
        )
        frames.append(frame)

    return ImageSequenceClip(frames, fps=FPS)


def _generate_voiceover_edge_tts(text: str, output_path: str) -> bool:
    """Generate voiceover using Microsoft Edge TTS (free, no API key)."""
    try:
        import asyncio
        import edge_tts
        EDGE_VOICE = "en-US-GuyNeural"

        async def _run():
            communicate = edge_tts.Communicate(text, EDGE_VOICE)
            mp3_path = output_path.replace(".mp3", "_edge.mp3")
            await communicate.save(mp3_path)
            return mp3_path

        mp3_path = asyncio.run(_run())
        if os.path.exists(mp3_path):
            os.rename(mp3_path, output_path)
        logger.info(f"Edge TTS voiceover saved: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Edge TTS voiceover failed: {e}")
        return False


def generate_voiceover(text: str, api_key: str, output_path: str) -> bool:
    """Try ElevenLabs first, fall back to Edge TTS."""
    if api_key:
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
            logger.info(f"ElevenLabs voiceover saved: {output_path}")
            return True
        except Exception as e:
            logger.warning(f"ElevenLabs failed ({e}), falling back to Edge TTS...")
    return _generate_voiceover_edge_tts(text, output_path)


def generate_reel(
    post_type: str,
    headline: str,
    script: str,
    slides: list = None,
    brand_name: str = "AI_TECH_NEWSS",
    filename: str = None,
    background_image_url: str = None,
    elevenlabs_api_key: str = None,
) -> str:
    theme = THEME_COLORS.get(post_type, THEME_COLORS["daily_brief"])
    highlight = theme["highlight"]
    badge = theme["badge"]
    bg_color = theme.get("bg", (10, 15, 40))

    if not filename:
        filename = f"{post_type}_reel.mp4"
    output_path = os.path.join(OUTPUT_DIR, filename)

    bg_img = _download_image(background_image_url)

    # Use Claude-generated slides if available, else fall back to wrapped headline
    if slides and len(slides) >= 2:
        lines = [s.strip().upper() for s in slides[:5] if s.strip()]
    else:
        lines = _wrap_text(headline, max_chars=14)
    n_lines = len(lines)

    # Generate voiceover
    audio_path = output_path.replace(".mp4", "_audio.mp3")
    has_audio = False
    if script:
        has_audio = generate_voiceover(script, elevenlabs_api_key, audio_path)

    # Generate background music
    import time
    from utils.music_generator import generate_background_music
    music_seed = int(time.time()) % 999999
    music_path = output_path.replace(".mp4", "_music.wav")
    has_music = False
    try:
        generate_background_music(post_type, 35.0, music_path, seed=music_seed)
        has_music = True
    except Exception as e:
        logger.warning(f"Music generation failed: {e}")

    # Calculate total video duration
    seconds_per_line = 1.4
    hold_duration = 3.0

    # If audio available, match video length to audio
    audio_duration = 0
    if has_audio:
        try:
            audio_duration = AudioFileClip(audio_path).duration
        except Exception:
            pass

    text_duration = n_lines * seconds_per_line + hold_duration
    total_duration = max(text_duration, audio_duration) if audio_duration else text_duration

    # ── Build animated clips (Ken Burns + text fade-in) ──────────
    clips = []
    time_cursor = 0.0

    for i in range(1, n_lines + 1):
        duration = seconds_per_line if i < n_lines else hold_duration
        clip = _make_animated_clip(
            text_lines_visible=lines[:i],
            all_lines=lines,
            post_type=post_type,
            bg_img=bg_img,
            badge_text=badge,
            highlight_color=highlight,
            duration=duration,
            time_start=time_cursor,
            total_duration=total_duration,
            bg_color=bg_color,
            fade_in=True,
        )
        clips.append(clip)
        time_cursor += duration

    # Hold final frame for remaining audio duration
    if audio_duration > time_cursor:
        remaining = audio_duration - time_cursor
        clip = _make_animated_clip(
            text_lines_visible=lines,
            all_lines=lines,
            post_type=post_type,
            bg_img=bg_img,
            badge_text=badge,
            highlight_color=highlight,
            duration=remaining,
            time_start=time_cursor,
            total_duration=total_duration,
            bg_color=bg_color,
            fade_in=False,
        )
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")

    # Mix audio
    try:
        from moviepy import CompositeAudioClip
        audio_clips = []

        if has_audio:
            voiceover = AudioFileClip(audio_path)
            audio_clips.append(voiceover)

        if has_music and os.path.exists(music_path):
            music = AudioFileClip(music_path)
            music = music.subclipped(0, min(music.duration, video.duration))
            music = music.with_volume_scaled(0.18)
            audio_clips.append(music)

        if audio_clips:
            mixed = CompositeAudioClip(audio_clips)
            video = video.with_audio(mixed)

    except Exception as e:
        logger.warning(f"Audio mixing failed: {e}")
        if has_audio:
            try:
                video = video.with_audio(AudioFileClip(audio_path))
            except Exception:
                pass

    # Export
    video.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=1,
        ffmpeg_params=["-crf", "28"],
        logger=None,
    )

    # Cleanup temp files
    for path in [audio_path, music_path]:
        if os.path.exists(path):
            os.remove(path)

    logger.info(f"Reel saved: {output_path}")
    return output_path
