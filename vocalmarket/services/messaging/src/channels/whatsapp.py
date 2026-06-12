"""
WhatsApp Business adapter — Meta Cloud API (Graph API).

Inbound:
  GET  /channels/whatsapp/webhook   verification challenge (hub.challenge)
  POST /channels/whatsapp/webhook   message notifications, verified via
                                    X-Hub-Signature-256 (HMAC-SHA256 of raw body)
Outbound:
  POST graph.facebook.com/<version>/<phone_number_id>/messages
  Replies use interactive reply buttons when suggestions exist (max 3, per Meta).

This targets Meta's Cloud API directly. The same `OutboundMessage` could be sent
via Twilio's WhatsApp endpoint instead by swapping `_send` — the bridge is identical.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import PlainTextResponse

from ..bridge import ConversationBridge
from ..config import settings
from ..models import Channel, InboundMessage, OutboundMessage
from ..sessions import store
from .base import verify_meta_signature

logger = logging.getLogger(__name__)


class WhatsAppAdapter:
    channel = Channel.WHATSAPP
    path_prefix = "/channels/whatsapp"

    def __init__(self, bridge: ConversationBridge) -> None:
        self._bridge = bridge
        self._api = httpx.AsyncClient(
            base_url=f"https://graph.facebook.com/{settings.whatsapp_graph_version}",
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            timeout=settings.request_timeout_seconds,
        )

    def router(self) -> APIRouter:
        router = APIRouter(prefix=self.path_prefix, tags=["whatsapp"])

        @router.get("/webhook")
        async def verify(request: Request) -> Response:
            params = request.query_params
            if (
                params.get("hub.mode") == "subscribe"
                and params.get("hub.verify_token") == settings.whatsapp_verify_token
            ):
                return PlainTextResponse(params.get("hub.challenge", ""))
            return Response(status_code=403)

        @router.post("/webhook")
        async def webhook(
            request: Request,
            signature: str | None = Header(default=None, alias="X-Hub-Signature-256"),
        ) -> Response:
            body = await request.body()
            if not verify_meta_signature(settings.whatsapp_app_secret, body, signature):
                return Response(status_code=401)

            payload = await request.json()
            for inbound in self._parse(payload):
                if await store.seen_message(
                    self.channel.value, str(inbound.reply_context.get("message_id", ""))
                ):
                    continue
                outbound = await self._bridge.handle(inbound)
                await self._send(inbound.channel_user_id, outbound)
            return Response(status_code=200)

        return router

    def _parse(self, payload: dict) -> list[InboundMessage]:
        """Meta batches messages under entry[].changes[].value.messages[]."""
        out: list[InboundMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    wa_id = msg.get("from")
                    message_id = msg.get("id")
                    text = self._extract_text(msg)
                    if wa_id is None:
                        continue
                    out.append(
                        InboundMessage(
                            channel=self.channel,
                            channel_user_id=wa_id,
                            text=text,
                            reply_context={"message_id": message_id},
                        )
                    )
        return out

    @staticmethod
    def _extract_text(msg: dict) -> str:
        msg_type = msg.get("type")
        if msg_type == "text":
            return msg.get("text", {}).get("body", "")
        if msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if "button_reply" in interactive:
                return interactive["button_reply"].get("id", "")
            if "list_reply" in interactive:
                return interactive["list_reply"].get("id", "")
        if msg_type == "button":
            return msg.get("button", {}).get("payload", "")
        # Voice/audio/image are acknowledged but not transcribed here (Cloud API
        # media requires a separate media download + STT step — future work).
        return ""

    async def _send(self, to: str, outbound: OutboundMessage) -> None:
        endpoint = f"/{settings.whatsapp_phone_number_id}/messages"
        body = outbound.to_plain_text()

        if outbound.suggestions:
            buttons = [
                {"type": "reply", "reply": {"id": s.payload, "title": s.label[:20]}}
                for s in outbound.suggestions[:3]  # Meta allows max 3 reply buttons
            ]
            message = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body[:1024] or "…"},
                    "action": {"buttons": buttons},
                },
            }
        else:
            message = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body[:4096] or "…"},
            }

        try:
            await self._api.post(endpoint, json=message)
        except httpx.HTTPError as exc:
            logger.error("WhatsApp send failed: %s", exc)

    async def aclose(self) -> None:
        await self._api.aclose()
