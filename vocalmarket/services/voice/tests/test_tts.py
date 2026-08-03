"""Tests for ElevenLabsTTS (vocalmarket/services/voice/src/tts.py)."""

from __future__ import annotations

import httpx
import pytest

from vocalmarket.services.voice.src.tts import ElevenLabsTTS


def _tts_with(handler, *, default_voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> ElevenLabsTTS:
    tts = ElevenLabsTTS.__new__(ElevenLabsTTS)
    tts._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.elevenlabs.io"
    )
    return tts


class TestStream:
    @pytest.mark.asyncio
    async def test_streams_audio_bytes_from_default_voice(self, monkeypatch):
        import vocalmarket.services.voice.src.tts as tts_module

        monkeypatch.setattr(tts_module._settings, "voice_id_za_english", "default-voice-id")
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, content=b"chunk-1chunk-2")

        tts = _tts_with(handler)

        chunks = [c async for c in tts.stream("Hello there")]

        assert b"".join(chunks) == b"chunk-1chunk-2"
        assert captured["url"].endswith("/v1/text-to-speech/default-voice-id/stream")

    @pytest.mark.asyncio
    async def test_explicit_voice_id_overrides_default(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, content=b"audio")

        tts = _tts_with(handler)

        _ = [c async for c in tts.stream("Sawubona", voice_id="za-afrikaans-voice")]

        assert captured["url"].endswith("/v1/text-to-speech/za-afrikaans-voice/stream")

    @pytest.mark.asyncio
    async def test_raises_on_upstream_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "invalid api key"})

        tts = _tts_with(handler)

        with pytest.raises(httpx.HTTPStatusError):
            _ = [c async for c in tts.stream("hi")]

    @pytest.mark.asyncio
    async def test_aclose_closes_underlying_client(self):
        tts = _tts_with(lambda r: httpx.Response(200, content=b""))
        await tts.aclose()
        assert tts._client.is_closed
