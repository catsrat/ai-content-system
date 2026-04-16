"""
reels_generator.py — Generates Instagram Reels automatically.

Format:
- 9:16 vertical video (1080x1920)
- ONE slide shown at a time (not stacked) — each slide replaces the previous
- Auto-sized text: always fits the screen, never gets cut off
- Ken Burns zoom on background
- Smooth fade-in per slide
- Slide counter (1/4, 2/4...)
- AI voiceover + background music
"""

import os
import io
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from elevenlabs.client import ElevenLabs
from moviepy import ImageSequenceClip, AudioFileClip, concatenate_videoclips
from utils.logger import get_logger

logger = get_logger("reels_generator")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "reels")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")

W, H = 1080, 1920
FPS = 15
FADE_FRAMES = 10  # 0.67s fade-in per slide

THEME_COLORS = {
    "daily_brief":    {"highlight": (0, 180, 255),  "badge": "AI NEWS",    "bg": (5, 10, 30)},
    "learning":       {"highlight": (0, 220, 100),  "badge": "LEARN NOW",  "bg": (5, 20, 10)},
    "differentiator": {"highlight": (255, 80, 30),  "badge": "HOT TAKE",   "bg": (30, 8, 5)},
    "workflow":       {"highlight": (180, 80, 255), "badge": "FREE TOOL",  "bg": (15, 5, 30)},
}

VOICE_ID = "pNInz6obpgDQGcFmaJgB"

HIGHLIGHT_TRIGGERS = [
    "ai", "openai", "google", "meta", "microsoft", "apple", "nvidia",
    "billion", "million", "%", "$", "free", "fired", "layoffs", "banned",
    "breaking", "new", "job", "jobs", "chatgpt", "gpt", "gemini",
    "claude", "llm", "agent", "agents", "robot", "warning",
]


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
    if bg_img:
        iw, ih = bg_img.size
        crop_w = int(W / zoom)
        crop_h = int(H / zoom)
        scale = max(crop_w / iw, crop_h / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        resized = bg_img.resize((new_w, new_h), Image.BILINEAR)
        left = (new_w - crop_w) // 2
        top = (new_h - crop_h) // 2
        cropped = resized.crop((left, top, left + crop_w, top + crop_h))
        result = cropped.resize((W, H), Image.BILINEAR)
        result = ImageEnhance.Brightness(result).enhance(0.30)
        result = ImageEnhance.Color(result).enhance(0.5)
        return result
    else:
        return Image.new("RGB", (W, H), bg_color)


def _ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


def _auto_fit_text(draw, text: str, max_width: int, max_size: int = 180, min_size: int = 50) -> tuple:
    """Return (font, size) that fits text within max_width."""
    for size in range(max_size, min_size - 1, -6):
        font = _get_font(size, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return font, size
    return _get_font(min_size, bold=True), min_size


def _wrap_to_lines(text: str, draw, max_width: int, font_size: int) -> list:
    """Wrap text into lines that each fit within max_width at font_size."""
    font = _get_font(font_size, bold=True)
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _render_slide(
    slide_text: str,
    slide_idx: int,
    total_slides: int,
    bg_img,
    badge_text: str,
    highlight_color: tuple,
    zoom: float = 1.0,
    alpha: float = 1.0,
    slide_offset_y: int = 0,
    bg_color: tuple = (10, 15, 40),
) -> np.ndarray:
    """
    Render ONE slide — text fills the screen, auto-sized, never cut off.
    Each slide replaces the previous (not stacked).
    """
    base = _make_background(bg_img, bg_color=bg_color, zoom=zoom)

    # Gradient overlay
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov = ImageDraw.Draw(overlay)
    for y in range(H):
        t = y / H
        a = int(15 + 220 * (t ** 1.4))
        ov.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    # Extra darkening in text zone
    for y in range(H // 3, 2 * H // 3 + 200):
        if 0 <= y < H:
            ov.line([(0, y), (W, y)], fill=(0, 0, 0, 70))

    base = base.convert("RGBA")
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    # ── Badge ────────────────────────────────────────────────────
    badge_font = _get_font(44, bold=True)
    bbbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbbox[2] - bbbox[0] + 48
    bh = 68
    bx = (W - bw) // 2
    by = 110
    r = min(34, bw // 2, bh // 2)
    hc = highlight_color
    if bx + r < bx + bw - r:
        draw.rectangle([bx + r, by, bx + bw - r, by + bh], fill=(*hc, 230))
    if by + r < by + bh - r:
        draw.rectangle([bx, by + r, bx + bw, by + bh - r], fill=(*hc, 230))
    for ex, ey in [(bx, by), (bx+bw-r*2, by), (bx, by+bh-r*2), (bx+bw-r*2, by+bh-r*2)]:
        draw.ellipse([ex, ey, ex+r*2, ey+r*2], fill=(*hc, 230))
    draw.text((bx + 24, by + 12), badge_text, font=badge_font, fill=(255, 255, 255))

    # ── Slide counter ─────────────────────────────────────────────
    ctr_font = _get_font(34, bold=False)
    ctr = f"{slide_idx + 1}/{total_slides}"
    cbbox = draw.textbbox((0, 0), ctr, font=ctr_font)
    draw.text((W - (cbbox[2]-cbbox[0]) - 50, 122), ctr, font=ctr_font,
              fill=(int(255*alpha), int(255*alpha), int(255*alpha), int(160*alpha)))

    # ── Main text — auto-sized, ONE slide at a time ───────────────
    MAX_W = W - 80  # 40px padding each side

    # First find the font size that fits the full text on one line
    temp_img = Image.new("RGB", (10, 10))
    temp_draw = ImageDraw.Draw(temp_img)
    font, font_size = _auto_fit_text(temp_draw, slide_text, MAX_W, max_size=200, min_size=60)

    # If font_size is small (long text), wrap into 2 lines at a bigger size
    if font_size < 90 and len(slide_text.split()) > 3:
        # Try 2-line layout at larger size
        two_line_size = min(160, font_size * 2)
        wrapped = _wrap_to_lines(slide_text, temp_draw, MAX_W, two_line_size)
        if len(wrapped) <= 3:
            font_size = two_line_size
            font = _get_font(font_size, bold=True)
            lines = wrapped
        else:
            lines = [slide_text]
    else:
        lines = [slide_text]

    line_h = font_size + 28
    total_text_h = len(lines) * line_h
    base_y = (H - total_text_h) // 2 - 20

    for i, line in enumerate(lines):
        words = line.split()
        full_line = " ".join(words)
        lbbox = draw.textbbox((0, 0), full_line, font=font)
        lw = lbbox[2] - lbbox[0]
        x = (W - lw) // 2
        y = base_y + i * line_h + slide_offset_y

        for word in words:
            clean = word.lower().strip(".,!?$%#@")
            is_hi = any(t in clean for t in HIGHLIGHT_TRIGGERS)

            if is_hi:
                color = tuple(int(c * alpha) for c in highlight_color)
            else:
                v = int(255 * alpha)
                color = (v, v, v)

            # Drop shadow
            draw.text((x + 4, y + 4), word, font=font, fill=(0, 0, 0, int(200 * alpha)))
            draw.text((x, y), word, font=font, fill=color)

            wbbox = draw.textbbox((0, 0), word + " ", font=font)
            x += wbbox[2] - wbbox[0]

    # ── Accent bar ────────────────────────────────────────────────
    acc_y = base_y + total_text_h + 20
    acc_w = int(200 * alpha)
    if acc_w > 2:
        draw.rectangle([(W-acc_w)//2, acc_y, (W+acc_w)//2, acc_y+6],
                       fill=(*highlight_color, int(220*alpha)))

    # ── Progress bar ──────────────────────────────────────────────
    pb_y = H - 130
    progress = (slide_idx + alpha) / max(total_slides, 1)
    draw.rectangle([60, pb_y, W-60, pb_y+6], fill=(255, 255, 255, 35))
    fw = int((W - 120) * min(progress, 1.0))
    if fw > 0:
        draw.rectangle([60, pb_y, 60+fw, pb_y+6], fill=(*highlight_color, 200))
        draw.ellipse([60+fw-9, pb_y-6, 60+fw+9, pb_y+12], fill=(*highlight_color, 255))

    # ── Watermark ─────────────────────────────────────────────────
    wm_font = _get_font(36, bold=True)
    handle = "@AI_TECH_NEWSS"
    wbbox = draw.textbbox((0, 0), handle, font=wm_font)
    ww = wbbox[2] - wbbox[0]
    wh = wbbox[3] - wbbox[1]
    wx = (W - ww) // 2
    wy = H - wh - 46
    draw.rectangle([wx-18, wy-8, wx+ww+18, wy+wh+8], fill=(0, 0, 0, 160))
    draw.text((wx, wy), handle, font=wm_font, fill=(255, 255, 255))

    return np.array(base.convert("RGB"))


def _make_slide_clip(
    slide_text: str,
    slide_idx: int,
    total_slides: int,
    bg_img,
    badge_text: str,
    highlight_color: tuple,
    duration: float,
    time_start: float,
    total_duration: float,
    bg_color: tuple,
    fade_in: bool = True,
):
    """Generate animated frames for ONE slide (Ken Burns + fade-in)."""
    n_frames = max(1, int(duration * FPS))
    frames = []

    for i in range(n_frames):
        global_t = min((time_start + i / FPS) / max(total_duration, 1), 1.0)
        zoom = 1.0 + 0.18 * _ease_in_out(global_t)

        if fade_in and i < FADE_FRAMES:
            raw = i / max(FADE_FRAMES - 1, 1)
            alpha = min(1.0, _ease_in_out(raw))
            offset_y = int(50 * (1.0 - alpha))
        else:
            alpha = 1.0
            offset_y = 0

        frame = _render_slide(
            slide_text=slide_text,
            slide_idx=slide_idx,
            total_slides=total_slides,
            bg_img=bg_img,
            badge_text=badge_text,
            highlight_color=highlight_color,
            zoom=zoom,
            alpha=alpha,
            slide_offset_y=offset_y,
            bg_color=bg_color,
        )
        frames.append(frame)

    return ImageSequenceClip(frames, fps=FPS)


def _generate_voiceover_edge_tts(text: str, output_path: str) -> bool:
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

    # Use Claude-generated slides if available, else split headline into words
    if slides and len(slides) >= 2:
        slide_texts = [s.strip().upper() for s in slides[:5] if s.strip()]
    else:
        # Fallback: split headline into 2-word chunks
        words = headline.upper().split()
        slide_texts = []
        for i in range(0, len(words), 2):
            slide_texts.append(" ".join(words[i:i+2]))
        slide_texts = slide_texts[:4]

    n_slides = len(slide_texts)
    logger.info(f"Reel slides: {slide_texts}")

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

    # Timings
    seconds_per_slide = 2.0
    hold_duration = 3.0

    audio_duration = 0
    if has_audio:
        try:
            audio_duration = AudioFileClip(audio_path).duration
        except Exception:
            pass

    text_duration = n_slides * seconds_per_slide + hold_duration
    total_duration = max(text_duration, audio_duration) if audio_duration else text_duration

    # Build clips — ONE slide per clip, shown independently
    clips = []
    time_cursor = 0.0

    for i, slide_text in enumerate(slide_texts):
        is_last = (i == n_slides - 1)
        duration = hold_duration if is_last else seconds_per_slide
        clip = _make_slide_clip(
            slide_text=slide_text,
            slide_idx=i,
            total_slides=n_slides,
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

    # Extend last slide if audio is longer
    if audio_duration > time_cursor:
        remaining = audio_duration - time_cursor
        clip = _make_slide_clip(
            slide_text=slide_texts[-1],
            slide_idx=n_slides - 1,
            total_slides=n_slides,
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
            audio_clips.append(AudioFileClip(audio_path))
        if has_music and os.path.exists(music_path):
            music = AudioFileClip(music_path)
            music = music.subclipped(0, min(music.duration, video.duration))
            music = music.with_volume_scaled(0.18)
            audio_clips.append(music)
        if audio_clips:
            video = video.with_audio(CompositeAudioClip(audio_clips))
    except Exception as e:
        logger.warning(f"Audio mixing failed: {e}")
        if has_audio:
            try:
                video = video.with_audio(AudioFileClip(audio_path))
            except Exception:
                pass

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

    for path in [audio_path, music_path]:
        if os.path.exists(path):
            os.remove(path)

    logger.info(f"Reel saved: {output_path}")
    return output_path
