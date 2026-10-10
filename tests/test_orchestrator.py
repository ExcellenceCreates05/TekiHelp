"""
Tests the orchestrator branches, with the InferenceRouter mocked out so
these run offline/deterministically -- including FIX #3 (reject feedback)
and FIX #4 (concurrent-event guard), and Rule 8 (max iterations).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app import config
from app.agent.orchestrator import Orchestrator
from app.models.session import Session, WorkflowStatus


def make_router_returning(payload: dict):
    router = MagicMock()
    result = MagicMock()
    result.parsed = payload
    result.engine_used = "gemini"
    result.fell_back = False
    router.generate_structured.return_value = result
    return router


def test_clarification_asked_when_field_missing():
    router = make_router_returning({
        "title": "Men's Breakfast", "date": "2026-10-17", "time": None, "venue": "Main Church",
        "is_event": True, "possible_new_event": False,
    })
    orch = Orchestrator(router)
    session = Session(session_key="t1", channel="test", chat_id="1")

    reply = orch.handle_message(session, "Men's breakfast Saturday at church")

    assert "time" in reply.text.lower() or "begin" in reply.text.lower()
    assert session.status == WorkflowStatus.COLLECTING


def test_render_offered_when_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREVIEW_FOLDER_PATH", tmp_path)
    router = make_router_returning({
        "title": "Men's Breakfast", "date": "2026-10-17", "time": "08:00 AM", "venue": "Main Church",
        "is_event": True, "possible_new_event": False,
    })
    orch = Orchestrator(router)
    session = Session(session_key="t2", channel="test", chat_id="2")

    reply = orch.handle_message(session, "Men's breakfast Sat 8am Main Church")

    assert reply.offer_approval is True
    assert session.status == WorkflowStatus.AWAITING_APPROVAL


def test_non_event_does_not_touch_event_state():
    router = make_router_returning({
        "title": None, "date": None, "time": None, "venue": None,
        "is_event": False, "possible_new_event": False,
    })
    orch = Orchestrator(router)
    session = Session(session_key="t3", channel="test", chat_id="3")

    orch.handle_message(session, "Please pray for us")

    assert session.current_event.title is None
    assert session.status == WorkflowStatus.COLLECTING


def test_fix3_rejection_asks_for_correction_not_reprompt():
    router = MagicMock()
    orch = Orchestrator(router)
    session = Session(session_key="t4", channel="test", chat_id="4")
    session.status = WorkflowStatus.AWAITING_APPROVAL
    session.pending_preview_path = "/fake/path.png"

    reply = orch.handle_rejection(session)

    assert session.status == WorkflowStatus.AWAITING_CORRECTION
    assert "correct" in reply.text.lower()


def test_fix3_correction_updates_only_targeted_field(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREVIEW_FOLDER_PATH", tmp_path)
    router = make_router_returning({
        "title": None, "date": "2026-10-24", "time": None, "venue": None,  # only date corrected
        "is_event": True, "possible_new_event": False,
    })
    orch = Orchestrator(router)
    session = Session(session_key="t5", channel="test", chat_id="5")
    session.status = WorkflowStatus.AWAITING_CORRECTION
    session.current_event.title = "Men's Breakfast"
    session.current_event.time = "08:00 AM"
    session.current_event.venue = "Main Church"
    session.current_event.date = "2026-10-17"  # wrong date being corrected

    reply = orch.handle_message(session, "Actually it's the 24th")

    assert session.current_event.date == "2026-10-24"
    assert session.current_event.title == "Men's Breakfast"  # untouched fields preserved
    assert reply.offer_approval is True  # now complete again


def test_fix4_concurrent_event_guard_triggers_confirmation():
    router = make_router_returning({
        "title": "Youth Conference", "date": None, "time": None, "venue": "Fellowship Hall",
        "is_event": True, "possible_new_event": True,
    })
    orch = Orchestrator(router)
    session = Session(session_key="t6", channel="test", chat_id="6")
    session.current_event.title = "Men's Breakfast"  # a DIFFERENT event already in progress
    session.current_event.venue = "Main Church"

    reply = orch.handle_message(session, "Also, youth conference at Fellowship Hall")

    assert session.awaiting_new_event_confirmation is True
    assert "new" in reply.text.lower() or "separate" in reply.text.lower()
    # original event must be untouched until the operator confirms
    assert session.current_event.title == "Men's Breakfast"


def test_fix4_confirmation_yes_resets_event():
    router = make_router_returning({
        "title": "Youth Conference", "date": None, "time": None, "venue": None,
        "is_event": True, "possible_new_event": False,
    })
    orch = Orchestrator(router)
    session = Session(session_key="t7", channel="test", chat_id="7")
    session.current_event.title = "Men's Breakfast"
    session.awaiting_new_event_confirmation = True

    orch.handle_message(session, "yes, it's a new event")

    assert session.current_event.title is None  # reset happened


def test_rule8_max_iterations_terminates_safely():
    router = make_router_returning({
        "title": None, "date": None, "time": None, "venue": None,
        "is_event": False, "possible_new_event": False,
    })
    orch = Orchestrator(router)
    session = Session(session_key="t8", channel="test", chat_id="8")
    session.iteration_count = config.MAX_AGENT_ITERATIONS  # already at the cap

    reply = orch.handle_message(session, "hello again")

    # Safe termination means the conversation restarts cleanly, not that it
    # becomes permanently unusable -- reset_event() returns status to
    # COLLECTING with a cleared event and iteration_count, ready for a
    # fresh attempt (see the "let's start over" copy in the reply text).
    assert session.status == WorkflowStatus.COLLECTING
    assert session.current_event.title is None
    assert session.iteration_count == 0
    assert "start over" in reply.text.lower()
