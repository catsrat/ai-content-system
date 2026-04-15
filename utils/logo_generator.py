"""
logo_generator.py — Generates profile logo for X and Instagram.
Dark background, bold AI text with cyan accent, clean minimal design.
"""

import os
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _get_font(size: int, bold: bool = True):
    paths = [
        os.path.join(ASSETS_DIR, "Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf"),
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_logo(size: int = 1080, output_filename: str = "logo.png") -> str:
    W = H = size
    img = Image.new("RGB", (W, H), (8, 12, 30))  # Deep dark navy
    draw = ImageDraw.Draw(img)

    # Background subtle grid pattern
    for i in range(0, W, 60):
        draw.line([(i, 0), (i, H)], fill=(20, 25, 50), width=1)
    for i in range(0, H, 60):
        draw.line([(0, i), (W, i)], fill=(20, 25, 50), width=1)

    # Outer glow ring
    ring_margin = int(W * 0.06)
    draw.ellipse(
        [ring_margin, ring_margin, W - ring_margin, H - ring_margin],
        outline=(0, 180, 255), width=6
    )
    # Inner subtle ring
    draw.ellipse(
        [ring_margin + 14, ring_margin + 14, W - ring_margin - 14, H - ring_margin - 14],
        outline=(0, 100, 180), width=2
    )

    # "AI" — massive bold text
    font_ai = _get_font(int(W * 0.42))
    bbox = draw.textbbox((0, 0), "AI", font=font_ai)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = int(H * 0.18)

    # Glow effect (draw multiple times with offset)
    for offset in range(6, 0, -1):
        draw.text((x + offset, y + offset), "AI", font=font_ai, fill=(0, 60, 120))
    draw.text((x, y), "AI", font=font_ai, fill=(0, 180, 255))

    # Accent bar under "AI"
    bar_y = y + th + int(H * 0.03)
    bar_w = int(W * 0.55)
    bar_h = int(H * 0.012)
    draw.rectangle([(W - bar_w) // 2, bar_y, (W + bar_w) // 2, bar_y + bar_h], fill=(0, 180, 255))

    # "TECH NEWS" — smaller below
    font_sub = _get_font(int(W * 0.085))
    sub_text = "TECH NEWS"
    bbox2 = draw.textbbox((0, 0), sub_text, font=font_sub)
    sw = bbox2[2] - bbox2[0]
    sx = (W - sw) // 2
    sy = bar_y + bar_h + int(H * 0.04)
    draw.text((sx, sy), sub_text, font=font_sub, fill=(200, 220, 255))

    # Bottom tagline
    font_tag = _get_font(int(W * 0.038), bold=False)
    tag = "STAY AHEAD. EVERY DAY."
    bbox3 = draw.textbbox((0, 0), tag, font=font_tag)
    tx = (W - (bbox3[2] - bbox3[0])) // 2
    ty = int(H * 0.82)
    draw.text((tx, ty), tag, font=font_tag, fill=(0, 140, 200))

    # Save full square version
    filepath = os.path.join(OUTPUT_DIR, output_filename)
    img.save(filepath, "PNG")

    # Also save a circular crop version (for X/Twitter)
    circle_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([0, 0, W, H], fill=255)
    circle_img.paste(img, (0, 0))
    circle_img.putalpha(mask)
    circle_path = os.path.join(OUTPUT_DIR, output_filename.replace(".png", "_circle.png"))
    circle_img.save(circle_path, "PNG")

    print(f"Square logo: {filepath}")
    print(f"Circle logo: {circle_path}")
    return filepath


if __name__ == "__main__":
    generate_logo()
