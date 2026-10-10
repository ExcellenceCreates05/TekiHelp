from PIL import Image

from app import config
from app.models.event import ValidatedEvent
from app.rendering.engine import _resolve_font_path, render_event_graphic


def test_renderer_uses_bundled_font_and_creates_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREVIEW_FOLDER_PATH", tmp_path)
    event = ValidatedEvent(
        title="Men's Breakfast",
        date="2026-10-03",
        time="08:00 AM",
        venue="Main Church",
    )

    font_path = _resolve_font_path()
    preview_path = render_event_graphic(event)

    assert font_path.endswith("DejaVuSans-Bold.ttf")
    with Image.open(preview_path) as image:
        assert image.size == (1920, 1080)
