"""Self-hosted Whisper STT wrapper."""

import io

import httpx
from pydantic_settings import BaseSettings


class STTSettings(BaseSettings):
    whisper_base_url: str = "http://whisper:9000"  # faster-whisper-server container
    whisper_model: str = "large-v3"
    whisper_language: str = "en"

    class Config:
        env_prefix = "VOICE_"


_settings = STTSettings()


class WhisperSTT:
    """
    Calls a self-hosted faster-whisper-server (OpenAI-compatible /v1/audio/transcriptions).
    Drop-in replacement for OpenAI Whisper API — no vendor lock-in.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=_settings.whisper_base_url, timeout=30.0)

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.webm"

        response = await self._client.post(
            "/v1/audio/transcriptions",
            files={"file": ("audio.webm", audio_file, "audio/webm")},
            data={
                "model": _settings.whisper_model,
                "language": language or _settings.whisper_language,
                "response_format": "json",
            },
        )
        response.raise_for_status()
        return response.json()["text"].strip()

    async def aclose(self) -> None:
        await self._client.aclose()
