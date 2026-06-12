"""
SMS adapter — Twilio.

Inbound:  POST /channels/sms/webhook   (application/x-www-form-urlencoded)
          Verified via X-Twilio-Signature (HMAC-SHA1 over URL + sorted params).
Outbound: TwiML <Response><Message>…</Message></Response> returned synchronously.

SMS is text-only and length-constrained, so the reply is flattened and truncated
to `sms_max_chars`. No voice, no buttons — suggestions are appended as bracketed
hints the user can text back.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import PlainTextResponse

from ..bridge import ConversationBridge
from ..config import settings
from ..models import Channel, InboundMessage, OutboundMessage
from .base import verify_twilio_signature


def _twiml(body: str) -> str:
    safe = (
        body.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'


class SMSAdapter:
    channel = Channel.SMS
    path_prefix = "/channels/sms"

    def __init__(self, bridge: ConversationBridge) -> None:
        self._bridge = bridge

    def router(self) -> APIRouter:
        router = APIRouter(prefix=self.path_prefix, tags=["sms"])

        @router.post("/webhook")
        async def webhook(
            request: Request,
            signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
        ) -> Response:
            form = await request.form()
            params = {k: str(v) for k, v in form.items()}

            # Twilio signs the exact public URL it POSTed to.
            url = settings.public_base_url.rstrip("/") + self.path_prefix + "/webhook"
            if not verify_twilio_signature(settings.twilio_auth_token, url, params, signature):
                return Response(status_code=401)

            inbound = InboundMessage(
                channel=self.channel,
                channel_user_id=params.get("From", ""),
                text=params.get("Body", ""),
                reply_context={"message_id": params.get("MessageSid", "")},
            )
            outbound: OutboundMessage = await self._bridge.handle(inbound)
            body = outbound.to_plain_text(max_len=settings.sms_max_chars)
            return PlainTextResponse(_twiml(body), media_type="application/xml")

        return router

    async def aclose(self) -> None:  # symmetry with other adapters
        return None
