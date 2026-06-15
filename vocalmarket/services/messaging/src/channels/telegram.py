"""
Telegram channel adapter.

Inbound:  POST /channels/telegram/webhook   (Telegram Bot API update)
Outbound:
  - Text replies    → sendMessage with inline_keyboard for suggested actions
  - Voice replies   → sendVoice (OGG Opus from ElevenLabs via voice service)
                      when the user sent a voice note (is_voice=True)
  - Payment invoice → sendInvoice when the orchestrator returns a payment_request
  - Pre-checkout    → answerPreCheckoutQuery (must reply within 10 s)
  - Post-payment    → confirmation message + notification to payments service

Voice notes: Telegram delivers them as a file_id. We download via getFile, then
hand the audio to the voice service's /stt endpoint. The transcribed text goes
through the standard orchestrator turn. On reply, if the original message was a
voice note, we synthesise the response via /tts and send it back as sendVoice.
Text always accompanies audio as a caption so the reply is readable without
headphones and in cases where TTS synthesis fails.

Telegram Payments: requires a payment provider token set in BotFather.
The provider token comes from connecting Stripe (or another provider) to the bot
via BotFather → /mybots → Payments. When MESSAGING_TELEGRAM_PAYMENT_PROVIDER_TOKEN
is set and the orchestrator returns a payment_request block, we send a sendInvoice.
The user taps Pay, Telegram handles card collection, we receive pre_checkout_query
(must answer within 10 s), then successful_payment. On success we notify the
payments service so the intelligence pipeline can record the transaction.
"""

from __future__ import annotations

import logging
import time

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
        self._voice = httpx.AsyncClient(
            base_url=settings.voice_service_url,
            timeout=settings.request_timeout_seconds,
        )
        # Separate client for payments service notifications.
        self._payments = httpx.AsyncClient(
            base_url="http://payments:8001",
            timeout=10.0,
        )

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

            # ── Pre-checkout query (payment validation) ──────────────────────
            if pcq := update.get("pre_checkout_query"):
                return await self._handle_pre_checkout(pcq)

            message = update.get("message") or update.get("edited_message")
            callback = update.get("callback_query")

            # ── Successful payment confirmation ──────────────────────────────
            if message and "successful_payment" in message:
                return await self._handle_successful_payment(message)

            # ── Regular message / callback ───────────────────────────────────
            if callback:
                inbound = await self._parse_callback(callback)
            elif message:
                inbound = await self._parse_message(message)
            else:
                return Response(status_code=200)

            if inbound is None:
                return Response(status_code=200)

            if await store.seen_message(self.channel.value, str(inbound.reply_context.get("message_id", ""))):
                return Response(status_code=200)

            outbound = await self._bridge.handle(inbound)
            await self._send(inbound.channel_user_id, outbound, is_voice=inbound.is_voice)
            return Response(status_code=200)

        return router

    # ── Inbound parsing ───────────────────────────────────────────────────────

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
            return InboundMessage(
                channel=self.channel,
                channel_user_id=chat_id,
                text=text or "",
                is_voice=True,
                reply_context={"message_id": message_id},
            )

        return None

    async def _parse_callback(self, callback: dict) -> InboundMessage | None:
        chat_id = str(callback["from"]["id"])
        data = callback.get("data", "")
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

    # ── STT (voice note → text) ───────────────────────────────────────────────

    async def _transcribe(self, file_id: str) -> str:
        """Download a Telegram voice note and run it through the voice service STT."""
        try:
            meta = await self._api.get("/getFile", params={"file_id": file_id})
            meta.raise_for_status()
            file_path = meta.json()["result"]["file_path"]
            audio_resp = await self._api.get(
                f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
            )
            audio_resp.raise_for_status()
            stt_resp = await self._voice.post(
                "/stt",
                files={"audio": ("voice.ogg", audio_resp.content, "audio/ogg")},
            )
            stt_resp.raise_for_status()
            return stt_resp.json().get("text", "")
        except httpx.HTTPError as exc:
            logger.warning("Telegram STT failed: %s", exc)
            return ""

    # ── TTS (text → voice note) ───────────────────────────────────────────────

    async def _synthesise(self, text: str) -> bytes | None:
        """
        Synthesise text via the voice service TTS endpoint.
        Returns OGG Opus bytes, or None if synthesis fails (fall back to text).
        """
        if not text:
            return None
        try:
            resp = await self._voice.post(
                "/tts",
                json={"text": text[:4096]},
                headers={"Accept": "audio/ogg"},
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            logger.warning("TTS synthesis failed, falling back to text reply: %s", exc)
            return None

    # ── Payment handling ──────────────────────────────────────────────────────

    async def _handle_pre_checkout(self, pcq: dict) -> Response:
        """
        Validate a pending Telegram payment before Stripe charges the card.
        Must answer within 10 seconds. We optimistically approve; a production
        system should check stock and order validity here.
        """
        try:
            await self._api.post(
                "/answerPreCheckoutQuery",
                json={"pre_checkout_query_id": pcq["id"], "ok": True},
            )
        except httpx.HTTPError as exc:
            logger.error("answerPreCheckoutQuery failed: %s", exc)
        return Response(status_code=200)

    async def _handle_successful_payment(self, message: dict) -> Response:
        """
        User's payment was charged. Confirm to the user and notify the payments
        service so the Intelligence pipeline can record the transaction.
        """
        sp = message["successful_payment"]
        chat_id = str(message["chat"]["id"])
        charge_id = sp.get("telegram_payment_charge_id", "")
        order_payload = sp.get("invoice_payload", "")
        amount = sp.get("total_amount", 0)
        currency = sp.get("currency", "ZAR")

        # Best-effort: notify the payments service.
        try:
            await self._payments.post(
                "/internal/telegram-payment",
                json={
                    "charge_id": charge_id,
                    "order_payload": order_payload,
                    "amount_cents": amount,
                    "currency": currency,
                    "channel": "telegram",
                    "channel_user_id": chat_id,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("Failed to notify payments service after Telegram payment: %s", exc)

        try:
            await self._api.post(
                "/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": (
                        f"✅ Payment confirmed!\n"
                        f"Amount: {currency} {amount / 100:.2f}\n"
                        f"Reference: {charge_id}\n\n"
                        "Your order is being processed. Type anything to continue shopping."
                    ),
                },
            )
        except httpx.HTTPError as exc:
            logger.error("sendMessage after payment failed: %s", exc)

        return Response(status_code=200)

    # ── Outbound sending ──────────────────────────────────────────────────────

    async def _send(
        self,
        chat_id: str,
        outbound: OutboundMessage,
        *,
        is_voice: bool = False,
    ) -> None:
        """
        Send the outbound message back to the user. Priority:
          1. Payment invoice (sendInvoice) if orchestrator requested one.
          2. Voice note (sendVoice) if the user spoke and TTS succeeds.
          3. Text message (sendMessage) as the universal fallback.
        Suggestions always render as inline_keyboard buttons.
        """
        # Build reply_markup once — shared across all send paths.
        reply_markup: dict | None = None
        if outbound.suggestions:
            reply_markup = {
                "inline_keyboard": [
                    [{"text": s.label, "callback_data": s.payload}]
                    for s in outbound.suggestions
                ]
            }

        # 1. In-chat payment invoice.
        if outbound.payment_request and settings.telegram_payment_provider_token:
            await self._send_invoice(chat_id, outbound, reply_markup)
            return

        plain = outbound.to_plain_text() or "…"

        # 2. Voice reply when the user sent a voice note.
        if is_voice:
            audio = await self._synthesise(outbound.text)
            if audio:
                await self._send_voice(chat_id, audio, plain, reply_markup)
                return
            # TTS failed — fall through to text with a note.
            plain = f"[Voice unavailable]\n{plain}"

        # 3. Text reply (universal fallback).
        await self._send_text(chat_id, plain, reply_markup)

    async def _send_text(
        self, chat_id: str, text: str, reply_markup: dict | None
    ) -> None:
        payload: dict = {"chat_id": chat_id, "text": text[:4096]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            await self._api.post("/sendMessage", json=payload)
        except httpx.HTTPError as exc:
            logger.error("Telegram sendMessage failed for %s: %s", chat_id, exc)

    async def _send_voice(
        self,
        chat_id: str,
        audio: bytes,
        caption: str,
        reply_markup: dict | None,
    ) -> None:
        """Send OGG Opus audio as a Telegram voice note with text caption."""
        data: dict = {"chat_id": chat_id}
        if caption:
            # Telegram caption max is 1024 characters.
            data["caption"] = caption[:1024]
        if reply_markup:
            import json as _json
            data["reply_markup"] = _json.dumps(reply_markup)
        try:
            await self._api.post(
                "/sendVoice",
                data=data,
                files={"voice": ("reply.ogg", audio, "audio/ogg")},
            )
        except httpx.HTTPError as exc:
            logger.error("Telegram sendVoice failed for %s: %s", chat_id, exc)
            # Fall back to text so the user always gets a reply.
            await self._send_text(chat_id, caption, reply_markup)

    async def _send_invoice(
        self,
        chat_id: str,
        outbound: OutboundMessage,
        reply_markup: dict | None,
    ) -> None:
        """Send a Telegram Payments invoice for in-chat checkout."""
        pr = outbound.payment_request
        assert pr is not None  # caller checks
        invoice_payload = pr.order_payload or f"order:{chat_id}:{int(time.time())}"
        body: dict = {
            "chat_id": chat_id,
            "title": pr.title,
            "description": pr.description or outbound.text,
            "payload": invoice_payload,
            "provider_token": settings.telegram_payment_provider_token,
            "currency": pr.currency,
            "prices": [{"label": pr.title, "amount": pr.amount_cents}],
            # Ask for name so we have something for the order record.
            "need_name": True,
            "need_phone_number": False,
            "need_email": False,
            "need_shipping_address": False,
            # Show a "Pay" button instead of the normal inline keyboard.
        }
        try:
            resp = await self._api.post("/sendInvoice", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Telegram sendInvoice failed for %s: %s", chat_id, exc)
            # Fall back: send the price as plain text so the user knows what to pay.
            fallback = (
                f"{outbound.text}\n\n"
                f"To complete your order: {pr.currency} {pr.amount_cents / 100:.2f}\n"
                "Reply 'pay' to receive a payment link."
            )
            await self._send_text(chat_id, fallback, reply_markup)

    async def aclose(self) -> None:
        await self._api.aclose()
        await self._voice.aclose()
        await self._payments.aclose()
