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
from typing import Callable

from app import config
from app.models.event import PartialEvent
from app.models.session import Message, Session, WorkflowStatus

SCHEMA_VERSION = 1

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS sessions (
        session_key TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        status TEXT NOT NULL,
        pending_preview_path TEXT,
        iteration_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL REFERENCES sessions(session_key),
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL REFERENCES sessions(session_key),
        title TEXT,
        date TEXT,
        time TEXT,
        venue TEXT,
        status TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS graphics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_key TEXT NOT NULL REFERENCES sessions(session_key),
        preview_path TEXT,
        final_path TEXT,
        approval_status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
)


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn, "sessions", "awaiting_new_event_confirmation", "INTEGER NOT NULL DEFAULT 0"
    )
    _add_column_if_missing(
        conn, "sessions", "awaiting_final_confirmation", "INTEGER NOT NULL DEFAULT 0"
    )


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migrate_to_v1,
}


class SQLiteSessionStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or str(config.DATABASE_PATH)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for statement in SCHEMA:
                conn.execute(statement)

            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than supported "
                    f"version {SCHEMA_VERSION}"
                )

            while version < SCHEMA_VERSION:
                next_version = version + 1
                migration = MIGRATIONS.get(next_version)
                if migration is None:
                    raise RuntimeError(f"No migration registered for schema version {next_version}")
                migration(conn)
                conn.execute(f"PRAGMA user_version = {next_version}")
                version = next_version

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
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
                        awaiting_final_confirmation, awaiting_new_event_confirmation,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?)""",
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
                awaiting_final_confirmation=bool(row["awaiting_final_confirmation"]),
                awaiting_new_event_confirmation=bool(row["awaiting_new_event_confirmation"]),
            )

    def save(self, session: Session) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE sessions SET status=?, pending_preview_path=?, iteration_count=?,
                   awaiting_final_confirmation=?, awaiting_new_event_confirmation=?,
                   updated_at=? WHERE session_key=?""",
                (
                    session.status.value,
                    session.pending_preview_path,
                    session.iteration_count,
                    int(session.awaiting_final_confirmation),
                    int(session.awaiting_new_event_confirmation),
                    now,
                    session.session_key,
                ),
            )
            event = conn.execute(
                "SELECT id FROM events WHERE session_key = ? ORDER BY id DESC LIMIT 1",
                (session.session_key,),
            ).fetchone()
            event_values = (
                session.current_event.title,
                session.current_event.date,
                session.current_event.time,
                session.current_event.venue,
                session.status.value,
                now,
            )
            if event is None:
                conn.execute(
                    """INSERT INTO events
                       (session_key, title, date, time, venue, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (session.session_key, *event_values),
                )
            else:
                conn.execute(
                    """UPDATE events SET title=?, date=?, time=?, venue=?, status=?, updated_at=?
                       WHERE id=?""",
                    (*event_values, event["id"]),
                )

            stored_messages = conn.execute(
                """SELECT role, content, timestamp FROM messages
                   WHERE session_key = ? ORDER BY id ASC""",
                (session.session_key,),
            ).fetchall()
            if len(stored_messages) > len(session.history):
                raise ValueError("Session history is older than its persisted message history")

            for index, row in enumerate(stored_messages):
                message = session.history[index]
                if (row["role"], row["content"], row["timestamp"]) != (
                    message.role,
                    message.content,
                    message.timestamp,
                ):
                    raise ValueError("Session history does not match persisted message history")

            new_messages = session.history[len(stored_messages):]
            if new_messages:
                conn.executemany(
                    "INSERT INTO messages (session_key, role, content, timestamp) VALUES (?, ?, ?, ?)",
                    [
                        (session.session_key, m.role, m.content, m.timestamp)
                        for m in new_messages
                    ],
                )

    def log_graphic(self, session_key: str, preview_path: str, final_path: str | None, approval_status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO graphics (session_key, preview_path, final_path, approval_status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_key, preview_path, final_path, approval_status, datetime.now(timezone.utc).isoformat()),
            )
