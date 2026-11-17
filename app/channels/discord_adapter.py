"""
Discord channel adapter (Week 3, Day 17-19) -- the stretch second channel.

Discord implements the same
ChannelAdapter interface as Telegram, so the orchestrator, extraction,
rendering, and Watch Folder code are reused completely unchanged.
"""
from __future__ import annotations

import io

import discord

from app import config
from app.channels.base import ChannelAdapter


class ApprovalView(discord.ui.View):
    def __init__(self, on_approve, on_reject, chat_id: str, preview_id: str):
        super().__init__(timeout=None)
        self._on_approve = on_approve
        self._on_reject = on_reject
        self._chat_id = chat_id
        self._preview_id = preview_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_approve(
            self._chat_id,
            str(interaction.user.id),
            self._preview_id,
            interaction,
            self,
        )

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_reject(
            self._chat_id,
            str(interaction.user.id),
            self._preview_id,
            interaction,
            self,
        )


class DiscordAdapter(ChannelAdapter):
    name = "discord"

    def __init__(self, client: discord.Client, on_approve, on_reject) -> None:
        self._client = client
        self._on_approve = on_approve
        self._on_reject = on_reject

    def is_authorized(self, chat_id: str) -> bool:
        if not config.DISCORD_AUTHORIZED_CHANNEL_IDS:
            return config.ALLOW_OPEN_ACCESS
        return str(chat_id) in config.DISCORD_AUTHORIZED_CHANNEL_IDS

    def is_operator_authorized(self, user_id: str) -> bool:
        if not config.DISCORD_AUTHORIZED_USER_IDS:
            return False
        return str(user_id) in config.DISCORD_AUTHORIZED_USER_IDS

    async def send_text(self, chat_id: str, text: str) -> None:
        channel = self._client.get_channel(int(chat_id))
        await channel.send(text)

    async def send_image_with_approval_buttons(
        self,
        chat_id: str,
        image_path: str,
        caption: str,
        preview_id: str | None = None,
    ) -> None:
        channel = self._client.get_channel(int(chat_id))
        with open(image_path, "rb") as f:
            data = io.BytesIO(f.read())
        file = discord.File(data, filename="preview.png")
        preview_id = preview_id or "expired"
        view = ApprovalView(self._on_approve, self._on_reject, chat_id, preview_id)
        await channel.send(content=caption, file=file, view=view)
