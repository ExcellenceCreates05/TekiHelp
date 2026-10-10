"""
Agent Orchestrator -- the Observe-Reason-Act loop (Week 2, Day 10-11).

This is the one place that decides what happens on each turn. It is
read top-to-bottom as: safety checks -> classify the message ->
route to the correct workflow branch based on session.status.

All five build-plan fixes converge here:
  FIX #1 (router stickiness)     -- handled inside InferenceRouter, transparent to this file
  FIX #2 (per-field validation)  -- handled inside extraction.py, transparent to this file
  FIX #3 (reject feedback)       -- WorkflowStatus.AWAITING_CORRECTION branch below
  FIX #4 (concurrent-event guard)-- the possible_new_event check below
  FIX #5 (atomic watch folder)   -- NOT called from here at all (Rule 5) -- only from the
                                     channel's approve-callback handler, by design
"""
from __future__ import annotations

import logging

from app import config
from app.ai.router import InferenceRouter, BothEnginesFailedError
from app.agent.extraction import extract
from app.agent.prompts import build_clarification_question, NEW_EVENT_CONFIRMATION_TEMPLATE, REJECTION_FOLLOWUP
from app.models.session import Session, WorkflowStatus
from app.rendering.engine import render_event_graphic

logger = logging.getLogger("tekihelp.orchestrator")


class AgentReply:
    """What the orchestrator hands back to the channel adapter to send."""

    def __init__(self, text: str | None = None, image_path: str | None = None, offer_approval: bool = False) -> None:
        self.text = text
        self.image_path = image_path
        self.offer_approval = offer_approval


class Orchestrator:
    def __init__(self, router: InferenceRouter) -> None:
        self._router = router

    def handle_message(self, session: Session, message: str) -> AgentReply:
        session.add_message("user", message)

        # Rule 8: max-iteration safety cap. Safe termination deliberately
        # means a CLEAN RESTART, not a dead-ended session: reset_event()
        # below sets status back to COLLECTING with iteration_count=0 and
        # all fields cleared, so the operator's next message begins a
        # genuinely fresh attempt rather than leaving them stuck in ENDED.
        session.iteration_count += 1
        if session.iteration_count > config.MAX_AGENT_ITERATIONS:
            reply = AgentReply(
                text=(
                    "I'm having trouble completing this event from our conversation. "
                    "Let's start over -- please send the announcement again with as much "
                    "detail as you can (what, when, where)."
                )
            )
            session.add_message("agent", reply.text)
            session.reset_event()
            return reply

        if session.status == WorkflowStatus.AWAITING_CORRECTION:
            return self._handle_correction_turn(session, message)

        if session.status == WorkflowStatus.AWAITING_APPROVAL:
            # Operator sent text while a preview is pending -- treat it as
            # additional info for the SAME event rather than confusing it.
            return self._handle_collecting_turn(session, message)

        if session.awaiting_new_event_confirmation:
            return self._handle_new_event_confirmation(session, message)

        return self._handle_collecting_turn(session, message)

    # ------------------------------------------------------------------
    # Branch: normal slot-filling (Observe -> Reason -> Act)
    # ------------------------------------------------------------------
    def _handle_collecting_turn(self, session: Session, message: str) -> AgentReply:
        try:
            outcome = extract(self._router, session, message)
        except BothEnginesFailedError:
            reply = AgentReply(
                text=(
                    "I couldn't reach either the primary or backup AI engine just now. "
                    "Please try again in a moment."
                )
            )
            session.add_message("agent", reply.text)
            return reply

        # Rule 4: nullification -- non-events never touch the event state.
        if not outcome.is_event:
            reply = AgentReply(text="Okay, noted -- let me know if you have an event announcement to share.")
            session.add_message("agent", reply.text)
            return reply

        # FIX #4: concurrent-event guard.
        if outcome.possible_new_event and not session.current_event.is_complete() and any(
            getattr(session.current_event, f) is not None for f in ("title", "date", "time", "venue")
        ):
            session.awaiting_new_event_confirmation = True
            hint = outcome.partial_event.title or message[:40]
            reply = AgentReply(text=NEW_EVENT_CONFIRMATION_TEMPLATE.format(new_hint=hint))
            session.add_message("agent", reply.text)
            return reply

        session.current_event = session.current_event.merge(outcome.partial_event)

        if not session.current_event.is_complete():
            missing = session.current_event.missing_fields()[0]
            question = build_clarification_question(missing, session.current_event.title)
            reply = AgentReply(text=question)
            session.add_message("agent", reply.text)
            return reply

        # Rule 1: atomic rendering -- only reachable once is_complete() is true,
        # and to_validated() cannot construct an object with a missing field.
        validated = session.current_event.to_validated()
        preview_path = render_event_graphic(validated)
        session.pending_preview_path = preview_path
        session.status = WorkflowStatus.AWAITING_APPROVAL

        caption = f"{validated.title}\n{validated.display_date()} at {validated.time}\n{validated.venue}"
        reply = AgentReply(text=None, image_path=preview_path, offer_approval=True)
        session.add_message("agent", f"[sent preview for approval: {caption}]")
        return reply

    # ------------------------------------------------------------------
    # Branch: FIX #3 -- after a Reject, next message is a targeted correction
    # ------------------------------------------------------------------
    def _handle_correction_turn(self, session: Session, message: str) -> AgentReply:
        try:
            outcome = extract(self._router, session, message)
        except BothEnginesFailedError:
            reply = AgentReply(text="I couldn't reach either AI engine to process that correction. Please try again shortly.")
            session.add_message("agent", reply.text)
            return reply

        session.current_event = session.current_event.merge(outcome.partial_event)
        session.status = WorkflowStatus.COLLECTING

        if not session.current_event.is_complete():
            missing = session.current_event.missing_fields()[0]
            question = build_clarification_question(missing, session.current_event.title)
            reply = AgentReply(text=f"Got it. {question}")
            session.add_message("agent", reply.text)
            return reply

        validated = session.current_event.to_validated()
        preview_path = render_event_graphic(validated)
        session.pending_preview_path = preview_path
        session.status = WorkflowStatus.AWAITING_APPROVAL
        reply = AgentReply(text=None, image_path=preview_path, offer_approval=True)
        session.add_message("agent", "[sent corrected preview for approval]")
        return reply

    # ------------------------------------------------------------------
    # Branch: FIX #4 -- resolving the new-vs-continuation ambiguity
    # ------------------------------------------------------------------
    def _handle_new_event_confirmation(self, session: Session, message: str) -> AgentReply:
        session.awaiting_new_event_confirmation = False
        affirmative = any(w in message.lower() for w in ("new", "different", "separate", "another", "yes"))
        if affirmative:
            session.reset_event()
            reply = AgentReply(text="Starting a new event -- please go ahead and tell me about it.")
            session.add_message("agent", reply.text)
            return reply
        # Otherwise treat the ORIGINAL triggering message as continuation info.
        return self._handle_collecting_turn(session, message)

    # ------------------------------------------------------------------
    # Called by the channel adapter's Reject button handler
    # ------------------------------------------------------------------
    def handle_rejection(self, session: Session) -> AgentReply:
        session.status = WorkflowStatus.AWAITING_CORRECTION
        reply = AgentReply(text=REJECTION_FOLLOWUP)
        session.add_message("agent", reply.text)
        return reply

    # ------------------------------------------------------------------
    # Called by the channel adapter's Approve button handler.
    # NOTE: this method does NOT write to the Watch Folder itself --
    # Rule 5 requires that only happen from the approval callback in
    # main.py, keeping "who is allowed to publish" auditable in one place.
    # ------------------------------------------------------------------
    def handle_approval(self, session: Session) -> AgentReply:
        session.status = WorkflowStatus.COMPLETED
        self._router.reset_stickiness(session.session_key)
        reply = AgentReply(text="Approved. Sending to the broadcast system.")
        session.add_message("agent", reply.text)
        return reply
