"""
Tests for the voice WebSocket session (vocalmarket/services/voice/src/service.py).

Exercises the full per-turn flow — audio in → transcription → orchestrator
call → TTS out — with the STT/TTS singletons and the orchestrator's httpx
client replaced by test doubles, so no real Whisper/ElevenLabs/orchestrator
network calls happen.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

import vocalmarket.services.voice.src.service as service_module


class _FakeSTT:
    def __init__(self, text: str):
        self._text = text
        self.calls = 0

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        self.calls += 1
        return self._text


class _FakeTTS:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def stream(self, text: str, voice_id: str | None = None):
        for chunk in self._chunks:
            yield chunk


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(service_module, "_stt", _FakeSTT("add milk to my cart"))
    monkeypatch.setattr(service_module, "_tts", _FakeTTS([b"audio-chunk-1", b"audio-chunk-2"]))

    def orchestrator_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat"
        body = request.read()
        import json

        payload = json.loads(body)
        assert payload["message"] == "add milk to my cart"
        assert payload["vertical"] == "grocery"
        return httpx.Response(200, json={"text": "Added milk to your cart."})

    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        return real_async_client(
            transport=httpx.MockTransport(orchestrator_handler),
            base_url=kwargs.get("base_url", "http://ai-orchestrator:8002"),
        )

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    return TestClient(service_module.app)


class TestVoiceSession:
    def test_ping_pong(self, client):
        with client.websocket_connect("/ws/voice/grocery/user-1") as ws:
            ws.send_text("ping")
            assert ws.receive_json() == {"type": "pong"}

    def test_client_disconnect_does_not_raise_server_side(self, client):
        """
        Regression test: the handler used to call websocket.receive() again
        after the disconnect message, which raises RuntimeError on Starlette's
        WebSocket rather than being caught by `except WebSocketDisconnect`.
        Simply opening and cleanly closing a session must not error.
        """
        with client.websocket_connect("/ws/voice/grocery/user-1") as ws:
            ws.send_text("ping")
            assert ws.receive_json() == {"type": "pong"}
        # Exiting the `with` block sends the disconnect frame; no exception
        # should propagate out of the server-side handler.

    def test_full_turn_transcribes_calls_orchestrator_and_streams_tts(self, client):
        with client.websocket_connect("/ws/voice/grocery/user-1") as ws:
            ws.send_bytes(b"raw-audio-bytes")

            transcription = ws.receive_json()
            assert transcription == {"type": "transcription", "text": "add milk to my cart"}

            agent_response = ws.receive_json()
            assert agent_response == {"type": "agent_response", "text": "Added milk to your cart."}

            chunk_1 = ws.receive_bytes()
            chunk_2 = ws.receive_bytes()
            assert chunk_1 == b"audio-chunk-1"
            assert chunk_2 == b"audio-chunk-2"

            complete = ws.receive_json()
            assert complete == {"type": "tts_complete"}

    def test_stt_invoked_once_per_audio_chunk(self, client):
        with client.websocket_connect("/ws/voice/grocery/user-1") as ws:
            ws.send_bytes(b"chunk-a")
            for _ in range(4):
                ws.receive()  # drain transcription/agent_response/2 tts chunks
            ws.receive_json()  # tts_complete

        assert service_module._stt.calls == 1


class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "stt": "whisper", "tts": "elevenlabs"}
