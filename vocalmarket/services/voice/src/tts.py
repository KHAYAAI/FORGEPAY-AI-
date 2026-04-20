"""ElevenLabs TTS wrapper with South African English accent support."""

from typing import AsyncIterator

import httpx
from pydantic_settings import BaseSettings


class TTSSettings(BaseSettings):
    elevenlabs_api_key: str = ""
    # South African English voices from ElevenLabs voice library
    voice_id_za_english: str = "21m00Tcm4TlvDq8ikWAM"
    voice_id_za_afrikaans: str = ""   # Optional Afrikaans voice
    tts_model: str = "eleven_turbo_v2_5"  # Low-latency model for real-time
    tts_output_format: str = "mp3_44100_128"

    class Config:
        env_prefix = "VOICE_"


_settings = TTSSettings()
_BASE_URL = "https://api.elevenlabs.io"


class ElevenLabsTTS:
    """
    Streams TTS audio from ElevenLabs.
    Uses the /v1/text-to-speech/{voice_id}/stream endpoint for low latency.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"xi-api-key": _settings.elevenlabs_api_key},
            timeout=60.0,
        )

    async def stream(self, text: str, voice_id: str | None = None) -> AsyncIterator[bytes]:
        vid = voice_id or _settings.voice_id_za_english
        async with self._client.stream(
            "POST",
            f"/v1/text-to-speech/{vid}/stream",
            json={
                "text": text,
                "model_id": _settings.tts_model,
                "output_format": _settings.tts_output_format,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            },
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(chunk_size=4096):
                yield chunk

    async def aclose(self) -> None:
        await self._client.aclose()
