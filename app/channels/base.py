"""
Message Gateway abstraction.

Both the Telegram adapter (Week 1) and the Discord adapter (Week 3)
implement this interface. The agent orchestrator only ever talks to
a ChannelAdapter -- it has no idea whether a reply is going out over
Telegram or Discord. This is what makes adding a second channel in
Week 3 a matter of writing one new file, not touching the agent.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    name: str

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> None:
        ...

    @abstractmethod
    async def send_image_with_approval_buttons(self, chat_id: str, image_path: str, caption: str) -> None:
        """Sends the rendered preview with Approve/Reject controls."""
        ...

    @abstractmethod
    def is_authorized(self, chat_id: str) -> bool:
        ...
