"""WhatsApp payload parsing — Meta batches messages in a nested envelope."""

import httpx

from vocalmarket.services.messaging.src.bridge import ConversationBridge
from vocalmarket.services.messaging.src.channels.whatsapp import WhatsAppAdapter
from vocalmarket.services.messaging.src.sessions import SessionStore


def _adapter() -> WhatsAppAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), base_url="http://orch")
    bridge = ConversationBridge(http_client=client, session_store=SessionStore())
    return WhatsAppAdapter(bridge)


def test_parse_text_message():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "27820001111",
                                    "id": "wamid.ABC",
                                    "type": "text",
                                    "text": {"body": "I need 50 bags of cement"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    msgs = _adapter()._parse(payload)
    assert len(msgs) == 1
    assert msgs[0].channel_user_id == "27820001111"
    assert msgs[0].text == "I need 50 bags of cement"
    assert msgs[0].reply_context["message_id"] == "wamid.ABC"


def test_parse_interactive_button_reply():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "27820002222",
                                    "id": "wamid.XYZ",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {"id": "b2b_procurement", "title": "Suppliers"},
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    msgs = _adapter()._parse(payload)
    assert msgs[0].text == "b2b_procurement"


def test_parse_ignores_status_only_events():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert _adapter()._parse(payload) == []
