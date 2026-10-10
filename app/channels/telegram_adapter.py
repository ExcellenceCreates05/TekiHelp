"""
Telegram channel adapter -- implements ChannelAdapter.

Week 1 note: this file defines the adapter class used from Week 2 onward
by app/main.py. For the Week 1 single-turn milestone, use
scripts/week1_manual_test.py instead (no Telegram needed yet) --
the bot wiring here is what Week 1 Day 6-7 sets up but Week 2 is what
actually drives it through the full agent loop.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from app import config
from app.channels.base import ChannelAdapter


class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self, application: Application) -> None:
        self._app = application

    def is_authorized(self, chat_id: str) -> bool:
        if not config.TELEGRAM_AUTHORIZED_CHAT_IDS:
            # No allowlist configured: allow everyone (fine for dev, NOT for
            # production -- set TELEGRAM_AUTHORIZED_CHAT_IDS before the beta test).
            return True
        return str(chat_id) in config.TELEGRAM_AUTHORIZED_CHAT_IDS

    async def send_text(self, chat_id: str, text: str) -> None:
        await self._app.bot.send_message(chat_id=chat_id, text=text)

    async def send_image_with_approval_buttons(self, chat_id: str, image_path: str, caption: str) -> None:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve", callback_data="approve"),
                    InlineKeyboardButton("Reject", callback_data="reject"),
                ]
            ]
        )
        with open(image_path, "rb") as f:
            await self._app.bot.send_photo(
                chat_id=chat_id, photo=f, caption=caption, reply_markup=keyboard
            )
