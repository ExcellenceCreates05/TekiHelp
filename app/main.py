"""
Entry point -- Week 2, Day 12-14 milestone: full conversational pipeline
over Telegram, backed by SQLite, with all five fixes active.

Run with:  python -m app.main
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app import config
from app.agent.orchestrator import Orchestrator
from app.ai.router import InferenceRouter
from app.broadcast.watch_folder import deliver_to_watch_folder
from app.channels.telegram_adapter import TelegramAdapter
from app.storage.database import SQLiteSessionStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("tekihelp.main")

router = InferenceRouter()
orchestrator = Orchestrator(router)
store = SQLiteSessionStore()


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    adapter: TelegramAdapter = context.application.bot_data["adapter"]

    if not adapter.is_authorized(chat_id):
        await adapter.send_text(chat_id, "This bot is restricted to authorized control-room operators.")
        return

    text = update.message.text or ""
    session = store.get_or_create("telegram", chat_id)

    reply = orchestrator.handle_message(session, text)
    store.save(session)

    if reply.offer_approval and reply.image_path:
        caption = "Preview ready. Approve to send to the Watch Folder, or Reject to correct it."
        await adapter.send_image_with_approval_buttons(chat_id, reply.image_path, caption)
    elif reply.text:
        await adapter.send_text(chat_id, reply.text)


async def on_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    adapter: TelegramAdapter = context.application.bot_data["adapter"]
    session = store.get_or_create("telegram", chat_id)

    await query.answer()

    if query.data == "approve":
        reply = orchestrator.handle_approval(session)
        # Rule 5: this is the ONLY place in the whole codebase allowed to
        # call deliver_to_watch_folder -- the orchestrator itself never does.
        if session.pending_preview_path:
            final_path = deliver_to_watch_folder(session.pending_preview_path)
            store.log_graphic(session.session_key, session.pending_preview_path, final_path, "approved")
            logger.info("Delivered to Watch Folder: %s", final_path)
        store.save(session)
        await adapter.send_text(chat_id, reply.text)

    elif query.data == "reject":
        if session.pending_preview_path:
            store.log_graphic(session.session_key, session.pending_preview_path, None, "rejected")
        reply = orchestrator.handle_rejection(session)
        store.save(session)
        await adapter.send_text(chat_id, reply.text)


def build_application() -> Application:
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    adapter = TelegramAdapter(application)
    application.bot_data["adapter"] = adapter

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    application.add_handler(CallbackQueryHandler(on_approval_callback))
    return application


def main() -> None:
    app = build_application()
    logger.info("Tekihelp bot starting (Telegram)...")
    app.run_polling()


if __name__ == "__main__":
    main()
