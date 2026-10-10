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
from app.storage.database import SQLiteSessionStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tekihelp.discord_runner")

router = InferenceRouter()
orchestrator = Orchestrator(router)
store = SQLiteSessionStore()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
adapter: DiscordAdapter | None = None


async def handle_approve(chat_id: str) -> None:
    session = store.get_or_create("discord", chat_id)
    reply = orchestrator.handle_approval(session)
    if session.pending_preview_path:
        final_path = deliver_to_watch_folder(session.pending_preview_path)
        store.log_graphic(session.session_key, session.pending_preview_path, final_path, "approved")
    store.save(session)
    await adapter.send_text(chat_id, reply.text)


async def handle_reject(chat_id: str) -> None:
    session = store.get_or_create("discord", chat_id)
    if session.pending_preview_path:
        store.log_graphic(session.session_key, session.pending_preview_path, None, "rejected")
    reply = orchestrator.handle_rejection(session)
    store.save(session)


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
    store.save(session)

    if reply.offer_approval and reply.image_path:
        await adapter.send_image_with_approval_buttons(
            chat_id, reply.image_path, "Preview ready. Approve or Reject below."
        )
    elif reply.text:
        await adapter.send_text(chat_id, reply.text)


def main() -> None:
    if not config.DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")
    client.run(config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
