"""
Telegram adapter — TTS voice reply and Payments in-chat checkout.

Tests exercise the core send/payment/pre-checkout methods directly (not the full
webhook route) so there is no dependency on deduplication state, session stores,
or starlette routing. All HTTP calls are intercepted by httpx.MockTransport.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from vocalmarket.services.messaging.src.bridge import ConversationBridge
from vocalmarket.services.messaging.src.channels.telegram import TelegramAdapter
from vocalmarket.services.messaging.src.models import (
    OutboundMessage,
    PaymentRequest,
    Suggestion,
)
from vocalmarket.services.messaging.src.sessions import SessionStore

FAKE_OGG = b"OggS\x00" + b"\x00" * 32  # minimal OGG-like bytes for TTS stub


# ── Adapter factory ───────────────────────────────────────────────────────────

def _adapter(
    api_handler=None,
    voice_handler=None,
    payments_handler=None,
) -> TelegramAdapter:
    """Build an adapter with all HTTP clients replaced by MockTransport."""
    bridge = MagicMock(spec=ConversationBridge)
    bridge.handle = AsyncMock(return_value=OutboundMessage(text="ok"))
    adapter = TelegramAdapter(bridge)
    adapter._api = httpx.AsyncClient(
        transport=httpx.MockTransport(api_handler or (lambda r: httpx.Response(200, json={"ok": True}))),
        base_url="https://api.telegram.org/bot_test",
    )
    adapter._voice = httpx.AsyncClient(
        transport=httpx.MockTransport(voice_handler or (lambda r: httpx.Response(200, json={}))),
        base_url="http://voice:8003",
    )
    adapter._payments = httpx.AsyncClient(
        transport=httpx.MockTransport(payments_handler or (lambda r: httpx.Response(200, json={}))),
        base_url="http://payments:8001",
    )
    return adapter


# ── TTS synthesis ─────────────────────────────────────────────────────────────

async def test_synthesise_returns_audio_bytes_on_success():
    """_synthesise calls /tts and returns bytes when the voice service responds."""
    def voice_handler(request: httpx.Request) -> httpx.Response:
        assert "/tts" in str(request.url)
        return httpx.Response(200, content=FAKE_OGG, headers={"content-type": "audio/ogg"})

    adapter = _adapter(voice_handler=voice_handler)
    result = await adapter._synthesise("Hello, here are your results")
    assert result == FAKE_OGG


async def test_synthesise_returns_none_on_voice_service_error():
    """_synthesise returns None (graceful fallback) when voice service is down."""
    def voice_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unavailable"})

    adapter = _adapter(voice_handler=voice_handler)
    result = await adapter._synthesise("Hello")
    assert result is None


async def test_synthesise_returns_none_for_empty_text():
    adapter = _adapter()
    result = await adapter._synthesise("")
    assert result is None


# ── _send: voice-note reply path ──────────────────────────────────────────────

async def test_send_with_is_voice_uses_sendvoice_when_tts_succeeds():
    """is_voice=True + successful TTS → sendVoice (not sendMessage)."""
    called: list[str] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    def voice_handler(request: httpx.Request) -> httpx.Response:
        if "/tts" in str(request.url):
            return httpx.Response(200, content=FAKE_OGG, headers={"content-type": "audio/ogg"})
        return httpx.Response(200, json={})

    adapter = _adapter(api_handler=api_handler, voice_handler=voice_handler)
    outbound = OutboundMessage(
        text="Milk 2L is R32.99",
        suggestions=[Suggestion(label="Add to cart", payload="add:milk")],
    )
    await adapter._send("12345", outbound, is_voice=True)

    assert any("/sendVoice" in p for p in called), f"Expected sendVoice. Got: {called}"
    assert not any("/sendMessage" in p for p in called)


async def test_send_with_is_voice_falls_back_to_sendmessage_when_tts_fails():
    """is_voice=True but TTS fails → sendMessage so user always gets a reply."""
    called: list[str] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    def voice_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "TTS down"})

    adapter = _adapter(api_handler=api_handler, voice_handler=voice_handler)
    outbound = OutboundMessage(text="Bread is R18.50")
    await adapter._send("12345", outbound, is_voice=True)

    assert any("/sendMessage" in p for p in called), f"Expected sendMessage fallback. Got: {called}"
    assert not any("/sendVoice" in p for p in called)


async def test_send_without_is_voice_never_calls_tts():
    """Text-in messages must never hit the TTS endpoint."""
    voice_called: list[str] = []
    api_called: list[str] = []

    def voice_handler(request: httpx.Request) -> httpx.Response:
        voice_called.append(str(request.url))
        return httpx.Response(200, content=FAKE_OGG)

    def api_handler(request: httpx.Request) -> httpx.Response:
        api_called.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    adapter = _adapter(api_handler=api_handler, voice_handler=voice_handler)
    outbound = OutboundMessage(text="Here are your results")
    await adapter._send("12345", outbound, is_voice=False)

    assert not any("/tts" in p for p in voice_called), "TTS must not be called for text messages"
    assert any("/sendMessage" in p for p in api_called)


async def test_sendvoice_includes_caption_and_inline_keyboard():
    """sendVoice payload must carry the text as caption and buttons as reply_markup."""
    captured: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if "/sendVoice" in request.url.path:
            # multipart — capture the form fields
            captured.append({"path": request.url.path, "content": request.content.decode(errors="replace")})
        return httpx.Response(200, json={"ok": True})

    def voice_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FAKE_OGG, headers={"content-type": "audio/ogg"})

    adapter = _adapter(api_handler=api_handler, voice_handler=voice_handler)
    outbound = OutboundMessage(
        text="Milk 2L is R32.99",
        suggestions=[Suggestion(label="Add to cart", payload="add:milk")],
    )
    await adapter._send("12345", outbound, is_voice=True)

    assert len(captured) == 1
    body = captured[0]["content"]
    assert "R32.99" in body           # caption present
    assert "Add to cart" in body      # suggestion button label present


# ── _send: payment invoice path ───────────────────────────────────────────────

async def test_send_sends_invoice_when_payment_request_and_provider_token_set(monkeypatch):
    """OutboundMessage with payment_request → sendInvoice when provider token configured."""
    called: list[str] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    adapter = _adapter(api_handler=api_handler)

    import vocalmarket.services.messaging.src.channels.telegram as tg_module
    monkeypatch.setattr(tg_module.settings, "telegram_payment_provider_token", "stripe_test_xyz")

    outbound = OutboundMessage(
        text="Your total is R287.45",
        payment_request=PaymentRequest(
            title="Grocery Order",
            description="Milk × 1, Bread × 2",
            amount_cents=28745,
            currency="ZAR",
            order_payload="order:conv-1:001",
        ),
    )
    await adapter._send("12345", outbound)

    assert any("/sendInvoice" in p for p in called), f"Expected sendInvoice. Got: {called}"
    assert not any("/sendMessage" in p for p in called)
    assert not any("/sendVoice" in p for p in called)


async def test_send_uses_sendmessage_when_payment_provider_token_not_set(monkeypatch):
    """Without a provider token, fall back to plain text so user can still see the price."""
    called: list[str] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    adapter = _adapter(api_handler=api_handler)

    import vocalmarket.services.messaging.src.channels.telegram as tg_module
    monkeypatch.setattr(tg_module.settings, "telegram_payment_provider_token", "")

    outbound = OutboundMessage(
        text="Your total is R287.45",
        payment_request=PaymentRequest(
            title="Grocery Order",
            description="Items",
            amount_cents=28745,
            currency="ZAR",
        ),
    )
    await adapter._send("12345", outbound)

    assert any("/sendMessage" in p for p in called), f"Expected sendMessage fallback. Got: {called}"
    assert not any("/sendInvoice" in p for p in called)


async def test_invoice_payload_contains_correct_fields(monkeypatch):
    """The sendInvoice body must carry title, amount_cents, currency, and provider_token."""
    invoice_body: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if "/sendInvoice" in request.url.path:
            invoice_body.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    adapter = _adapter(api_handler=api_handler)

    import vocalmarket.services.messaging.src.channels.telegram as tg_module
    monkeypatch.setattr(tg_module.settings, "telegram_payment_provider_token", "stripe_test_xyz")

    outbound = OutboundMessage(
        text="Confirm order",
        payment_request=PaymentRequest(
            title="Grocery Order",
            description="Milk 2L × 1",
            amount_cents=3299,
            currency="ZAR",
            order_payload="order:abc:1",
        ),
    )
    await adapter._send("99999", outbound)

    assert len(invoice_body) == 1
    body = invoice_body[0]
    assert body["title"] == "Grocery Order"
    assert body["currency"] == "ZAR"
    assert body["prices"] == [{"label": "Grocery Order", "amount": 3299}]
    assert body["provider_token"] == "stripe_test_xyz"
    assert body["payload"] == "order:abc:1"


# ── Pre-checkout query ────────────────────────────────────────────────────────

async def test_pre_checkout_query_answered_ok():
    """Bot must answer pre_checkout_query with ok=True within 10 s."""
    answered: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if "/answerPreCheckoutQuery" in request.url.path:
            answered.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    adapter = _adapter(api_handler=api_handler)
    await adapter._handle_pre_checkout({"id": "pcq_abc123"})

    assert len(answered) == 1
    assert answered[0]["pre_checkout_query_id"] == "pcq_abc123"
    assert answered[0]["ok"] is True


async def test_pre_checkout_query_survives_api_error():
    """If Telegram API is temporarily down, pre-checkout should not raise."""
    def api_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"ok": False})

    adapter = _adapter(api_handler=api_handler)
    # Must not raise — Telegram will timeout and retry.
    await adapter._handle_pre_checkout({"id": "pcq_xyz"})


# ── Successful payment ────────────────────────────────────────────────────────

async def test_successful_payment_notifies_payments_service():
    """On payment completion, the Intelligence pipeline must be notified."""
    payments_received: list[dict] = []

    def payments_handler(request: httpx.Request) -> httpx.Response:
        payments_received.append(json.loads(request.content))
        return httpx.Response(200, json={"recorded": True})

    adapter = _adapter(payments_handler=payments_handler)
    message = {
        "chat": {"id": 12345},
        "message_id": 99,
        "successful_payment": {
            "currency": "ZAR",
            "total_amount": 28745,
            "invoice_payload": "order:conv-1:001",
            "telegram_payment_charge_id": "charge_tg_abc",
            "provider_payment_charge_id": "ch_stripe_xyz",
        },
    }
    await adapter._handle_successful_payment(message)

    assert len(payments_received) == 1
    p = payments_received[0]
    assert p["charge_id"] == "charge_tg_abc"
    assert p["amount_cents"] == 28745
    assert p["currency"] == "ZAR"
    assert p["order_payload"] == "order:conv-1:001"
    assert p["channel"] == "telegram"
    assert p["channel_user_id"] == "12345"


async def test_successful_payment_sends_confirmation_to_user():
    """After payment, user receives a confirmation message with the charge reference."""
    messages_sent: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if "/sendMessage" in request.url.path:
            messages_sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    adapter = _adapter(api_handler=api_handler)
    message = {
        "chat": {"id": 12345},
        "message_id": 99,
        "successful_payment": {
            "currency": "ZAR",
            "total_amount": 28745,
            "invoice_payload": "order:conv-1:001",
            "telegram_payment_charge_id": "charge_tg_abc",
            "provider_payment_charge_id": "ch_stripe_xyz",
        },
    }
    await adapter._handle_successful_payment(message)

    assert len(messages_sent) == 1
    text = messages_sent[0]["text"]
    assert "charge_tg_abc" in text
    assert "287.45" in text   # amount formatted as currency
    assert "12345" == str(messages_sent[0]["chat_id"])


async def test_successful_payment_still_confirms_user_when_payments_service_down():
    """Even if the payments service is unreachable, the user must receive a confirmation."""
    messages_sent: list[dict] = []

    def api_handler(request: httpx.Request) -> httpx.Response:
        if "/sendMessage" in request.url.path:
            messages_sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    def payments_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    adapter = _adapter(api_handler=api_handler, payments_handler=payments_handler)
    message = {
        "chat": {"id": 12345},
        "message_id": 99,
        "successful_payment": {
            "currency": "ZAR",
            "total_amount": 10000,
            "invoice_payload": "order:xyz",
            "telegram_payment_charge_id": "charge_123",
            "provider_payment_charge_id": "ch_abc",
        },
    }
    await adapter._handle_successful_payment(message)

    # User confirmation was sent despite payments service being down.
    assert len(messages_sent) == 1
    assert "charge_123" in messages_sent[0]["text"]
