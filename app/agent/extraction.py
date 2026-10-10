"""
Extraction layer: turns a raw model JSON response into a PartialEvent,
applying per-field validation/normalization immediately (FIX #2) rather
than deferring it to a final whole-object check.

If the model returns a date/time that doesn't match the required
normalized format, that specific field is dropped (set to None) and
logged -- it does NOT crash the conversation, and the agent will
naturally re-ask for that field as if it were still missing. This is
deliberately forgiving of model mistakes while staying strict about
never passing malformed data forward.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls

from pydantic import ValidationError

from app.ai.router import InferenceRouter
from app.agent.prompts import build_extraction_prompt
from app.models.event import PartialEvent
from app.models.session import Session

logger = logging.getLogger("tekihelp.extraction")


class ExtractionOutcome:
    def __init__(
        self,
        partial_event: PartialEvent,
        is_event: bool,
        possible_new_event: bool,
        engine_used: str,
        fell_back: bool,
        dropped_fields: list[str],
    ) -> None:
        self.partial_event = partial_event
        self.is_event = is_event
        self.possible_new_event = possible_new_event
        self.engine_used = engine_used
        self.fell_back = fell_back
        self.dropped_fields = dropped_fields


def extract(router: InferenceRouter, session: Session, message: str) -> ExtractionOutcome:
    today = date_cls.today().isoformat()
    prompt = build_extraction_prompt(session, message, today)

    result = router.generate_structured(session.session_key, prompt)
    data = result.parsed

    dropped: list[str] = []
    field_kwargs: dict[str, str | None] = {}

    for field in ("title", "date", "time", "venue"):
        value = data.get(field)
        if value is None:
            field_kwargs[field] = None
            continue
        try:
            # Validate ONE field at a time by constructing a throwaway
            # PartialEvent with just that field -- this is what gives us
            # per-field granularity instead of one all-or-nothing check.
            PartialEvent(**{field: value})
            field_kwargs[field] = value
        except ValidationError:
            logger.warning(
                "Session %s: dropped unnormalized field '%s'=%r from %s output",
                session.session_key, field, value, result.engine_used,
            )
            dropped.append(field)
            field_kwargs[field] = None

    partial_event = PartialEvent(**field_kwargs)

    return ExtractionOutcome(
        partial_event=partial_event,
        is_event=bool(data.get("is_event", True)),
        possible_new_event=bool(data.get("possible_new_event", False)),
        engine_used=result.engine_used,
        fell_back=result.fell_back,
        dropped_fields=dropped,
    )
