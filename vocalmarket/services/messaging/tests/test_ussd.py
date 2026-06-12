"""USSD state machine — the menu logic must work with no network and stay short."""

import httpx

from vocalmarket.services.messaging.src.bridge import ConversationBridge
from vocalmarket.services.messaging.src.channels.ussd import USSDAdapter
from vocalmarket.services.messaging.src.sessions import SessionStore


def _adapter(handler=None) -> USSDAdapter:
    handler = handler or (lambda request: httpx.Response(200, json={"text": "ok"}))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://orch")
    bridge = ConversationBridge(http_client=client, session_store=SessionStore())
    return USSDAdapter(bridge)


async def test_empty_text_shows_main_menu():
    out = await _adapter()._handle("+27820001234", "")
    assert out.startswith("CON")
    assert "Grocery" in out and "Pharmacy" in out and "Suppliers" in out


async def test_vertical_selected_prompts_for_request():
    out = await _adapter()._handle("+27820001234", "1")
    assert out.startswith("CON")
    assert "Grocery" in out


async def test_free_text_runs_a_turn_and_keeps_session_open():
    captured = {}

    def handler(request):
        captured["body"] = request.read().decode()
        return httpx.Response(
            200, json={"text": "Milk 2L is R32.99", "products": [], "suggested_actions": []}
        )

    out = await _adapter(handler)._handle("+27820001234", "1*buy milk")
    assert "buy milk" in captured["body"]
    assert '"vertical": "grocery"' in captured["body"] or '"vertical":"grocery"' in captured["body"]
    assert out.startswith("CON")
    assert "Milk 2L is R32.99" in out
    assert "Exit" in out


async def test_explicit_exit_ends_session():
    out = await _adapter()._handle("+27820001234", "1*buy milk*00")
    assert out.startswith("END")


async def test_invalid_selection_reprompts_menu():
    out = await _adapter()._handle("+27820001234", "9")
    assert out.startswith("CON")
    assert "Grocery" in out
