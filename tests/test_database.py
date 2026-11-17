from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.models.event import PartialEvent
from app.models.session import Message, Session, WorkflowStatus
from app.storage.database import SCHEMA_VERSION, SQLiteSessionStore


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
