"""
image_generator.py — Generates high-quality carousel slides using real Unsplash photos.

Style: uncover.ai inspired
- Real topic-relevant photo as full background
- Clean dark gradient overlay
- Bold white text, minimal clutter
- Brand watermark
- 4 carousel slides per post (swipeable)
"""

import os
import io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from utils.logger import get_logger

logger = get_logger("image_generator")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")

THEME_COLORS = {
    "daily_brief":    {"highlight": (0, 180, 255),   "badge": "AI NEWS",    "emoji": "📰"},
    "learning":       {"highlight": (0, 220, 120),   "badge": "LEARN THIS", "emoji": "🧠"},
    "differentiator": {"highlight": (255, 80, 30),   "badge": "HOT TAKE",   "emoji": "🔥"},
    "workflow":       {"highlight": (180, 80, 255),  "badge": "FREE TOOL",  "emoji": "⚡"},
}

# Instagram carousel size (4:5 portrait — best reach)
W, H = 1080, 1350


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    bundled = os.path.join(ASSETS_DIR, "Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf")
    fallbacks_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    fallbacks_reg = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    paths = [bundled] + (fallbacks_bold if bold else fallbacks_reg)
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fetch_unsplash_photo(topic: str, access_key: str) -> Image.Image | None:
    """Fetch a random relevant photo from Unsplash — different every time."""
    if not access_key:
        return None
    try:
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                      "of", "with", "by", "from", "use", "using", "how", "why", "what", "is"}
        keywords = [w.lower() for w in topic.split() if w.lower() not in stop_words][:3]
        query = " ".join(keywords) + " technology"

        # Use /photos/random for a different photo every call
        resp = requests.get(
            "https://api.unsplash.com/photos/random",
            params={
                "query": query,
                "orientation": "portrait",
                "content_filter": "high",
                "count": 1,
            },
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10,
        )
        if not resp.ok:
            logger.warning(f"Unsplash API error: {resp.status_code}")
            return None

        data = resp.json()
        results = data if isinstance(data, list) else [data]

        if not results:
            # Fallback to generic AI photo
            resp2 = requests.get(
                "https://api.unsplash.com/photos/random",
                params={"query": "artificial intelligence", "orientation": "portrait", "count": 1},
                headers={"Authorization": f"Client-ID {access_key}"},
                timeout=10,
            )
            data2 = resp2.json() if resp2.ok else []
            results = data2 if isinstance(data2, list) else [data2]

        if results and results[0].get("urls"):
            photo_url = results[0]["urls"]["regular"]
            img_resp = requests.get(photo_url, timeout=15)
            img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
            logger.info(f"Unsplash random photo fetched for: {query}")
            return img

    except Exception as e:
        logger.warning(f"Unsplash fetch failed: {e}")
    return None


def _download_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None


def _prepare_background(img: Image.Image | None) -> Image.Image:
    """Crop photo to canvas size with dark overlay, or use gradient fallback."""
    if img:
        # Center crop to canvas
        iw, ih = img.size
        scale = max(W / iw, H / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img = img.resize((nw, nh), Image.LANCZOS)
        left = (nw - W) // 2
        top = (nh - H) // 2
        img = img.crop((left, top, left + W, top + H))
        # Darken for text readability
        img = ImageEnhance.Brightness(img).enhance(0.40)
        img = ImageEnhance.Color(img).enhance(0.65)
        return img
    else:
        # Gradient fallback
        bg = Image.new("RGB", (W, H), (8, 10, 25))
        return bg


def _draw_gradient(overlay_draw: ImageDraw):
    """Draw gradient overlay — heavier at bottom for text area."""
    for y in range(H):
        t = y / H
        # Strong bottom gradient
        alpha = int(20 + 200 * (t ** 1.5))
        overlay_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))


def _auto_wrap(draw: ImageDraw, text: str, font: ImageFont.FreeTypeFont,
               max_width: int) -> list[str]:
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _auto_fit_text(draw: ImageDraw, text: str, max_width: int,
                   max_size: int = 100, min_size: int = 36) -> tuple:
    """Find largest font size where text fits within max_width."""
    for size in range(max_size, min_size - 1, -4):
        font = _get_font(size, bold=True)
        lines = _auto_wrap(draw, text, font, max_width)
        # Accept if fits in 3 lines max
        if len(lines) <= 3:
            return font, size, lines
    font = _get_font(min_size, bold=True)
    lines = _auto_wrap(draw, text, font, max_width)
    return font, min_size, lines


def _draw_rounded_rect(draw: ImageDraw, x1, y1, x2, y2, r, fill):
    if x2 <= x1 or y2 <= y1:
        return
    r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=fill)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=fill)
    draw.ellipse([x1, y1, x1 + r * 2, y1 + r * 2], fill=fill)
    draw.ellipse([x2 - r * 2, y1, x2, y1 + r * 2], fill=fill)
    draw.ellipse([x1, y2 - r * 2, x1 + r * 2, y2], fill=fill)
    draw.ellipse([x2 - r * 2, y2 - r * 2, x2, y2], fill=fill)


def _render_slide(
    slide_text: str,
    slide_idx: int,
    total_slides: int,
    bg: Image.Image,
    highlight: tuple,
    brand_name: str,
    is_cover: bool = False,
    is_cta: bool = False,
) -> Image.Image:
    """Render one carousel slide."""
    base = bg.copy().convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    _draw_gradient(ov_draw)
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    PADDING = 60
    max_text_w = W - PADDING * 2

    # ── Top bar: brand handle only (minimal) ───────────────
    top_font = _get_font(26, bold=True)
    top_text = f"@{brand_name}"
    draw.text((PADDING, 52), top_text, font=top_font, fill=(*highlight, 200))

    # ── Main text (lower 40% of image) ─────────────────────
    text_zone_top = int(H * 0.52)

    if is_cover:
        # Cover slide: very large headline
        font, size, lines = _auto_fit_text(draw, slide_text, max_text_w, max_size=110, min_size=52)
    elif is_cta:
        # CTA slide: medium text + follow prompt
        font, size, lines = _auto_fit_text(draw, slide_text, max_text_w, max_size=72, min_size=40)
    else:
        # Content slide: medium text
        font, size, lines = _auto_fit_text(draw, slide_text, max_text_w, max_size=72, min_size=36)

    line_h = size + 18
    total_text_h = len(lines) * line_h
    text_y = text_zone_top + (H - text_zone_top - total_text_h - 120) // 2

    for i, line in enumerate(lines):
        lb = draw.textbbox((0, 0), line, font=font)
        lw = lb[2] - lb[0]
        lx = (W - lw) // 2
        ly = text_y + i * line_h
        # Shadow
        draw.text((lx + 3, ly + 3), line, font=font, fill=(0, 0, 0, 160))
        # Main text
        draw.text((lx, ly), line, font=font, fill=(255, 255, 255))

    # Accent line under text
    line_y = text_y + total_text_h + 20
    draw.rectangle([(W - 80) // 2, line_y, (W + 80) // 2, line_y + 4], fill=(*highlight, 200))

    # Swipe hint / CTA below accent line
    hint_font = _get_font(28, bold=False)
    if is_cta:
        hint_text = f"Follow @{brand_name} for daily AI updates"
        hint_color = (*highlight, 220)
    elif slide_idx < total_slides - 1:
        hint_text = "swipe for more  →"
        hint_color = (255, 255, 255, 140)
    else:
        hint_text = ""
        hint_color = (255, 255, 255, 0)

    if hint_text:
        hb = draw.textbbox((0, 0), hint_text, font=hint_font)
        hw = hb[2] - hb[0]
        draw.text(((W - hw) // 2, line_y + 28), hint_text, font=hint_font, fill=hint_color)

    # ── Brand watermark (bottom) ────────────────────────────
    wm_font = _get_font(28, bold=True)
    handle = f"@{brand_name}"
    wb = draw.textbbox((0, 0), handle, font=wm_font)
    ww = wb[2] - wb[0]
    wx = (W - ww) // 2
    wy = H - 55
    draw.text((wx + 2, wy + 2), handle, font=wm_font, fill=(0, 0, 0, 140))
    draw.text((wx, wy), handle, font=wm_font, fill=(255, 255, 255, 180))

    # Bottom accent line
    for i in range(5):
        draw.line([(0, H - 5 + i), (W, H - 5 + i)], fill=(*highlight, 180 - i * 30))

    return base.convert("RGB")


def generate_carousel_images(
    post_type: str,
    carousel_texts: list[str],
    topic: str = "",
    brand_name: str = "AI_TECH_NEWSS",
    base_filename: str = "carousel",
    background_image_url: str = None,
    unsplash_access_key: str = "",
) -> list[str]:
    """
    Generate 4 carousel slide images for Instagram.
    carousel_texts: list of 4 slide texts [hook, point1, point2, cta]
    Returns list of file paths.
    """
    theme = THEME_COLORS.get(post_type, THEME_COLORS["daily_brief"])
    highlight = theme["highlight"]

    # Fetch photo: try Unsplash first, then article image, then None
    photo = None
    if unsplash_access_key and topic:
        photo = _fetch_unsplash_photo(topic, unsplash_access_key)
    if photo is None and background_image_url:
        photo = _download_image(background_image_url)

    bg = _prepare_background(photo)

    # Ensure we have exactly 4 slides
    texts = list(carousel_texts)
    while len(texts) < 4:
        texts.append(f"Follow @{brand_name} for daily AI updates")
    texts = texts[:4]

    paths = []
    total = len(texts)
    for i, text in enumerate(texts):
        is_cover = (i == 0)
        is_cta = (i == total - 1)
        slide = _render_slide(
            slide_text=text,
            slide_idx=i,
            total_slides=total,
            bg=bg,
            highlight=highlight,
            brand_name=brand_name,
            is_cover=is_cover,
            is_cta=is_cta,
        )
        fname = f"{base_filename}_slide_{i + 1}.png"
        fpath = os.path.join(OUTPUT_DIR, fname)
        slide.save(fpath, "PNG", quality=95)
        logger.info(f"Carousel slide {i+1}/{total} saved: {fpath}")
        paths.append(fpath)

    return paths


def generate_post_image(
    post_type: str,
    headline: str,
    brand_name: str = "AI_TECH_NEWSS",
    filename: str = None,
    background_image_url: str = None,
    topic: str = "",
    unsplash_access_key: str = "",
) -> str:
    """
    Generate a single image (used for Twitter).
    Uses 1080x1080 square format.
    """
    # Temporarily override canvas to square for Twitter
    global W, H
    orig_W, orig_H = W, H
    W, H = 1080, 1080

    theme = THEME_COLORS.get(post_type, THEME_COLORS["daily_brief"])

    photo = None
    if unsplash_access_key and topic:
        photo = _fetch_unsplash_photo(topic, unsplash_access_key)
    if photo is None and background_image_url:
        photo = _download_image(background_image_url)

    bg = _prepare_background(photo, theme["highlight"])

    slide = _render_slide(
        slide_text=headline,
        slide_idx=0,
        total_slides=1,
        bg=bg,
        highlight=theme["highlight"],
        brand_name=brand_name,
        is_cover=True,
        is_cta=False,
    )

    W, H = orig_W, orig_H  # restore

    if not filename:
        filename = f"{post_type}_image.png"
    fpath = os.path.join(OUTPUT_DIR, filename)
    slide.save(fpath, "PNG", quality=95)
    logger.info(f"Image saved: {fpath}")
    return fpath
