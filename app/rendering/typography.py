"""
Typography helpers: text wrapping and auto-scaling font size so the
title always fits its bounding box regardless of length.
"""
from __future__ import annotations

from PIL import ImageFont


def wrap_text_to_width(text: str, font: ImageFont.FreeTypeFont, draw, max_width: int) -> list[str]:
    """Greedy word-wrap: returns a list of lines that each fit within max_width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def fit_font_for_box(
    text: str,
    font_path: str,
    draw,
    max_width: int,
    max_height: int,
    start_size: int = 96,
    min_size: int = 28,
    line_spacing: float = 1.15,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """
    Shrinks font size step by step until the wrapped text fits inside
    (max_width, max_height). Returns the chosen font and the wrapped lines.
    """
    size = start_size
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text_to_width(text, font, draw, max_width)
        line_height = int((font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) * line_spacing)
        total_height = line_height * len(lines)
        widest_line = max(
            (draw.textbbox((0, 0), line, font=font)[2] for line in lines), default=0
        )
        if total_height <= max_height and widest_line <= max_width:
            return font, lines
        size -= 4
    # Fall back to the smallest size even if it slightly overflows --
    # better a tight fit than a crash.
    font = ImageFont.truetype(font_path, min_size)
    return font, wrap_text_to_width(text, font, draw, max_width)
