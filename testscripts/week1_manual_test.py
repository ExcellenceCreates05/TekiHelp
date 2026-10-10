"""
Week 1 Day 6-7 milestone script.

Run this directly (no Telegram needed yet) to prove the pipeline works
end-to-end for a SINGLE message that already contains all four fields:

    python scripts/week1_manual_test.py "Men's breakfast Saturday 3 October 2026 at 8am at Main Church"

This exercises: router -> extraction -> PartialEvent -> ValidatedEvent
-> Pillow render -> (simulated approval) -> atomic Watch Folder write.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.router import InferenceRouter
from app.agent.extraction import extract
from app.broadcast.watch_folder import deliver_to_watch_folder
from app.models.session import Session
from app.rendering.engine import render_event_graphic


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/week1_manual_test.py \"<announcement text>\"")
        sys.exit(1)

    message = sys.argv[1]
    session = Session(session_key="manual:test", channel="manual", chat_id="test")
    router = InferenceRouter()

    print(f"Input message: {message!r}\n")

    outcome = extract(router, session, message)
    print(f"Engine used: {outcome.engine_used} (fell back: {outcome.fell_back})")
    if outcome.dropped_fields:
        print(f"Dropped (unnormalized) fields: {outcome.dropped_fields}")
    print(f"is_event: {outcome.is_event}")
    print(f"Extracted: {outcome.partial_event.model_dump()}\n")

    if not outcome.is_event:
        print("Classified as non-event. Nothing to render.")
        return

    session.current_event = session.current_event.merge(outcome.partial_event)

    if not session.current_event.is_complete():
        print(f"Still missing: {session.current_event.missing_fields()}")
        print("(In the real bot, the agent would now ask a clarification question.)")
        return

    validated = session.current_event.to_validated()
    print(f"Validated event: {validated.model_dump()}\n")

    preview_path = render_event_graphic(validated)
    print(f"Rendered preview: {preview_path}")

    # Simulate operator approval for this manual test.
    final_path = deliver_to_watch_folder(preview_path)
    print(f"Delivered to Watch Folder (atomic write): {final_path}")


if __name__ == "__main__":
    main()
