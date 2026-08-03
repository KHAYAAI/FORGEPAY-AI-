"""
Voice Processing Service.

WebSocket endpoint that accepts raw audio chunks, streams them to Whisper STT,
forwards the transcription to the AI Orchestrator, then streams TTS audio back.

Flow per session:
  client → [audio chunks] → Whisper → text → Orchestrator → text → ElevenLabs → [audio chunks] → client
"""

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .stt import WhisperSTT
from .tts import ElevenLabsTTS

app = FastAPI(title="VocalMarket Voice Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_stt = WhisperSTT()
_tts = ElevenLabsTTS()


@app.websocket("/ws/voice/{vertical}/{user_id}")
async def voice_session(websocket: WebSocket, vertical: str, user_id: str):
    await websocket.accept()

    import httpx
    orchestrator_client = httpx.AsyncClient(base_url="http://ai-orchestrator:8002")
    conversation_id = f"{user_id}-{vertical}-{int(asyncio.get_event_loop().time())}"

    try:
        while True:
            # Receive audio chunk (binary) or control message (text)
            message = await websocket.receive()

            # Starlette's low-level receive() returns the disconnect event as
            # a plain message rather than raising WebSocketDisconnect — that
            # only happens on the receive_text()/receive_bytes()/receive_json()
            # convenience wrappers. Without this check, the next receive()
            # call on an already-disconnected socket raises RuntimeError on
            # every normal client disconnect.
            if message["type"] == "websocket.disconnect":
                break

            if "bytes" in message:
                audio_bytes = message["bytes"]

                # 1. Transcribe
                text = await _stt.transcribe(audio_bytes)
                await websocket.send_json({"type": "transcription", "text": text})

                # 2. Get AI response
                resp = await orchestrator_client.post("/chat", json={
                    "user_id": user_id,
                    "message": text,
                    "vertical": vertical,
                    "conversation_id": conversation_id,
                })
                resp.raise_for_status()
                response_text = resp.json()["text"]

                # 3. Stream TTS back as audio chunks
                await websocket.send_json({"type": "agent_response", "text": response_text})
                async for chunk in _tts.stream(response_text):
                    await websocket.send_bytes(chunk)
                await websocket.send_json({"type": "tts_complete"})

            elif "text" in message:
                control = message["text"]
                if control == "ping":
                    await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        await orchestrator_client.aclose()


@app.get("/health")
async def health():
    return {"status": "ok", "stt": "whisper", "tts": "elevenlabs"}
