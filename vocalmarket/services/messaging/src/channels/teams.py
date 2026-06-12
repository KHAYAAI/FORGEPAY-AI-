"""
Microsoft Teams adapter — Bot Framework webhook receiver.

Inbound:  POST /channels/teams/messages   (a Bot Framework Activity)
Outbound: a reply Activity POSTed to
          {serviceUrl}/v3/conversations/{conversationId}/activities/{activityId}
          authenticated with an AAD app token (client-credentials flow, cached).

Security note: the Bot Framework signs inbound requests with a JWT in the
Authorization header that should be validated against the Bot Framework OpenID
metadata + JWKS. Implementing full JWKS validation is out of scope here; instead we
gate the endpoint with a shared secret (MESSAGING_TEAMS_INBOUND_SECRET) for the
launch, and leave a clear hook (`_verify`) to drop in JWT validation for production.
"""

from __future__ import annotations

import hmac
import logging
import time

import httpx
from fastapi import APIRouter, Header, Request, Response

from ..bridge import ConversationBridge
from ..config import settings
from ..models import Channel, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class TeamsAdapter:
    channel = Channel.TEAMS
    path_prefix = "/channels/teams"

    def __init__(self, bridge: ConversationBridge) -> None:
        self._bridge = bridge
        self._http = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
        self._token: str = ""
        self._token_expiry: float = 0.0

    def _verify(self, authorization: str | None) -> bool:
        """
        Shared-secret gate. Production should additionally validate the Bot
        Framework JWT (issuer https://api.botframework.com, audience = app id).
        """
        if not settings.teams_inbound_secret:
            return True  # dev / not yet configured
        if not authorization:
            return False
        expected = f"Bearer {settings.teams_inbound_secret}"
        return hmac.compare_digest(expected, authorization)

    def router(self) -> APIRouter:
        router = APIRouter(prefix=self.path_prefix, tags=["teams"])

        @router.post("/messages")
        async def messages(
            request: Request,
            authorization: str | None = Header(default=None),
        ) -> Response:
            if not self._verify(authorization):
                return Response(status_code=401)

            activity = await request.json()
            if activity.get("type") != "message":
                return Response(status_code=200)  # ignore typing/conversationUpdate

            inbound = InboundMessage(
                channel=self.channel,
                channel_user_id=str(activity.get("from", {}).get("id", "")),
                text=(activity.get("text") or "").strip(),
                reply_context={
                    "service_url": activity.get("serviceUrl", ""),
                    "conversation_id": activity.get("conversation", {}).get("id", ""),
                    "activity_id": activity.get("id", ""),
                    "recipient": activity.get("recipient", {}),
                    "from": activity.get("from", {}),
                },
            )
            outbound = await self._bridge.handle(inbound)
            await self._reply(inbound.reply_context, outbound)
            return Response(status_code=200)

        return router

    async def _aad_token(self) -> str:
        """Client-credentials token for the Bot Framework, cached until expiry."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        if not (settings.teams_app_id and settings.teams_app_password):
            return ""
        resp = await self._http.post(
            "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.teams_app_id,
                "client_secret": settings.teams_app_password,
                "scope": "https://api.botframework.com/.default",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._token

    async def _reply(self, ctx: dict, outbound: OutboundMessage) -> None:
        service_url = ctx.get("service_url", "").rstrip("/")
        conversation_id = ctx.get("conversation_id", "")
        if not service_url or not conversation_id:
            return

        reply = {
            "type": "message",
            "from": ctx.get("recipient", {}),
            "recipient": ctx.get("from", {}),
            "text": outbound.to_plain_text(),
        }
        if outbound.suggestions:
            reply["suggestedActions"] = {
                "actions": [
                    {"type": "imBack", "title": s.label, "value": s.payload}
                    for s in outbound.suggestions
                ]
            }

        url = f"{service_url}/v3/conversations/{conversation_id}/activities/{ctx.get('activity_id', '')}"
        try:
            token = await self._aad_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            await self._http.post(url, json=reply, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Teams reply failed: %s", exc)

    async def aclose(self) -> None:
        await self._http.aclose()
