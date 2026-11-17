from __future__ import annotations

from unittest.mock import MagicMock

from app import config
from app.agent.orchestrator import Orchestrator
from app.models.session import WorkflowStatus
from app.storage.database import SQLiteSessionStore


def make_router(payload):
    router = MagicMock()
    result = MagicMock()
    result.parsed = payload
    result.engine_used = "gemini"
    result.fell_back = False
    router.generate_structured.return_value = result
    return router


def test_sqlite_reload_confirmation_correction_and_preview_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREVIEW_FOLDER_PATH", tmp_path)
    db_path = tmp_path / "e2e.db"
    store = SQLiteSessionStore(str(db_path))

    router = make_router({
        "title": "Men's Breakfast",
        "date": "2026-10-17",
        "time": "08:00 AM",
        "venue": "Main Church",
        "is_event": True,
        "possible_new_event": False,
    })
    orch = Orchestrator(router)

    session = store.get_or_create("telegram", "e2e")
    reply = orch.handle_message(session, "Men's breakfast Saturday 8am Main Church")
    store.save(session)

    session = store.get_or_create("telegram", "e2e")
    assert session.awaiting_final_confirmation is True
    assert reply.offer_approval is False

    router.generate_structured.return_value.parsed = {
        "title": "Men's Breakfast",
        "date": None,
        "time": None,
        "venue": None,
        "is_event": True,
        "possible_new_event": False,
    }
    correction_reply = orch.handle_message(session, "no, it is on Monday")
    store.save(session)

    session = store.get_or_create("telegram", "e2e")
    assert correction_reply.offer_approval is False
    assert session.status == WorkflowStatus.AWAITING_CORRECTION

    router.generate_structured.return_value.parsed = {
        "title": None,
        "date": "2026-10-19",
        "time": None,
        "venue": None,
        "is_event": True,
        "possible_new_event": False,
    }
    corrected = orch.handle_message(session, "It is Monday")
    store.save(session)
    session = store.get_or_create("telegram", "e2e")

    assert corrected.offer_approval is False
    assert session.awaiting_final_confirmation is True

    confirmed = orch.handle_message(session, "yes")
    store.save(session)
    session = store.get_or_create("telegram", "e2e")

    assert confirmed.offer_approval is True
    assert session.status == WorkflowStatus.AWAITING_APPROVAL
    assert session.pending_preview_id


def test_authorized_claim_repeat_and_delivery_failure(tmp_path):
    db_path = tmp_path / "approval.db"
    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("discord", "approval")
    session.status = WorkflowStatus.AWAITING_APPROVAL
    session.pending_preview_path = str(tmp_path / "preview_abc123.png")
    session.pending_preview_id = "abc123"
    (tmp_path / "preview_abc123.png").write_bytes(b"preview")
    store.save(session)

    claim = store.claim_preview(
        "discord:approval",
        "abc123",
        "approve",
        120,
    )
    assert claim is not None
    assert store.fail_delivery(
        "discord:approval",
        "abc123",
        session.pending_preview_path,
        claim,
    )

    retry = store.claim_preview(
        "discord:approval",
        "abc123",
        "approve",
        120,
    )
    assert retry is not None
    assert store.complete_delivery(
        "discord:approval",
        "abc123",
        session.pending_preview_path,
        str(tmp_path / "watch_folder" / "preview_abc123.png"),
        retry,
    )
    assert not store.complete_delivery(
        "discord:approval",
        "abc123",
        session.pending_preview_path,
        str(tmp_path / "watch_folder" / "preview_abc123.png"),
        retry,
    )
