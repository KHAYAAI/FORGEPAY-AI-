"""Bridge routing: vertical switching, help, and the orchestrator turn mapping."""

import httpx
import pytest

from vocalmarket.services.messaging.src.bridge import ConversationBridge, platform_user_id
from vocalmarket.services.messaging.src.models import Channel, InboundMessage
from vocalmarket.services.messaging.src.sessions import SessionStore


def _bridge(handler) -> ConversationBridge:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://orchestrator")
    return ConversationBridge(http_client=client, session_store=SessionStore())


def test_platform_user_id_namespaced():
    assert platform_user_id(Channel.WHATSAPP, "27820001111") == "whatsapp:27820001111"
    assert platform_user_id(Channel.TELEGRAM, "999") == "telegram:999"


async def test_help_intent_short_circuits_without_calling_orchestrator():
    called = False

    def handler(request):  # pragma: no cover - must NOT be hit
        nonlocal called
        called = True
        return httpx.Response(200, json={"text": "x"})

    bridge = _bridge(handler)
    out = await bridge.handle(
        InboundMessage(channel=Channel.SMS, channel_user_id="+27820001111", text="help")
    )
    assert "VocalMarket" in out.text
    assert called is False


async def test_vertical_switch_is_remembered():
    seen = {}

    def handler(request):
        body = request.read().decode()
        seen["body"] = body
        return httpx.Response(200, json={"text": "Found 2 items", "products": [], "suggested_actions": []})

    bridge = _bridge(handler)
    user = "+27820002222"

    # First message switches to suppliers, no orchestrator call.
    out = await bridge.handle(
        InboundMessage(channel=Channel.SMS, channel_user_id=user, text="suppliers")
    )
    assert "B2B Procurement" in out.text

    # Next message should route to b2b_procurement.
    await bridge.handle(
        InboundMessage(channel=Channel.SMS, channel_user_id=user, text="steel bolts")
    )
    assert '"vertical": "b2b_procurement"' in seen["body"] or '"vertical":"b2b_procurement"' in seen["body"]


async def test_orchestrator_response_maps_products_and_actions():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "text": "Here are your options",
                "products": [
                    {"name": "Full Cream Milk 2L", "price": 32.99, "currency": "R", "in_stock": True},
                    {"name": "Brown Bread", "price": 18.5, "currency": "R", "in_stock": False},
                ],
                "suggested_actions": [
                    {"label": "Add to cart", "payload": "add:milk"},
                    {"type": "checkout"},
                ],
            },
        )

    bridge = _bridge(handler)
    out = await bridge.handle(
        InboundMessage(channel=Channel.TELEGRAM, channel_user_id="555", text="milk and bread", vertical="grocery")
    )
    assert out.text == "Here are your options"
    assert len(out.products) == 2
    assert out.products[1].in_stock is False
    assert out.suggestions[0].label == "Add to cart"
    assert out.suggestions[1].label == "checkout"

    flat = out.to_plain_text()
    assert "Full Cream Milk 2L" in flat
    assert "out of stock" in flat


async def test_orchestrator_failure_degrades_gracefully():
    def handler(request):
        return httpx.Response(503, json={"detail": "down"})

    bridge = _bridge(handler)
    out = await bridge.handle(
        InboundMessage(channel=Channel.SLACK, channel_user_id="U1", text="hi", vertical="grocery")
    )
    assert "couldn't reach" in out.text.lower()
