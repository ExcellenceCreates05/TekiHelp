"""
SQLite persistence layer -- Week 2, Day 8-9.

Implements the four tables from the brief (sessions, messages, events,
graphics). Exposes the SAME get_or_create/save interface as
InMemorySessionStore (Week 1) so app/agent/orchestrator.py doesn't care
which backend is wired in -- see app/main.py for the single line that
chooses.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app import config
from app.models.event import PartialEvent
from app.models.session import Message, Session, WorkflowStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
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

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL REFERENCES sessions(session_key),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL REFERENCES sessions(session_key),
    title TEXT,
    date TEXT,
    time TEXT,
    venue TEXT,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graphics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL REFERENCES sessions(session_key),
    preview_path TEXT,
    final_path TEXT,
    approval_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class SQLiteSessionStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or str(config.DATABASE_PATH)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_or_create(self, channel: str, chat_id: str) -> Session:
        key = f"{channel}:{chat_id}"
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_key = ?", (key,)).fetchone()
            if row is None:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """INSERT INTO sessions
                       (session_key, channel, chat_id, status, iteration_count,
                        awaiting_new_event_confirmation, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 0, 0, ?, ?)""",
                    (key, channel, chat_id, WorkflowStatus.COLLECTING.value, now, now),
                )
                conn.execute(
                    """INSERT INTO events (session_key, status, updated_at)
                       VALUES (?, ?, ?)""",
                    (key, WorkflowStatus.COLLECTING.value, now),
                )
                return Session(session_key=key, channel=channel, chat_id=chat_id)

            event_row = conn.execute(
                "SELECT * FROM events WHERE session_key = ? ORDER BY id DESC LIMIT 1", (key,)
            ).fetchone()
            message_rows = conn.execute(
                "SELECT role, content, timestamp FROM messages WHERE session_key = ? ORDER BY id ASC",
                (key,),
            ).fetchall()

            event = PartialEvent(
                title=event_row["title"] if event_row else None,
                date=event_row["date"] if event_row else None,
                time=event_row["time"] if event_row else None,
                venue=event_row["venue"] if event_row else None,
            )
            history = [Message(role=m["role"], content=m["content"], timestamp=m["timestamp"]) for m in message_rows]

            return Session(
                session_key=key,
                channel=row["channel"],
                chat_id=row["chat_id"],
                history=history,
                current_event=event,
                status=WorkflowStatus(row["status"]),
                pending_preview_path=row["pending_preview_path"],
                iteration_count=row["iteration_count"],
                awaiting_new_event_confirmation=bool(row["awaiting_new_event_confirmation"]),
            )

    def save(self, session: Session) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE sessions SET status=?, pending_preview_path=?, iteration_count=?,
                   awaiting_new_event_confirmation=?, updated_at=? WHERE session_key=?""",
                (
                    session.status.value,
                    session.pending_preview_path,
                    session.iteration_count,
                    int(session.awaiting_new_event_confirmation),
                    now,
                    session.session_key,
                ),
            )
            conn.execute(
                """INSERT INTO events (session_key, title, date, time, venue, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.session_key,
                    session.current_event.title,
                    session.current_event.date,
                    session.current_event.time,
                    session.current_event.venue,
                    session.status.value,
                    now,
                ),
            )
            # Persist only messages not already stored (naive approach: clear + rewrite
            # is simpler for a 5-week project than diffing; conversations here are short).
            conn.execute("DELETE FROM messages WHERE session_key = ?", (session.session_key,))
            conn.executemany(
                "INSERT INTO messages (session_key, role, content, timestamp) VALUES (?, ?, ?, ?)",
                [(session.session_key, m.role, m.content, m.timestamp) for m in session.history],
            )

    def log_graphic(self, session_key: str, preview_path: str, final_path: str | None, approval_status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO graphics (session_key, preview_path, final_path, approval_status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_key, preview_path, final_path, approval_status, datetime.now(timezone.utc).isoformat()),
            )
