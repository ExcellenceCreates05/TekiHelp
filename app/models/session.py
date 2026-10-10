"""
Session state -- one per conversation (keyed by channel + chat_id).

This is the in-memory representation; app/storage/database.py persists
it to SQLite. Keeping the dataclass separate from the DB layer means
the agent logic never has to know about SQL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app.models.event import PartialEvent


class WorkflowStatus(str, Enum):
    COLLECTING = "collecting"          # still gathering slots
    AWAITING_APPROVAL = "awaiting_approval"  # rendered, waiting on operator
    AWAITING_CORRECTION = "awaiting_correction"  # FIX #3: rejected, waiting for what to fix
    COMPLETED = "completed"            # approved and delivered
    ENDED = "ended"                    # non-event or terminated


@dataclass
class Message:
    role: str  # "user" | "agent"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Session:
    session_key: str  # e.g. "telegram:82736491" or "discord:9981..."
    channel: str
    chat_id: str
    history: list[Message] = field(default_factory=list)
    current_event: PartialEvent = field(default_factory=PartialEvent)
    status: WorkflowStatus = WorkflowStatus.COLLECTING
    pending_preview_path: str | None = None
    iteration_count: int = 0
    # FIX #4: a lightweight flag the orchestrator sets when it suspects
    # the newest message might start a *second*, unrelated event while
    # the current one is still incomplete. See agent/orchestrator.py.
    awaiting_new_event_confirmation: bool = False

    def add_message(self, role: str, content: str) -> None:
        self.history.append(Message(role=role, content=content))

    def recent_history_text(self, limit: int = 8) -> str:
        recent = self.history[-limit:]
        return "\n".join(f"{m.role}: {m.content}" for m in recent)

    def reset_event(self) -> None:
        self.current_event = PartialEvent()
        self.status = WorkflowStatus.COLLECTING
        self.pending_preview_path = None
        self.iteration_count = 0
        self.awaiting_new_event_confirmation = False
