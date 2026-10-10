"""
Prompt templates. Kept as plain functions (not an external templating
engine) so they're easy to diff and cite in Chapter 4/5 as artefacts
of the Reflection-and-Learning cycles.
"""
from __future__ import annotations

from app.models.session import Session

EXTRACTION_SYSTEM_INSTRUCTIONS = """You are the extraction component of Tekihelp, an AI assistant that turns \
informal church/event announcements into structured broadcast graphics.

You are given the conversation so far and the event fields already known. \
Your ONLY job is to return a single JSON object -- no prose, no markdown fences.

Required JSON shape:
{
  "title": string or null,
  "date": string or null,      // MUST be normalized to YYYY-MM-DD, or null
  "time": string or null,      // MUST be normalized to "HH:MM AM/PM" (e.g. "08:00 AM"), or null
  "venue": string or null,
  "is_event": boolean,         // false for greetings, prayers, small talk -- Constitution Rule 4
  "possible_new_event": boolean // true ONLY if this message looks like it starts a DIFFERENT
                                 // event than the one already in progress (see current event below)
}

Rules you must follow (from the Operational Constitution):
1. NEVER invent a title, date, time, or venue that was not stated or clearly implied. If it is
   not present in the message, return null for that field. Do not guess a default time or date.
2. ALWAYS normalize dates and times. Today's reference date is given below -- use it to resolve
   relative expressions ("this Saturday", "tomorrow", "kesho"). Interpret common Swahili/English
   code-switched time expressions (e.g. "saa nane" = 2:00 PM, "saa mbili" = 8:00 AM) using the
   standard Swahili time system (shift by 6 hours from the stated number).
3. If the message is not an announcement of an event at all (a greeting, a prayer request, small
   talk), set "is_event" to false and leave all four fields null.
4. Only fill in fields that are stated or very clearly implied by THIS message or the recent
   conversation history. Do not carry over assumptions beyond what the conversation supports.
5. Set "possible_new_event" to true only if this message names a clearly different title/venue
   than the event already in progress, while that event is still incomplete. Otherwise false.

Today's date: __TODAY__

Current event already known (do not re-ask about non-null fields):
__CURRENT_EVENT_JSON__

Recent conversation:
__HISTORY__

New message to process:
__MESSAGE__

Return ONLY the JSON object.
"""


def build_extraction_prompt(session: Session, new_message: str, today: str) -> str:
    # Deliberately NOT using str.format() here: the template above contains
    # literal JSON braces (the "Required JSON shape" example) and the
    # current_event_json value itself is also JSON containing braces, both
    # of which break str.format's placeholder parsing. Plain string
    # replacement sidesteps that entirely.
    prompt = EXTRACTION_SYSTEM_INSTRUCTIONS
    prompt = prompt.replace("__TODAY__", today)
    prompt = prompt.replace("__CURRENT_EVENT_JSON__", session.current_event.model_dump_json())
    prompt = prompt.replace("__HISTORY__", session.recent_history_text() or "(no prior messages)")
    prompt = prompt.replace("__MESSAGE__", new_message)
    return prompt


CLARIFICATION_TEMPLATES = {
    "title": "What should I call this event?",
    "date": "What date is {title_or_it} happening?",
    "time": "What time will {title_or_it} begin?",
    "venue": "Where will {title_or_it} be held?",
}


def build_clarification_question(missing_field: str, title: str | None) -> str:
    label = f'"{title}"' if title else "it"
    template = CLARIFICATION_TEMPLATES[missing_field]
    return template.format(title_or_it=label)


# FIX #3: reject-feedback prompt
REJECTION_FOLLOWUP = (
    "Got it -- I won't send that one. What should I correct? "
    "(You can tell me the new title, date, time, or venue.)"
)

# FIX #4: concurrent-event guard prompt
NEW_EVENT_CONFIRMATION_TEMPLATE = (
    "Just checking -- is \"{new_hint}\" more information for the event we were "
    "just discussing, or is it a completely new, separate event?"
)
