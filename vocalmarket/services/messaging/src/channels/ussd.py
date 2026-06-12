"""
USSD adapter — Africa's Talking gateway (feature-phone access, no smartphone/data).

This is the most important channel for reach in South Africa and across the
continent: it works on any GSM handset with zero data, zero app install.

Inbound:  POST /channels/ussd   (application/x-www-form-urlencoded)
          Fields: sessionId, serviceCode, phoneNumber, text
Outbound: plain text, prefixed with:
          "CON " → keep the session open (expect more input)
          "END " → terminate the session

Protocol detail: the gateway sends the FULL accumulated input every request, with
each user entry joined by '*'. So "1*buy 2 litres of milk" means the user picked
menu option 1 (Grocery) then typed a free-text request. We treat the newest segment
as the latest message, which gives genuine multi-turn conversations over USSD —
each reply stays under one 160-char USSD page.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ..bridge import ConversationBridge
from ..config import settings
from ..models import Channel, InboundMessage

MENU = {
    "1": "grocery",
    "2": "healthcare",
    "3": "b2b_procurement",
}

MAIN_MENU = (
    "CON VocalMarket\n"
    "1. Grocery\n"
    "2. Pharmacy\n"
    "3. Suppliers"
)


class USSDAdapter:
    channel = Channel.USSD
    path_prefix = "/channels/ussd"

    def __init__(self, bridge: ConversationBridge) -> None:
        self._bridge = bridge

    def router(self) -> APIRouter:
        router = APIRouter(prefix=self.path_prefix, tags=["ussd"])

        @router.post("")
        async def ussd(request: Request) -> PlainTextResponse:
            form = await request.form()
            phone = str(form.get("phoneNumber", ""))
            raw = str(form.get("text", "")).strip()
            return PlainTextResponse(await self._handle(phone, raw))

        return router

    async def _handle(self, phone: str, raw: str) -> str:
        parts = [p for p in raw.split("*")] if raw else []

        # Level 0 — no input yet: show the vertical menu.
        if not parts:
            return MAIN_MENU

        # Level 1 — first entry must be a valid vertical choice.
        vertical = MENU.get(parts[0])
        if vertical is None:
            return MAIN_MENU  # re-prompt on invalid selection

        # Explicit exit.
        if parts[-1] in {"00", "0"} and len(parts) > 1:
            return "END Thanks for using VocalMarket."

        # Level 2 — vertical chosen but no request typed yet.
        free_text = [p for p in parts[1:] if p not in {"0", "00"}]
        if not free_text:
            label = {"grocery": "Grocery", "healthcare": "Pharmacy", "b2b_procurement": "Suppliers"}[vertical]
            return f"CON {label}: type what you need"

        # Newest entry is the user's latest message.
        message = free_text[-1]
        inbound = InboundMessage(
            channel=self.channel,
            channel_user_id=phone,
            text=message,
            vertical=vertical,
        )
        outbound = await self._bridge.handle(inbound)
        answer = outbound.to_plain_text(max_len=settings.ussd_max_chars - 40)

        # Keep the session open for another turn; offer an explicit exit.
        return f"CON {answer}\n\n0. Ask again  00. Exit"

    async def aclose(self) -> None:  # symmetry
        return None
