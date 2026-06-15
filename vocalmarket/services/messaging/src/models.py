"""
Channel-neutral message models.

Every inbound channel adapter normalises its platform-specific payload into an
`InboundMessage`. The `ConversationBridge` turns that into an `OutboundMessage`,
which each adapter then renders back into its own native format (Telegram inline
keyboards, WhatsApp interactive buttons, Slack blocks, USSD CON/END strings…).

Keeping a single neutral shape in the middle means the AI pipeline never needs to
know which channel a user is on — the same orchestrator turn serves them all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Channel(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    SLACK = "slack"
    TEAMS = "teams"
    USSD = "ussd"


@dataclass
class InboundMessage:
    """A user message arriving from any channel, normalised."""

    channel: Channel
    channel_user_id: str          # chat_id / phone / slack user id / AAD object id
    text: str                     # transcribed/typed user text (may be "")
    # Optional explicit vertical (slash command, USSD menu choice). When None the
    # bridge falls back to the user's session default, then the global default.
    vertical: str | None = None
    # Channel-specific routing data the adapter needs to send a reply back.
    reply_context: dict = field(default_factory=dict)
    # True for voice notes that were transcribed before reaching the bridge.
    is_voice: bool = False


@dataclass
class Suggestion:
    """A suggested next action, rendered as a button where the channel supports it."""

    label: str
    # A short stable payload the channel sends back when the button is tapped.
    payload: str


@dataclass
class ProductLine:
    """A single product result, rendered as a text line on plain-text channels."""

    name: str
    price: float | None = None
    currency: str = ""
    in_stock: bool = True

    def to_text(self) -> str:
        price = ""
        if self.price is not None:
            price = f" — {self.currency}{self.price:,.2f}".rstrip()
        stock = "" if self.in_stock else " (out of stock)"
        return f"• {self.name}{price}{stock}"


@dataclass
class PaymentRequest:
    """
    A payment invoice the channel should present to the user for in-chat checkout.

    `amount_cents` is in the smallest unit of `currency` (e.g. South African cents
    for ZAR). `order_payload` is an opaque string passed back to the bot in the
    successful_payment event and forwarded to the payments service.
    """

    title: str
    description: str
    amount_cents: int
    currency: str = "ZAR"
    order_payload: str = ""


@dataclass
class OutboundMessage:
    """The reply to send back to the user on their originating channel."""

    text: str
    suggestions: list[Suggestion] = field(default_factory=list)
    products: list[ProductLine] = field(default_factory=list)
    # Set by the bridge when the orchestrator requests an in-chat payment.
    payment_request: PaymentRequest | None = None

    def to_plain_text(self, max_len: int | None = None) -> str:
        """
        Flatten everything into a single plain-text body for channels without
        rich formatting (SMS, USSD). Truncates to `max_len` GSM characters.
        """
        parts = [self.text] if self.text else []
        if self.products:
            parts.append("\n".join(p.to_text() for p in self.products))
        if self.suggestions:
            opts = "  ".join(f"[{s.label}]" for s in self.suggestions)
            parts.append(opts)
        body = "\n".join(parts).strip()
        if max_len is not None and len(body) > max_len:
            body = body[: max_len - 1].rstrip() + "…"
        return body
