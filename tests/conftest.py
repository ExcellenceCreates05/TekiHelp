"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.session import Session


@pytest.fixture
def fresh_session() -> Session:
    return Session(session_key="test:1", channel="test", chat_id="1")
