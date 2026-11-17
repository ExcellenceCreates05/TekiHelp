"""
Discord bot runner (Week 3). Run alongside or instead of app/main.py with:

    python -m app.channels.discord_runner

Notice how little is here: the orchestrator, extraction, rendering and
Watch Folder logic are 100% shared with Telegram. This is the proof that
the Message Gateway abstraction from the original brief actually pays
off, rather than just being a diagram.
"""
from __future__ import annotations

import logging

import discord

from app import config
from app.agent.orchestrator import Orchestrator
from app.ai.router import InferenceRouter
from app.broadcast.watch_folder import deliver_to_watch_folder
from app.channels.discord_adapter import DiscordAdapter
from app.models.session import WorkflowStatus
from app.storage.database import (
    SQLiteSessionStore,
    SessionHistoryMismatchError,
    StaleSessionError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tekihelp.discord_runner")

if config.ALLOW_OPEN_ACCESS:
    logger.warning("ALLOW_OPEN_ACCESS=true: submission allowlists are open for local development")

router = InferenceRouter()
orchestrator = Orchestrator(router)
store = SQLiteSessionStore()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
adapter: DiscordAdapter | None = None


async def handle_approve(chat_id: str, user_id: str, preview_id: str, interaction, view) -> None:
    if not adapter.is_authorized(chat_id):
        await interaction.response.send_message("This channel is not authorized.", ephemeral=True)
        return
    if not adapter.is_operator_authorized(user_id):
        await interaction.response.send_message(
            "Operator authorization is not configured or this user is not authorized.",
            ephemeral=True,
        )
        return

    session = store.get_or_create("discord", chat_id)
    if session.pending_preview_id != preview_id:
        await interaction.response.send_message("This preview has expired or is stale.", ephemeral=True)
        return
    if session.status != WorkflowStatus.AWAITING_APPROVAL:
        await interaction.response.send_message("This preview has expired.", ephemeral=True)
        return
    if not session.pending_preview_path or session.awaiting_final_confirmation:
        await interaction.response.send_message("This preview is no longer valid.", ephemeral=True)
        return

    claim_owner = store.claim_preview(
        session.session_key,
        preview_id,
        "approve",
        config.DELIVERY_CLAIM_TIMEOUT_S,
    )
    if not claim_owner:
        await interaction.response.send_message(
            "This preview is no longer valid or is already being handled.",
            ephemeral=True,
        )
        return

    for item in view.children:
        item.disabled = True
    await interaction.response.edit_message(view=view)

    reply = orchestrator.handle_approval(session)
    approved_path = reply.approved_path or session.pending_preview_path
    if not approved_path:
        await interaction.followup.send("This preview is no longer valid.", ephemeral=True)
        return
    try:
        final_path = deliver_to_watch_folder(approved_path)
    except Exception as exc:
        store.fail_delivery(
            session.session_key,
            preview_id,
            approved_path,
            claim_owner,
        )
        await interaction.followup.send(
            f"Delivery failed and is recoverable. Please retry approval. {exc}",
            ephemeral=True,
        )
        return

    if not store.complete_delivery(
        session.session_key,
        preview_id,
        approved_path,
        final_path,
        claim_owner,
    ):
        await interaction.followup.send("This preview was already handled.", ephemeral=True)
        return
    await interaction.followup.send(reply.text, ephemeral=True)


async def handle_reject(chat_id: str, user_id: str, preview_id: str, interaction, view) -> None:
    if not adapter.is_authorized(chat_id):
        await interaction.response.send_message("This channel is not authorized.", ephemeral=True)
        return
    if not adapter.is_operator_authorized(user_id):
        await interaction.response.send_message(
            "Operator authorization is not configured or this user is not authorized.",
            ephemeral=True,
        )
        return

    session = store.get_or_create("discord", chat_id)
    if session.pending_preview_id != preview_id:
        await interaction.response.send_message("This preview has expired or is stale.", ephemeral=True)
        return
    if session.status != WorkflowStatus.AWAITING_APPROVAL:
        await interaction.response.send_message("This preview has expired.", ephemeral=True)
        return
    if not session.pending_preview_path or session.awaiting_final_confirmation:
        await interaction.response.send_message("This preview is no longer valid.", ephemeral=True)
        return

    claim_owner = store.claim_preview(
        session.session_key,
        preview_id,
        "reject",
        config.DELIVERY_CLAIM_TIMEOUT_S,
    )
    if not claim_owner:
        await interaction.response.send_message(
            "This preview is no longer valid or is already being handled.",
            ephemeral=True,
        )
        return

    for item in view.children:
        item.disabled = True
    await interaction.response.edit_message(view=view)

    reply = orchestrator.handle_rejection(session)
    if reply.rejected_path:
        store.complete_rejection(
            session.session_key,
            preview_id,
            reply.rejected_path,
            claim_owner,
        )
    await interaction.followup.send(reply.text, ephemeral=True)


@client.event
async def on_ready():
    global adapter
    adapter = DiscordAdapter(client, handle_approve, handle_reject)
    logger.info("Tekihelp Discord bot ready as %s", client.user)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    chat_id = str(message.channel.id)
    if not adapter.is_authorized(chat_id):
        return

    session = store.get_or_create("discord", chat_id)
    reply = orchestrator.handle_message(session, message.content)
    try:
        store.save(session)
    except (StaleSessionError, SessionHistoryMismatchError):
        await adapter.send_text(
            chat_id,
            "That action is no longer valid, please try again.",
        )
        return

    if reply.offer_approval and reply.image_path:
        await adapter.send_image_with_approval_buttons(
            chat_id,
            reply.image_path,
            "Preview ready. Approve or Reject below.",
            session.pending_preview_id,
        )
    elif reply.text:
        await adapter.send_text(chat_id, reply.text)


def main() -> None:
    if not config.DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")
    client.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
