"""
Tests Rule 1 (atomic rendering, structurally enforced) and FIX #2
(per-field normalization/validation).
"""
import pytest
from pydantic import ValidationError

from app.models.event import PartialEvent, ValidatedEvent


def test_partial_event_accepts_nulls():
    e = PartialEvent(title="Men's Breakfast")
    assert e.date is None
    assert e.missing_fields() == ["date", "time", "venue"]
    assert not e.is_complete()


def test_partial_event_rejects_unnormalized_date():
    with pytest.raises(ValidationError):
        PartialEvent(date="next Saturday")  # not YYYY-MM-DD


def test_partial_event_rejects_unnormalized_time():
    with pytest.raises(ValidationError):
        PartialEvent(time="8am")  # not "HH:MM AM/PM"


def test_partial_event_accepts_normalized_values():
    e = PartialEvent(date="2026-10-17", time="08:00 AM")
    assert e.date == "2026-10-17"
    assert e.time == "08:00 AM"


def test_merge_does_not_erase_known_fields():
    """FIX #4 depends on this: an update with new nulls must not wipe
    previously known fields."""
    e1 = PartialEvent(title="Men's Breakfast", venue="Main Church")
    e2 = PartialEvent(date="2026-10-17")  # title/venue not mentioned this turn
    merged = e1.merge(e2)
    assert merged.title == "Men's Breakfast"
    assert merged.venue == "Main Church"
    assert merged.date == "2026-10-17"


def test_to_validated_requires_all_fields():
    e = PartialEvent(title="X", date="2026-10-17", time="08:00 AM")  # venue missing
    with pytest.raises(ValueError):
        e.to_validated()


def test_validated_event_cannot_be_constructed_incomplete():
    """Rule 1: there must be NO way to construct a ValidatedEvent with a
    missing field -- this is the structural enforcement, not just a check."""
    with pytest.raises(ValidationError):
        ValidatedEvent(title="X", date="2026-10-17", time="08:00 AM", venue="")


def test_full_pipeline_partial_to_validated():
    e = PartialEvent(
        title="Men's Breakfast", date="2026-10-17", time="08:00 AM", venue="Main Church"
    )
    assert e.is_complete()
    v = e.to_validated()
    assert isinstance(v, ValidatedEvent)


def test_display_date_uses_portable_day_format():
    event = ValidatedEvent(
        title="Men's Breakfast",
        date="2026-10-03",
        time="08:00 AM",
        venue="Main Church",
    )
    assert event.display_date() == "Saturday, 3 October 2026"
