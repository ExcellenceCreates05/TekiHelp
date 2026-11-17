from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.event import PartialEvent
from app.models.session import Message, Session, WorkflowStatus
from app.storage.database import (
    SCHEMA_VERSION,
    SQLiteSessionStore,
    SessionHistoryMismatchError,
    StaleSessionError,
)


def create_legacy_database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_key TEXT PRIMARY KEY,
                channel TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                status TEXT NOT NULL,
                pending_preview_path TEXT,
                iteration_count INTEGER NOT NULL DEFAULT 0,
                awaiting_new_event_confirmation INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL REFERENCES sessions(session_key),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL REFERENCES sessions(session_key),
                title TEXT,
                date TEXT,
                time TEXT,
                venue TEXT,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE graphics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT NOT NULL REFERENCES sessions(session_key),
                preview_path TEXT,
                final_path TEXT,
                approval_status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO sessions (
                session_key, channel, chat_id, status, iteration_count,
                awaiting_new_event_confirmation, created_at, updated_at
            ) VALUES (
                'telegram:legacy', 'telegram', 'legacy', 'collecting', 2, 0,
                'created', 'updated'
            );
            INSERT INTO messages (session_key, role, content, timestamp)
            VALUES ('telegram:legacy', 'user', 'old message', 'message-time');
            INSERT INTO events (
                session_key, title, date, time, venue, status, updated_at
            ) VALUES (
                'telegram:legacy', 'Existing event', '2026-10-17', '08:00 AM',
                'Main Church', 'collecting', 'event-time'
            );
            INSERT INTO graphics (
                session_key, preview_path, final_path, approval_status, created_at
            ) VALUES (
                'telegram:legacy', 'preview.png', NULL, 'pending', 'graphic-time'
            );
            """
        )


def test_legacy_database_migration_preserves_rows_and_defaults_confirmation(tmp_path):
    db_path = tmp_path / "legacy.db"
    create_legacy_database(db_path)

    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "legacy")

    assert session.awaiting_final_confirmation is False
    assert session.current_event.title == "Existing event"
    assert [(message.role, message.content) for message in session.history] == [
        ("user", "old message")
    ]

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        assert "awaiting_final_confirmation" in columns
        assert conn.execute(
            """SELECT status, iteration_count, awaiting_final_confirmation
               FROM sessions WHERE session_key = ?""",
            ("telegram:legacy",),
        ).fetchone() == ("collecting", 2, 0)
        assert conn.execute(
            "SELECT role, content, timestamp FROM messages"
        ).fetchall() == [("user", "old message", "message-time")]
        assert conn.execute(
            """SELECT title, date, time, venue, status, updated_at
               FROM events"""
        ).fetchall() == [
            ("Existing event", "2026-10-17", "08:00 AM", "Main Church", "collecting", "event-time")
        ]
        assert conn.execute(
            """SELECT preview_path, final_path, approval_status, created_at
               FROM graphics"""
        ).fetchall() == [("preview.png", None, "pending", "graphic-time")]

    SQLiteSessionStore(str(db_path))
    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(sessions)")]
        assert columns.count("awaiting_final_confirmation") == 1
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_new_database_migrates_to_current_version(tmp_path):
    db_path = tmp_path / "new.db"

    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "new")

    assert session.awaiting_final_confirmation is False
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_save_reload_appends_messages_and_updates_event_in_place(tmp_path):
    db_path = tmp_path / "session.db"
    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "1")
    session.current_event = PartialEvent(
        title="Men's Breakfast",
        date="2026-10-17",
        time="08:00 AM",
        venue="Main Church",
    )
    session.awaiting_final_confirmation = True
    session.add_message("user", "first message")
    session.add_message("agent", "confirm this event")
    store.save(session)

    loaded = store.get_or_create("telegram", "1")
    assert loaded.awaiting_final_confirmation is True
    assert [message.content for message in loaded.history] == [
        "first message",
        "confirm this event",
    ]

    with sqlite3.connect(db_path) as conn:
        original_message_rows = conn.execute(
            "SELECT id, role, content, timestamp FROM messages ORDER BY id"
        ).fetchall()
        original_event = conn.execute(
            "SELECT id FROM events WHERE session_key = ?", ("telegram:1",)
        ).fetchone()[0]

    loaded.awaiting_final_confirmation = False
    loaded.current_event.date = "2026-10-24"
    loaded.add_message("user", "one week later")
    store.save(loaded)

    reloaded = store.get_or_create("telegram", "1")
    assert reloaded.awaiting_final_confirmation is False
    assert [message.content for message in reloaded.history] == [
        "first message",
        "confirm this event",
        "one week later",
    ]
    assert reloaded.current_event.date == "2026-10-24"

    with sqlite3.connect(db_path) as conn:
        message_rows = conn.execute(
            "SELECT id, role, content, timestamp FROM messages ORDER BY id"
        ).fetchall()
        event_rows = conn.execute(
            "SELECT id, date FROM events WHERE session_key = ?", ("telegram:1",)
        ).fetchall()

    assert message_rows[: len(original_message_rows)] == original_message_rows
    assert len(message_rows) == len(original_message_rows) + 1
    assert event_rows == [(original_event, "2026-10-24")]


def test_failed_save_rolls_back_session_and_event_updates(tmp_path):
    db_path = tmp_path / "rollback.db"
    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "1")
    session.current_event = PartialEvent(title="Original event")
    store.save(session)

    session.status = WorkflowStatus.COMPLETED
    session.current_event.title = "Unsaved event"
    session.history.append(Message(role=None, content="invalid message"))

    with pytest.raises(sqlite3.IntegrityError):
        store.save(session)

    reloaded = store.get_or_create("telegram", "1")
    assert reloaded.status == WorkflowStatus.COLLECTING
    assert reloaded.current_event.title == "Original event"
    assert reloaded.history == []


def test_save_rejects_stale_session_version(tmp_path):
    db_path = tmp_path / "version.db"
    store = SQLiteSessionStore(str(db_path))
    first = store.get_or_create("telegram", "version")
    second = store.get_or_create("telegram", "version")

    first.add_message("user", "first")
    store.save(first)

    second.add_message("user", "stale")
    with pytest.raises(StaleSessionError):
        store.save(second)


def test_save_rejects_history_mismatch(tmp_path):
    db_path = tmp_path / "history.db"
    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "history")
    session.history = [Message(role="user", content="one")]
    store.save(session)

    session.history.clear()
    with pytest.raises(SessionHistoryMismatchError):
        store.save(session)


def test_approval_preserves_event_and_starts_next_event_row(tmp_path):
    db_path = tmp_path / "approval.db"
    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "approved")
    session.current_event = PartialEvent(
        title="Approved Breakfast",
        date="2026-10-17",
        time="08:00 AM",
        venue="Main Church",
    )
    session.status = WorkflowStatus.COMPLETED
    store.save(session)

    reloaded = store.get_or_create("telegram", "approved")
    assert reloaded.status == WorkflowStatus.COLLECTING
    assert reloaded.current_event.title is None

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        rows = conn.execute(
            """SELECT title, date, time, venue, status
               FROM events WHERE session_key = ? ORDER BY id""",
            ("telegram:approved",),
        ).fetchall()

    assert rows == [
        ("Approved Breakfast", "2026-10-17", "08:00 AM", "Main Church", "approved"),
        (None, None, None, None, "collecting"),
    ]


def test_foreign_keys_and_indexes_exist(tmp_path):
    db_path = tmp_path / "hygiene.db"
    store = SQLiteSessionStore(str(db_path))
    store.get_or_create("telegram", "hygiene")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert "idx_messages_session_id" in indexes
        assert "idx_events_session_id" in indexes
        assert "idx_graphics_session" in indexes

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO messages
                   (session_key, role, content, timestamp)
                   VALUES (?, 'user', 'orphan', 'now')""",
                ("telegram:missing",),
            )


def test_legacy_pending_preview_is_cleared(tmp_path):
    db_path = tmp_path / "legacy-preview.db"
    create_legacy_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """UPDATE sessions
               SET status='awaiting_approval', pending_preview_path='preview.png'
               WHERE session_key='telegram:legacy'""",
        )

    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "legacy")

    assert session.pending_preview_path is None
    assert session.pending_preview_id is None
    assert session.status == WorkflowStatus.COLLECTING


def test_concurrent_claim_delivers_once_and_failure_is_recoverable(tmp_path):
    db_path = tmp_path / "claim.db"
    first_store = SQLiteSessionStore(str(db_path))
    session = first_store.get_or_create("telegram", "claim")
    session.status = WorkflowStatus.AWAITING_APPROVAL
    session.pending_preview_path = "preview_abc123.png"
    session.pending_preview_id = "abc123"
    first_store.save(session)

    first_store = SQLiteSessionStore(str(db_path))
    second_store = SQLiteSessionStore(str(db_path))
    first_claim = first_store.claim_preview(
        "telegram:claim", "abc123", "approve", 120
    )
    second_claim = second_store.claim_preview(
        "telegram:claim", "abc123", "approve", 120
    )

    assert first_claim is not None
    assert second_claim is None
    assert first_store.fail_delivery(
        "telegram:claim",
        "abc123",
        "preview_abc123.png",
        first_claim,
    )

    retry_claim = second_store.claim_preview(
        "telegram:claim", "abc123", "approve", 120
    )
    assert retry_claim is not None
    assert first_store.complete_delivery(
        "telegram:claim",
        "abc123",
        "preview_abc123.png",
        "watch_folder/preview_abc123.png",
        retry_claim,
    )
    assert not second_store.complete_delivery(
        "telegram:claim",
        "abc123",
        "preview_abc123.png",
        "watch_folder/preview_abc123.png",
        retry_claim,
    )


def test_expired_claim_can_be_claimed_again(tmp_path):
    db_path = tmp_path / "expired.db"
    store = SQLiteSessionStore(str(db_path))
    session = store.get_or_create("telegram", "expired")
    session.status = WorkflowStatus.AWAITING_APPROVAL
    session.pending_preview_path = "preview_expired.png"
    session.pending_preview_id = "expired"
    store.save(session)

    first_claim = store.claim_preview(
        "telegram:expired", "expired", "approve", -1
    )
    assert first_claim is not None

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """UPDATE sessions
               SET status='delivering',
                   claim_expires_at='2000-01-01T00:00:00+00:00'
               WHERE session_key='telegram:expired'"""
        )

    retry_claim = store.claim_preview(
        "telegram:expired", "expired", "approve", 120
    )
    assert retry_claim is not None
