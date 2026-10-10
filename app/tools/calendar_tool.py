"""
Calendar Tool (Week 3, Day 15-16).

Deliberately scoped as a READ-ONLY lookup, not a scheduling system --
see the build plan's note on keeping this tool disciplined. It checks
a local calendar.json for a same-date/same-venue clash and returns a
soft warning string the orchestrator can surface to the operator; it
never blocks rendering on its own (that would violate Rule 1, which
only cares about the four fields being present).
"""
from __future__ import annotations

import json
from pathlib import Path

from app import config
from app.models.event import ValidatedEvent


def _load_calendar() -> list[dict]:
    if not Path(config.CALENDAR_PATH).exists():
        return []
    with open(config.CALENDAR_PATH, "r") as f:
        return json.load(f)


def check_for_clash(event: ValidatedEvent) -> str | None:
    """
    Returns a human-readable warning string if another known event shares
    the same date and venue, else None. Read-only -- never raises, never
    mutates calendar.json.
    """
    for entry in _load_calendar():
        if entry.get("date") == event.date and entry.get("venue") == event.venue:
            if entry.get("title") != event.title:
                return (
                    f"Note: \"{entry.get('title')}\" is already scheduled at "
                    f"{event.venue} on this date ({entry.get('time')}). Continue anyway?"
                )
    return None


def add_to_calendar(event: ValidatedEvent) -> None:
    """Called only after approval, to keep the lookup file current for
    future clash checks."""
    entries = _load_calendar()
    entries.append(event.model_dump())
    with open(config.CALENDAR_PATH, "w") as f:
        json.dump(entries, f, indent=2)
