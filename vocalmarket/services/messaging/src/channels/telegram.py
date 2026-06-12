"""
Telegram channel adapter.

Inbound:  POST /channels/telegram/webhook   (Telegram Bot API update)
Outbound: sendMessage with an inline keyboard built from suggested actions.

Voice notes: Telegram delivers them as a file_id. We download via getFile, then
hand the audio to the voice service's STT. If STT isn't reachable we ask the user
to type instead — the text path always works.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Header, Request, Response

from ..bridge import ConversationBridge
from ..config import settings
from ..models import Channel, InboundMessage, OutboundMessage
from ..sessions import store
from .base import verify_telegram_secret

logger = logging.getLogger(__name__)


class TelegramAdapter:
    channel = Channel.TELEGRAM
    path_prefix = "/channels/telegram"

    def __init__(self, bridge: ConversationBridge) -> None:
        self._bridge = bridge
        self._api = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{settings.telegram_bot_token}",
            timeout=settings.request_timeout_seconds,
        )
        # Voice transcription reuses the voice service STT endpoint.
        self._voice = httpx.AsyncClient(timeout=settings.request_timeout_seconds)

    def router(self) -> APIRouter:
        router = APIRouter(prefix=self.path_prefix, tags=["telegram"])

        @router.post("/webhook")
        async def webhook(
            request: Request,
            secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
        ) -> Response:
            if not verify_telegram_secret(settings.telegram_webhook_secret, secret):
                return Response(status_code=401)

            update = await request.json()
            message = update.get("message") or update.get("edited_message")
            callback = update.get("callback_query")

            if callback:
                inbound = await self._parse_callback(callback)
            elif message:
                inbound = await self._parse_message(message)
            else:
                return Response(status_code=200)  # ignore non-message updates

            if inbound is None:
                return Response(status_code=200)

            if await store.seen_message(self.channel.value, str(inbound.reply_context.get("message_id", ""))):
                return Response(status_code=200)

            outbound = await self._bridge.handle(inbound)
            await self._send(inbound.channel_user_id, outbound)
            return Response(status_code=200)

        return router

    async def _parse_message(self, message: dict) -> InboundMessage | None:
        chat_id = str(message["chat"]["id"])
        message_id = message.get("message_id")

        if "text" in message:
            return InboundMessage(
                channel=self.channel,
                channel_user_id=chat_id,
                text=message["text"],
                reply_context={"message_id": message_id},
            )

        if "voice" in message:
            text = await self._transcribe(message["voice"]["file_id"])
            if not text:
                return InboundMessage(
                    channel=self.channel,
                    channel_user_id=chat_id,
                    text="",
                    reply_context={"message_id": message_id},
                )
            return InboundMessage(
                channel=self.channel,
                channel_user_id=chat_id,
                text=text,
                is_voice=True,
                reply_context={"message_id": message_id},
            )
        return None

    async def _parse_callback(self, callback: dict) -> InboundMessage | None:
        chat_id = str(callback["from"]["id"])
        data = callback.get("data", "")
        # Answer the callback so Telegram stops the loading spinner.
        try:
            await self._api.post("/answerCallbackQuery", json={"callback_query_id": callback["id"]})
        except httpx.HTTPError:
            pass
        return InboundMessage(
            channel=self.channel,
            channel_user_id=chat_id,
            text=data,
            reply_context={"message_id": callback.get("id")},
        )

    async def _transcribe(self, file_id: str) -> str:
        """Download the voice note and run it through the voice service STT."""
        try:
            meta = await self._api.get("/getFile", params={"file_id": file_id})
            meta.raise_for_status()
            file_path = meta.json()["result"]["file_path"]
            audio = await self._voice.get(
                f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
            )
            audio.raise_for_status()
            stt = await self._voice.post(
                f"{settings.orchestrator_url.replace('ai-orchestrator:8002', 'voice:8003')}/stt",
                files={"audio": ("voice.ogg", audio.content, "audio/ogg")},
            )
            stt.raise_for_status()
            return stt.json().get("text", "")
        except httpx.HTTPError as exc:
            logger.warning("Telegram voice transcription failed: %s", exc)
            return ""

    async def _send(self, chat_id: str, outbound: OutboundMessage) -> None:
        payload: dict = {"chat_id": chat_id, "text": outbound.to_plain_text() or "…"}
        if outbound.suggestions:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": s.label, "callback_data": s.payload}] for s in outbound.suggestions
                ]
            }
        try:
            await self._api.post("/sendMessage", json=payload)
        except httpx.HTTPError as exc:
            logger.error("Telegram sendMessage failed: %s", exc)

    async def aclose(self) -> None:
        await self._api.aclose()
        await self._voice.aclose()
