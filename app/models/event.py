"""
Pydantic event schema.

FIX #2 implemented here: fields are normalized and validated individually
as they are set, not only in one big check once all four are present.
This means a bad date format is caught and can be re-asked about the
moment it is extracted, rather than surfacing as a confusing failure
at render time after several more conversational turns have passed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

REQUIRED_FIELDS = ["title", "date", "time", "venue"]

_TIME_PATTERN = re.compile(r"^(0[1-9]|1[0-2]):[0-5][0-9] (AM|PM)$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PartialEvent(BaseModel):
    """
    The event as it exists mid-conversation: any field may still be None.
    Used by the agent/session layer while slots are being filled.
    """

    title: Optional[str] = None
    date: Optional[str] = None  # normalized to YYYY-MM-DD once set
    time: Optional[str] = None  # normalized to "HH:MM AM/PM" once set
    venue: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            return None
        return v.strip() if v else v

    @field_validator("date")
    @classmethod
    def date_must_be_normalized(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _DATE_PATTERN.match(v):
            raise ValueError(
                f"date '{v}' is not normalized to YYYY-MM-DD. "
                "The extraction layer must normalize before setting this field."
            )
        # Confirms it's a real calendar date, not just pattern-shaped.
        datetime.strptime(v, "%Y-%m-%d")
        return v

    @field_validator("time")
    @classmethod
    def time_must_be_normalized(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _TIME_PATTERN.match(v):
            raise ValueError(
                f"time '{v}' is not normalized to 'HH:MM AM/PM'. "
                "The extraction layer must normalize before setting this field."
            )
        return v

    @field_validator("venue")
    @classmethod
    def venue_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            return None
        return v.strip() if v else v

    def missing_fields(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if getattr(self, f) is None]

    def is_complete(self) -> bool:
        return len(self.missing_fields()) == 0

    def merge(self, update: "PartialEvent") -> "PartialEvent":
        """Apply a new extraction on top of the existing state; never let a
        newly-null field erase a previously-known one (FIX #4 depends on
        this -- updates are additive within the same event)."""
        data = self.model_dump()
        for field in REQUIRED_FIELDS:
            new_val = getattr(update, field)
            if new_val is not None:
                data[field] = new_val
        return PartialEvent(**data)

    def to_validated(self) -> "ValidatedEvent":
        if not self.is_complete():
            raise ValueError(
                f"Cannot validate an incomplete event. Missing: {self.missing_fields()}"
            )
        return ValidatedEvent(
            title=self.title, date=self.date, time=self.time, venue=self.venue
        )


class ValidatedEvent(BaseModel):
    """
    The event once ALL four fields are confirmed present and normalized.
    This is the only type the rendering tool is allowed to accept --
    Rule 1 of the Constitution (atomic rendering) is enforced structurally
    here: there is no code path that can construct a ValidatedEvent with
    a missing field, so "render with partial data" is not representable,
    not just discouraged.
    """

    title: str
    date: str
    time: str
    venue: str

    @model_validator(mode="after")
    def all_fields_present(self) -> "ValidatedEvent":
        for f in REQUIRED_FIELDS:
            val = getattr(self, f)
            if val is None or (isinstance(val, str) and not val.strip()):
                raise ValueError(f"ValidatedEvent.{f} must not be empty")
        return self

    def display_date(self) -> str:
        """Human-friendly date for the rendered graphic, e.g. 'Saturday, 3 October 2026'."""
        d = datetime.strptime(self.date, "%Y-%m-%d")
        return f"{d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}"
