"""
INBXR — Blog Featured Image Generator
Generates branded 1200x630 OG images for blog posts using Pillow.
"""

import math
import os
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont

# ── Paths ──
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATIC_DIR = os.path.join(_BASE_DIR, "static")
_IMAGES_DIR = os.path.join(_STATIC_DIR, "images")
_LOGO_PATH = os.path.join(_IMAGES_DIR, "logo.png")

# Use persistent data dir on Railway, fall back to static/images/blog locally
_DATA_DIR = os.environ.get("INBXR_DATA_DIR", os.path.join(_BASE_DIR, "data"))
_BLOG_IMG_DIR = os.path.join(_DATA_DIR, "blog_images")

# ── Brand colors ──
BG_COLOR = (15, 23, 42)          # --bg-1 dark navy
BRAND_TEAL = (21, 193, 130)      # --brand #15c182
ACCENT_DARK = (3, 160, 113)      # --accent #03a071
TEXT_WHITE = (255, 255, 255)
TEXT_MUTED = (148, 163, 184)      # slate-400
CARD_BG = (30, 41, 59)           # slightly lighter navy

# ── Dimensions ──
WIDTH = 1200
HEIGHT = 630

# ── Category icon patterns (simple geometric shapes) ──
_CATEGORY_ICONS = {
    "deliverability": "inbox",
    "authentication": "shield",
    "reputation": "chart",
    "content": "pencil",
}


def _get_font(size, bold=False):
    """Get the best available font at given size."""
    # Try common font paths
    candidates = []
    if bold:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    # Nix store paths (Railway/Nixpacks)
    import glob as _glob
    for pattern in (["/nix/store/*/share/fonts/truetype/DejaVuSans-Bold.ttf"] if bold else ["/nix/store/*/share/fonts/truetype/DejaVuSans.ttf"]):
        matches = _glob.glob(pattern)
        if matches:
            candidates.insert(0, matches[0])
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_title(title, font, max_width, draw):
    """Word-wrap title text to fit within max_width pixels."""
    words = title.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _draw_icon(draw, icon_type, x, y, size, color):
    """Draw a simple geometric icon."""
    s = size
    if icon_type == "inbox":
        # Envelope shape
        draw.rectangle([x, y + s * 0.2, x + s, y + s * 0.8], outline=color, width=2)
        draw.line([x, y + s * 0.2, x + s * 0.5, y + s * 0.55], fill=color, width=2)
        draw.line([x + s, y + s * 0.2, x + s * 0.5, y + s * 0.55], fill=color, width=2)
    elif icon_type == "shield":
        # Shield shape
        points = [
            (x + s * 0.5, y),
            (x + s, y + s * 0.25),
            (x + s, y + s * 0.55),
            (x + s * 0.5, y + s),
            (x, y + s * 0.55),
            (x, y + s * 0.25),
        ]
        draw.polygon(points, outline=color, width=2)
        # Checkmark inside
        draw.line([x + s * 0.3, y + s * 0.5, x + s * 0.45, y + s * 0.65], fill=color, width=2)
        draw.line([x + s * 0.45, y + s * 0.65, x + s * 0.7, y + s * 0.35], fill=color, width=2)
    elif icon_type == "chart":
        # Bar chart
        draw.rectangle([x + s * 0.05, y + s * 0.6, x + s * 0.25, y + s], outline=color, fill=color)
        draw.rectangle([x + s * 0.3, y + s * 0.35, x + s * 0.5, y + s], outline=color, fill=color)
        draw.rectangle([x + s * 0.55, y + s * 0.1, x + s * 0.75, y + s], outline=color, fill=color)
        draw.rectangle([x + s * 0.8, y + s * 0.45, x + s, y + s], outline=color, fill=color)
    elif icon_type == "pencil":
        # Pencil/edit icon
        draw.polygon([
            (x + s * 0.7, y),
            (x + s, y + s * 0.3),
            (x + s * 0.3, y + s),
            (x, y + s * 0.7),
        ], outline=color, width=2)
        draw.line([x, y + s * 0.7, x + s * 0.3, y + s], fill=color, width=2)
    else:
        # Default: circle
        draw.ellipse([x, y, x + s, y + s], outline=color, width=2)


def _draw_decorative_elements(draw, category_slug):
    """Draw subtle background decorations."""
    icon_type = _CATEGORY_ICONS.get(category_slug, "inbox")

    # Corner accent lines
    accent = (*BRAND_TEAL, 40)  # semi-transparent

    # Top-right decorative dots grid
    for row in range(5):
        for col in range(5):
            cx = WIDTH - 120 + col * 22
            cy = 40 + row * 22
            draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(*BRAND_TEAL, 30))

    # Bottom-left decorative dots
    for row in range(3):
        for col in range(3):
            cx = 40 + col * 22
            cy = HEIGHT - 100 + row * 22
            draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(*BRAND_TEAL, 30))

    # Large faded icon in top-right
    _draw_icon(draw, icon_type, WIDTH - 200, 30, 120, (*BRAND_TEAL, 25))


def generate_blog_image(title, slug, category=None, keyword=None):
    """Generate a branded featured image for a blog post.

    Args:
        title: Blog post title
        slug: URL slug (used for filename)
        category: Category name (for icon selection)
        keyword: Target keyword (shown as tag)

    Returns:
        Relative path from static/ (e.g., 'images/blog/my-slug.png')
    """
    os.makedirs(_BLOG_IMG_DIR, exist_ok=True)

    # Use RGBA for semi-transparent elements
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img, "RGBA")

    # ── Background gradient effect (darker at top, slightly lighter at bottom) ──
    for y in range(HEIGHT):
        r = int(BG_COLOR[0] + (CARD_BG[0] - BG_COLOR[0]) * (y / HEIGHT) * 0.5)
        g = int(BG_COLOR[1] + (CARD_BG[1] - BG_COLOR[1]) * (y / HEIGHT) * 0.5)
        b = int(BG_COLOR[2] + (CARD_BG[2] - BG_COLOR[2]) * (y / HEIGHT) * 0.5)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b, 255))

    # ── Decorative elements ──
    cat_slug = re.sub(r'[^a-z0-9]+', '-', (category or "").lower()).strip('-')
    _draw_decorative_elements(draw, cat_slug)

    # ── Teal accent bar at top ──
    draw.rectangle([0, 0, WIDTH, 5], fill=BRAND_TEAL + (255,))

    # ── Category / keyword tag ──
    tag_text = (category or keyword or "Email Deliverability").upper()
    tag_font = _get_font(16, bold=True)
    tag_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    tag_x, tag_y = 80, 80
    # Tag pill background
    draw.rounded_rectangle(
        [tag_x - 12, tag_y - 6, tag_x + tag_w + 12, tag_y + 22],
        radius=12,
        fill=(*BRAND_TEAL, 30),
        outline=(*BRAND_TEAL, 80),
    )
    draw.text((tag_x, tag_y), tag_text, fill=BRAND_TEAL + (255,), font=tag_font)

    # ── Title text ──
    title_font = _get_font(46, bold=True)
    max_text_width = WIDTH - 180  # 80px padding each side + margin
    lines = _wrap_title(title, title_font, max_text_width, draw)

    # Limit to 4 lines max
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1][:len(lines[-1]) - 3] + "..."

    line_height = 58
    title_start_y = 130
    for i, line in enumerate(lines):
        y = title_start_y + i * line_height
        draw.text((80, y), line, fill=TEXT_WHITE + (255,), font=title_font)

    # ── Teal underline accent below title ──
    underline_y = title_start_y + len(lines) * line_height + 15
    draw.rectangle([80, underline_y, 280, underline_y + 4], fill=BRAND_TEAL + (255,))

    # ── Subtitle / description ──
    subtitle_font = _get_font(20)
    subtitle_y = underline_y + 30
    subtitle = "Free tools to fix your email deliverability"
    draw.text((80, subtitle_y), subtitle, fill=TEXT_MUTED + (255,), font=subtitle_font)

    # ── Logo in bottom-left (white version) ──
    try:
        logo = Image.open(_LOGO_PATH).convert("RGBA")
        # Scale logo to ~140px wide
        logo_w = 140
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        # Convert all non-transparent pixels to white
        pixels = logo.load()
        for py in range(logo.height):
            for px in range(logo.width):
                r, g, b, a = pixels[px, py]
                if a > 0:
                    pixels[px, py] = (255, 255, 255, a)
        logo_y = HEIGHT - logo_h - 40
        img.paste(logo, (80, logo_y), logo)
    except Exception:
        # Fallback: just write text
        logo_font = _get_font(28, bold=True)
        draw.text((80, HEIGHT - 70), "INBXR", fill=TEXT_WHITE + (255,), font=logo_font)

    # ── URL in bottom-right ──
    url_font = _get_font(16)
    url_text = "inbxr.us"
    url_bbox = draw.textbbox((0, 0), url_text, font=url_font)
    url_w = url_bbox[2] - url_bbox[0]
    draw.text((WIDTH - url_w - 60, HEIGHT - 55), url_text,
              fill=TEXT_MUTED + (255,), font=url_font)

    # ── Save ──
    out_path = os.path.join(_BLOG_IMG_DIR, f"{slug}.png")
    # Convert to RGB for PNG (remove alpha)
    final = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    final.paste(img, (0, 0), img)
    final.save(out_path, "PNG", optimize=True)

    # Return URL path for serving
    return f"/blog-images/{slug}.png"
