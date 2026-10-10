"""
WhatsApp Cloud API adapter (Week 4, Day 22-23) -- ONLY build/wire this in
if your Meta Business verification (started Week 1, Day 1) has cleared.
If it hasn't, skip this file entirely with no schedule impact -- see the
build plan's channel decision point.

Implements the same ChannelAdapter interface as Telegram/Discord. Uses
the WhatsApp Cloud API's REST endpoints directly (no heavy SDK needed
for this scope) via `requests`.

Requires in .env:
    WHATSAPP_ACCESS_TOKEN=
    WHATSAPP_PHONE_NUMBER_ID=
    WHATSAPP_VERIFY_TOKEN=        (for the webhook verification handshake)

This file assumes a webhook receiver (e.g. a small FastAPI/Flask app,
not included here to keep Week 4 scope honest) forwards incoming
messages into orchestrator.handle_message the same way app/main.py does
for Telegram. Wire that receiver only once verification has cleared.
"""
from __future__ import annotations

import os

import requests

from app.channels.base import ChannelAdapter

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppAdapter(ChannelAdapter):
    name = "whatsapp"

    def __init__(self) -> None:
        self._token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
        self._phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        if not self._token or not self._phone_number_id:
            raise RuntimeError(
                "WhatsApp adapter requires WHATSAPP_ACCESS_TOKEN and "
                "WHATSAPP_PHONE_NUMBER_ID -- only configure these once "
                "Meta Business verification has cleared."
            )

    def is_authorized(self, chat_id: str) -> bool:
        allowlist = os.environ.get("WHATSAPP_AUTHORIZED_NUMBERS", "")
        allowed = {n.strip() for n in allowlist.split(",") if n.strip()}
        return not allowed or chat_id in allowed

    def _post(self, payload: dict) -> None:
        url = f"{GRAPH_API_BASE}/{self._phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()

    async def send_text(self, chat_id: str, text: str) -> None:
        self._post({
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": "text",
            "text": {"body": text},
        })

    async def send_image_with_approval_buttons(self, chat_id: str, image_path: str, caption: str) -> None:
        # WhatsApp Cloud API requires media to be uploaded first to get a
        # media ID, then referenced in an interactive message with reply
        # buttons (WhatsApp limits interactive button labels to 20 chars).
        upload_url = f"{GRAPH_API_BASE}/{self._phone_number_id}/media"
        headers = {"Authorization": f"Bearer {self._token}"}
        with open(image_path, "rb") as f:
            files = {"file": ("preview.png", f, "image/png")}
            data = {"messaging_product": "whatsapp", "type": "image/png"}
            resp = requests.post(upload_url, headers=headers, files=files, data=data, timeout=30)
            resp.raise_for_status()
            media_id = resp.json()["id"]

        self._post({
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {"type": "image", "image": {"id": media_id}},
                "body": {"text": caption},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "approve", "title": "Approve"}},
                        {"type": "reply", "reply": {"id": "reject", "title": "Reject"}},
                    ]
                },
            },
        })
