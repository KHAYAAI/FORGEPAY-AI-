"""
ConversationBridge — the channel-neutral core.

Takes a normalised `InboundMessage` from any adapter, resolves which vertical and
platform user it belongs to, runs one orchestrator turn, and returns a normalised
`OutboundMessage`. Every channel shares this exact path, so a Telegram buyer, a
WhatsApp shopper, and a USSD feature-phone user all hit the same AI pipeline,
memory, and compliance checks.
"""

from __future__ import annotations

import logging

import httpx

from .config import settings
from .models import Channel, InboundMessage, OutboundMessage, ProductLine, Suggestion
from .sessions import SessionStore, store as default_store

logger = logging.getLogger(__name__)

VALID_VERTICALS = {"grocery", "b2b_procurement", "healthcare"}

# Human-friendly aliases users might type to switch context.
VERTICAL_ALIASES = {
    "grocery": "grocery",
    "groceries": "grocery",
    "food": "grocery",
    "shop": "grocery",
    "b2b": "b2b_procurement",
    "procurement": "b2b_procurement",
    "supplier": "b2b_procurement",
    "suppliers": "b2b_procurement",
    "pharmacy": "healthcare",
    "health": "healthcare",
    "healthcare": "healthcare",
    "medicine": "healthcare",
}

HELP_TEXT = (
    "VocalMarket assistant. Just tell me what you need.\n"
    "Switch mode anytime: type 'grocery', 'suppliers', or 'pharmacy'.\n"
    "Type 'help' to see this again."
)


def platform_user_id(channel: Channel, channel_user_id: str) -> str:
    """
    Deterministic platform user id from a channel identity.

    Namespacing by channel keeps a phone number on WhatsApp distinct from the same
    number on SMS, and lets the orchestrator/memory attribute facts correctly.
    """
    return f"{channel.value}:{channel_user_id}"


class ConversationBridge:
    """Routes inbound channel messages through the AI orchestrator."""

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.orchestrator_url,
            timeout=settings.request_timeout_seconds,
        )
        self._store = session_store or default_store

    async def handle(self, inbound: InboundMessage) -> OutboundMessage:
        text = (inbound.text or "").strip()

        # 1. Lightweight intent handling that never needs the LLM.
        lowered = text.lower()
        if lowered in {"help", "/help", "menu", "/start", "start"}:
            return OutboundMessage(text=HELP_TEXT, suggestions=self._vertical_suggestions())

        # 2. Explicit vertical switch (typed alias or adapter-provided vertical).
        chosen = inbound.vertical or VERTICAL_ALIASES.get(lowered)
        if chosen in VALID_VERTICALS:
            await self._store.set_vertical(inbound.channel.value, inbound.channel_user_id, chosen)
            if inbound.vertical is None:
                # The whole message was just a mode switch — acknowledge and wait.
                return OutboundMessage(
                    text=f"Switched to {self._label(chosen)}. What do you need?",
                )

        # 3. Resolve the effective vertical.
        vertical = (
            (inbound.vertical if inbound.vertical in VALID_VERTICALS else None)
            or await self._store.get_vertical(inbound.channel.value, inbound.channel_user_id)
            or settings.default_vertical
        )

        if not text:
            return OutboundMessage(
                text=f"You're in {self._label(vertical)}. Tell me what you need.",
                suggestions=self._vertical_suggestions(),
            )

        # 4. One orchestrator turn — same endpoint the voice service uses.
        return await self._run_turn(inbound, vertical, text)

    async def _run_turn(
        self, inbound: InboundMessage, vertical: str, text: str
    ) -> OutboundMessage:
        user_id = platform_user_id(inbound.channel, inbound.channel_user_id)
        conversation_id = f"{inbound.channel.value}:{inbound.channel_user_id}:{vertical}"
        try:
            resp = await self._http.post(
                "/chat",
                json={
                    "user_id": user_id,
                    "message": text,
                    "vertical": vertical,
                    "conversation_id": conversation_id,
                },
                headers={"X-User-Id": user_id, "X-Vertical": vertical},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Orchestrator call failed for %s: %s", user_id, exc)
            return OutboundMessage(
                text="Sorry — I couldn't reach the assistant just now. Please try again shortly."
            )

        return self._to_outbound(data)

    @staticmethod
    def _to_outbound(data: dict) -> OutboundMessage:
        products = [
            ProductLine(
                name=p.get("name") or p.get("title") or "Item",
                price=p.get("price"),
                currency=p.get("currency", ""),
                in_stock=p.get("in_stock", True),
            )
            for p in (data.get("products") or [])
        ]
        suggestions = []
        for a in data.get("suggested_actions") or []:
            label = a.get("label") or a.get("title") or a.get("type") or "Action"
            payload = a.get("payload") or a.get("action") or a.get("type") or label
            suggestions.append(Suggestion(label=str(label)[:24], payload=str(payload)[:64]))
        return OutboundMessage(
            text=data.get("text", ""),
            products=products,
            suggestions=suggestions,
        )

    @staticmethod
    def _vertical_suggestions() -> list[Suggestion]:
        return [
            Suggestion(label="🛒 Grocery", payload="grocery"),
            Suggestion(label="🏭 Suppliers", payload="b2b_procurement"),
            Suggestion(label="💊 Pharmacy", payload="healthcare"),
        ]

    @staticmethod
    def _label(vertical: str) -> str:
        return {
            "grocery": "Grocery",
            "b2b_procurement": "B2B Procurement",
            "healthcare": "Pharmacy",
        }.get(vertical, vertical)

    async def aclose(self) -> None:
        await self._http.aclose()
