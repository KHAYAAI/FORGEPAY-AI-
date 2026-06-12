"""
Slack adapter — slash commands + Events API.

Inbound:
  POST /channels/slack/commands   slash command (e.g. /vocalmarket buy milk)
  POST /channels/slack/events     Events API (app_mention, message.im, url_verification)
  All requests verified via X-Slack-Signature (v0 HMAC-SHA256, replay-protected).
Outbound:
  chat.postMessage with Block Kit — suggestions become a row of buttons.

Slack requires a response within 3s. We run the (fast) orchestrator turn inline,
then post the result; for slower turns this could be moved to a background task
that replies via response_url, but the bridge is quick enough for the inline path.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from ..bridge import ConversationBridge
from ..config import settings
from ..models import Channel, InboundMessage, OutboundMessage
from ..sessions import store
from .base import verify_slack_signature

logger = logging.getLogger(__name__)


class SlackAdapter:
    channel = Channel.SLACK
    path_prefix = "/channels/slack"

    def __init__(self, bridge: ConversationBridge) -> None:
        self._bridge = bridge
        self._api = httpx.AsyncClient(
            base_url="https://slack.com/api",
            headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            timeout=settings.request_timeout_seconds,
        )

    def _verify(self, body: bytes, ts: str | None, sig: str | None) -> bool:
        return verify_slack_signature(settings.slack_signing_secret, body, ts, sig)

    def router(self) -> APIRouter:
        router = APIRouter(prefix=self.path_prefix, tags=["slack"])

        @router.post("/commands")
        async def commands(
            request: Request,
            ts: str | None = Header(default=None, alias="X-Slack-Request-Timestamp"),
            sig: str | None = Header(default=None, alias="X-Slack-Signature"),
        ) -> Response:
            body = await request.body()
            if not self._verify(body, ts, sig):
                return Response(status_code=401)
            form = await request.form()
            inbound = InboundMessage(
                channel=self.channel,
                channel_user_id=str(form.get("user_id", "")),
                text=str(form.get("text", "")),
                reply_context={"channel_id": str(form.get("channel_id", ""))},
            )
            outbound = await self._bridge.handle(inbound)
            # Respond directly to the slash command (visible to the user).
            return JSONResponse(self._blocks(outbound, response_type="in_channel"))

        @router.post("/events")
        async def events(
            request: Request,
            ts: str | None = Header(default=None, alias="X-Slack-Request-Timestamp"),
            sig: str | None = Header(default=None, alias="X-Slack-Signature"),
        ) -> Response:
            body = await request.body()
            if not self._verify(body, ts, sig):
                return Response(status_code=401)
            payload = json.loads(body)

            if payload.get("type") == "url_verification":
                return PlainTextResponse(payload.get("challenge", ""))

            event = payload.get("event", {})
            # Ignore bot echoes and non-message events.
            if event.get("bot_id") or event.get("type") not in {"app_mention", "message"}:
                return Response(status_code=200)
            if event.get("subtype"):  # edits, joins, etc.
                return Response(status_code=200)

            event_id = payload.get("event_id", "")
            if await store.seen_message(self.channel.value, event_id):
                return Response(status_code=200)

            inbound = InboundMessage(
                channel=self.channel,
                channel_user_id=event.get("user", ""),
                text=self._strip_mention(event.get("text", "")),
                reply_context={"channel_id": event.get("channel", "")},
            )
            outbound = await self._bridge.handle(inbound)
            await self._post(event.get("channel", ""), outbound)
            return Response(status_code=200)

        return router

    @staticmethod
    def _strip_mention(text: str) -> str:
        # Remove a leading <@U123> mention if present.
        if text.startswith("<@"):
            return text.split(">", 1)[-1].strip()
        return text

    def _blocks(self, outbound: OutboundMessage, response_type: str = "ephemeral") -> dict:
        blocks: list[dict] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": outbound.to_plain_text() or "…"}}
        ]
        if outbound.suggestions:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": s.label[:75]},
                            "value": s.payload,
                            "action_id": f"vm_{i}",
                        }
                        for i, s in enumerate(outbound.suggestions[:5])
                    ],
                }
            )
        return {"response_type": response_type, "blocks": blocks}

    async def _post(self, channel_id: str, outbound: OutboundMessage) -> None:
        try:
            await self._api.post(
                "/chat.postMessage", json={"channel": channel_id, **self._blocks(outbound)}
            )
        except httpx.HTTPError as exc:
            logger.error("Slack postMessage failed: %s", exc)

    async def aclose(self) -> None:
        await self._api.aclose()
