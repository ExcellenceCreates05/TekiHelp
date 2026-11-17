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
from app.models.session import WorkflowStatus
from app.storage.database import (
    SQLiteSessionStore,
    SessionHistoryMismatchError,
    StaleSessionError,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("tekihelp.main")

if config.ALLOW_OPEN_ACCESS:
    logger.warning("ALLOW_OPEN_ACCESS=true: submission allowlists are open for local development")

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
    try:
        store.save(session)
    except (StaleSessionError, SessionHistoryMismatchError):
        await adapter.send_text(
            chat_id,
            "That action is no longer valid, please try again.",
        )
        return

    if reply.offer_approval and reply.image_path:
        caption = "Preview ready. Approve to send to the Watch Folder, or Reject to correct it."
        await adapter.send_image_with_approval_buttons(
            chat_id,
            reply.image_path,
            caption,
            session.pending_preview_id,
        )
    elif reply.text:
        await adapter.send_text(chat_id, reply.text)


async def on_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user_id = str(update.effective_user.id)
    adapter: TelegramAdapter = context.application.bot_data["adapter"]

    if not adapter.is_authorized(chat_id):
        await query.answer("This chat is not authorized.", show_alert=True)
        return
    if not adapter.is_operator_authorized(user_id):
        await query.answer(
            "Operator authorization is not configured or this user is not authorized.",
            show_alert=True,
        )
        return

    if not query.data or ":" not in query.data:
        await query.answer("This preview has expired.", show_alert=True)
        return
    action, preview_id = query.data.split(":", 1)
    if action not in {"approve", "reject"}:
        await query.answer("This preview has expired.", show_alert=True)
        return

    session = store.get_or_create("telegram", chat_id)
    if session.pending_preview_id != preview_id:
        await query.answer("This preview has expired or is stale.", show_alert=True)
        return
    if session.status != WorkflowStatus.AWAITING_APPROVAL:
        await query.answer("This preview has expired.", show_alert=True)
        return
    if not session.pending_preview_path or session.awaiting_final_confirmation:
        await query.answer("This preview is no longer valid.", show_alert=True)
        return

    claim_owner = store.claim_preview(
        session.session_key,
        preview_id,
        action,
        config.DELIVERY_CLAIM_TIMEOUT_S,
    )
    if not claim_owner:
        await query.answer("This preview is no longer valid or is already being handled.", show_alert=True)
        return

    await query.edit_message_reply_markup(reply_markup=None)

    if action == "reject":
        reply = orchestrator.handle_rejection(session)
        if reply.rejected_path:
            store.complete_rejection(
                session.session_key,
                preview_id,
                reply.rejected_path,
                claim_owner,
            )
        await query.answer("Preview rejected.")
        await adapter.send_text(chat_id, reply.text)
        return

    reply = orchestrator.handle_approval(session)
    approved_path = reply.approved_path or session.pending_preview_path
    if not approved_path:
        await query.answer("This preview is no longer valid.", show_alert=True)
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
        await query.answer("Delivery failed; the preview remains available to retry.", show_alert=True)
        await adapter.send_text(
            chat_id,
            f"Delivery failed and is recoverable. Please retry approval. {exc}",
        )
        return

    if not store.complete_delivery(
        session.session_key,
        preview_id,
        approved_path,
        final_path,
        claim_owner,
    ):
        await query.answer("This preview was already handled.", show_alert=True)
        return
    await query.answer("Approved and delivered.")
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
