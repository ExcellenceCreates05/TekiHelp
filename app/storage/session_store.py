"""
Week 1 session store: in-memory dict, keyed by "channel:chat_id".

This is intentionally the SAME interface that app/storage/database.py
(SQLite-backed, built in Week 2) will expose, so swapping one for the
other is a one-line change in app/agent/orchestrator.py, not a rewrite.
"""
from __future__ import annotations

from app.models.session import Session


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, channel: str, chat_id: str) -> Session:
        key = f"{channel}:{chat_id}"
        if key not in self._sessions:
            self._sessions[key] = Session(session_key=key, channel=channel, chat_id=chat_id)
        return self._sessions[key]

    def save(self, session: Session) -> None:
        self._sessions[session.session_key] = session
