"""
Deterministic graphic renderer. Takes a ValidatedEvent -- never a
PartialEvent, so an incomplete render is not even representable at
the type level (Constitution Rule 1, enforced structurally) -- and
produces a 1920x1080 PNG.

The AI determines WHAT the slide says. This module, and only this
module, determines what the slide LOOKS like.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app import config
from app.models.event import ValidatedEvent
from app.rendering.typography import fit_font_for_box

CANVAS_SIZE = (1920, 1080)
BACKGROUND_COLOR = (18, 22, 38)      # dark navy, safe default if no template image exists
TITLE_COLOR = (255, 255, 255)
DETAIL_COLOR = (210, 210, 225)
ACCENT_COLOR = (255, 196, 61)

# A bundled DejaVu font ships with most systems / Pillow installs; swap
# this path for a branded font file once the organization supplies one.
_DEFAULT_FONT_CANDIDATES = [
    str(Path(__file__).resolve().parent / "fonts" / "DejaVuSans-Bold.ttf"),
    str(Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"),
]


def _resolve_font_path() -> str:
    for candidate in _DEFAULT_FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    # Last resort: Pillow's bundled default (bitmap, not ideal, but never crashes).
    return ImageFont.load_default().path if hasattr(ImageFont.load_default(), "path") else ""


def render_event_graphic(event: ValidatedEvent, template_path: str | None = None) -> str:
    """
    Renders event onto a 1920x1080 PNG and returns the absolute path to
    the preview file written under config.PREVIEW_FOLDER_PATH.
    """
    if template_path and Path(template_path).exists():
        image = Image.open(template_path).convert("RGB").resize(CANVAS_SIZE)
    else:
        image = Image.new("RGB", CANVAS_SIZE, BACKGROUND_COLOR)

    draw = ImageDraw.Draw(image)
    font_path = _resolve_font_path()

    margin_x = 140
    max_text_width = CANVAS_SIZE[0] - 2 * margin_x

    # Title block, auto-scaled to fit
    title_font, title_lines = fit_font_for_box(
        event.title, font_path, draw,
        max_width=max_text_width, max_height=420,
        start_size=120, min_size=40,
    )
    y = 260
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_width = bbox[2] - bbox[0]
        x = (CANVAS_SIZE[0] - line_width) // 2
        draw.text((x, y), line, font=title_font, fill=TITLE_COLOR)
        y += int((bbox[3] - bbox[1]) * 1.15) + 10

    # Accent rule under the title
    rule_y = y + 20
    draw.line([(margin_x, rule_y), (CANVAS_SIZE[0] - margin_x, rule_y)], fill=ACCENT_COLOR, width=4)

    # Date / Time / Venue block
    detail_font = ImageFont.truetype(font_path, 52) if font_path else ImageFont.load_default()
    details = [event.display_date(), event.time, event.venue]
    detail_y = rule_y + 60
    for line in details:
        bbox = draw.textbbox((0, 0), line, font=detail_font)
        line_width = bbox[2] - bbox[0]
        x = (CANVAS_SIZE[0] - line_width) // 2
        draw.text((x, detail_y), line, font=detail_font, fill=DETAIL_COLOR)
        detail_y += 80

    filename = f"preview_{uuid.uuid4().hex[:10]}.png"
    out_path = config.PREVIEW_FOLDER_PATH / filename
    image.save(out_path, format="PNG")
    return str(out_path)
