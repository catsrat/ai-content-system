"""
image_generator.py — Generates organic news-style social media images.

Style inspired by high-engagement AI news accounts:
- Real news image as background
- Dark gradient overlay
- Bold white headline with colored keyword highlights
- Brand watermark
- Source tag
"""

import os
import io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from utils.logger import get_logger

logger = get_logger("image_generator")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Fallback background colors if no image available
THEME_COLORS = {
    "daily_brief":    {"bg": (10, 15, 40),   "highlight": (0, 180, 255),  "badge": "📰 AI NEWS"},
    "learning":       {"bg": (10, 30, 15),   "highlight": (0, 220, 100),  "badge": "🧠 LEARN NOW"},
    "differentiator": {"bg": (35, 10, 10),   "highlight": (255, 80, 30),  "badge": "🔥 HOT TAKE"},
}

# Words to auto-highlight in headlines
HIGHLIGHT_TRIGGERS = [
    "ai", "openai", "google", "meta", "microsoft", "apple", "nvidia",
    "billion", "million", "trillion", "%", "$", "fired", "layoffs",
    "banned", "dead", "warning", "urgent", "breaking", "first", "new",
    "free", "job", "jobs", "salary", "career", "robot", "chatgpt",
    "gpt", "gemini", "claude", "llm", "agent", "agents",
]


ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    # Bundled fonts (work on all platforms including Railway/Linux)
    bundled_paths = [
        os.path.join(ASSETS_DIR, "Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf"),
    ]
    # System font fallbacks
    system_paths_bold = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    system_paths_regular = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    all_paths = bundled_paths + (system_paths_bold if bold else system_paths_regular)
    for path in all_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                logger.info(f"Using font: {path} size={size}")
                return font
            except Exception:
                continue
    logger.warning(f"No font found — using default (text will be tiny!)")
    return ImageFont.load_default()


def _download_image(url: str) -> object:
    """Download and return a PIL Image from URL."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        logger.warning(f"Could not download image from {url}: {e}")
        return None


def _make_background(img: object, bg_color: tuple, size: tuple) -> Image.Image:
    """Prepare background: use downloaded image or solid color, cropped to square."""
    W, H = size

    if img:
        # Crop to square (center crop)
        iw, ih = img.size
        scale = max(W / iw, H / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - W) // 2
        top = (new_h - H) // 2
        img = img.crop((left, top, left + W, top + H))

        # Darken + desaturate slightly for text readability
        img = ImageEnhance.Brightness(img).enhance(0.45)
        img = ImageEnhance.Color(img).enhance(0.7)
        return img
    else:
        # Solid dark background
        bg = Image.new("RGB", (W, H), bg_color)
        return bg


def _draw_gradient_overlay(draw: ImageDraw, W: int, H: int):
    """Draw dark gradient overlay for text readability."""
    for y in range(H):
        t = y / H
        alpha = int(60 + 160 * (t ** 1.2))
        draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))


def _wrap_headline(headline: str, max_chars_per_line: int = 12) -> list[str]:
    """Wrap headline into lines, keeping important words together.
    Truncates to max 4 words per line, max 3 lines for big bold text."""
    # Trim headline to max 8 words for impact
    words = headline.split()[:8]
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if len(test) <= max_chars_per_line:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:3]


def _draw_highlighted_text(draw, lines, start_y, line_h, font_size, highlight_color, W):
    """Draw headline with auto-highlighted keywords."""
    font_bold = _get_font(font_size, bold=True)

    for i, line in enumerate(lines):
        words = line.split()
        # Calculate total line width first
        full_text = " ".join(words)
        bbox = draw.textbbox((0, 0), full_text, font=font_bold)
        total_w = bbox[2] - bbox[0]
        x = (W - total_w) // 2
        y = start_y + i * line_h

        # Draw word by word
        for j, word in enumerate(words):
            clean = word.lower().strip(".,!?")
            is_highlight = any(t in clean for t in HIGHLIGHT_TRIGGERS)
            color = highlight_color if is_highlight else (255, 255, 255)

            # Shadow
            shadow_offset = 3
            draw.text((x + shadow_offset, y + shadow_offset), word, font=font_bold, fill=(0, 0, 0, 180))
            # Main
            draw.text((x, y), word, font=font_bold, fill=color)

            # Advance x
            w_bbox = draw.textbbox((0, 0), word + " ", font=font_bold)
            x += w_bbox[2] - w_bbox[0]


def _draw_rounded_rect(draw, x1, y1, x2, y2, r, fill):
    r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=fill)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=fill)
    draw.ellipse([x1, y1, x1 + r*2, y1 + r*2], fill=fill)
    draw.ellipse([x2 - r*2, y1, x2, y1 + r*2], fill=fill)
    draw.ellipse([x1, y2 - r*2, x1 + r*2, y2], fill=fill)
    draw.ellipse([x2 - r*2, y2 - r*2, x2, y2], fill=fill)


def generate_post_image(
    post_type: str,
    headline: str,
    brand_name: str = "AI_TECH_NEWSS",
    filename: str = None,
    background_image_url: str = None,
) -> str:
    W, H = 1080, 1080
    theme = THEME_COLORS.get(post_type, THEME_COLORS["daily_brief"])
    highlight = theme["highlight"]

    # ── 1. Background ───────────────────────────────────────
    bg_img = _download_image(background_image_url)
    base = _make_background(bg_img, theme["bg"], (W, H))

    # ── 2. Gradient overlay (RGBA) ──────────────────────────
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    _draw_gradient_overlay(ov_draw, W, H)
    base = base.convert("RGBA")
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    # ── 3. Top source badge ─────────────────────────────────
    badge_font = _get_font(28, bold=True)
    badge_text = theme["badge"]
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbox[2] - bbox[0] + 32
    bh = 52
    _draw_rounded_rect(draw, 40, 40, 40 + bw, 40 + bh, 12, (*highlight, 230))
    draw.text((56, 51), badge_text, font=badge_font, fill=(255, 255, 255))

    # ── 4. Headline text (center of image) ─────────────────
    lines = _wrap_headline(headline, max_chars_per_line=12)
    n = len(lines)
    font_size = 130 if n == 1 else (110 if n == 2 else 90)
    line_h = font_size + 24
    total_h = n * line_h
    start_y = (H - total_h) // 2 - 40

    _draw_highlighted_text(draw, lines, start_y, line_h, font_size, highlight, W)

    # ── 5. Accent bar under headline ────────────────────────
    bar_y = start_y + total_h + 20
    bar_w = 120
    draw.rectangle([(W - bar_w) // 2, bar_y, (W + bar_w) // 2, bar_y + 5], fill=highlight)

    # ── 6. Brand watermark (bottom right) ──────────────────
    wm_font = _get_font(32, bold=True)
    handle = f"@{brand_name}"
    bbox = draw.textbbox((0, 0), handle, font=wm_font)
    ww = bbox[2] - bbox[0]
    wh = bbox[3] - bbox[1]
    wx = W - ww - 40
    wy = H - wh - 40
    # Semi-transparent pill behind watermark
    _draw_rounded_rect(draw, wx - 14, wy - 8, wx + ww + 14, wy + wh + 8, 10, (0, 0, 0, 160))
    draw.text((wx, wy), handle, font=wm_font, fill=(255, 255, 255))

    # ── 7. Thin accent line at very bottom ─────────────────
    for i in range(6):
        draw.line([(0, H - 6 + i), (W, H - 6 + i)], fill=(*highlight, 200 - i * 30))

    # Save
    final = base.convert("RGB")
    if not filename:
        filename = f"{post_type}_image.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    final.save(filepath, "PNG", quality=95)
    logger.info(f"Image saved: {filepath}")
    return filepath


def generate_carousel_slides(
    post_type: str,
    slides: list[str],
    brand_name: str = "AI_TECH_NEWSS",
    base_filename: str = "carousel",
    background_image_url: str = None,
) -> list[str]:
    paths = []
    for i, text in enumerate(slides[:10]):
        fname = f"{base_filename}_slide_{i + 1}.png"
        try:
            path = generate_post_image(
                post_type=post_type,
                headline=text,
                brand_name=brand_name,
                filename=fname,
                background_image_url=background_image_url,
            )
            paths.append(path)
        except Exception as e:
            logger.error(f"Slide {i+1} failed: {e}")
    return paths
