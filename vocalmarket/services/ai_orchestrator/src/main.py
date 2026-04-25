"""FastAPI entry point for the AI Orchestrator service."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from vocalmarket.shared.config.feature_flags import Vertical
from .orchestrator import AIOrchestrator, ConversationTurn, OrchestratorResponse

_orchestrator: AIOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    _orchestrator = AIOrchestrator()
    yield
    # Cleanup
    if _orchestrator._hermes:
        await _orchestrator._hermes.aclose()
    await _orchestrator._enthusiast.aclose()


app = FastAPI(title="VocalMarket AI Orchestrator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
FastAPIInstrumentor.instrument_app(app)


class ChatRequest(BaseModel):
    user_id: str
    message: str
    vertical: Vertical
    conversation_id: str
    data_set_id: str | None = None


@app.post("/chat", response_model=OrchestratorResponse)
async def chat(req: ChatRequest, request: Request) -> OrchestratorResponse:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialised")

    # Org context forwarded by the API gateway as headers
    org_id = request.headers.get("X-Org-Id") or None

    turn = ConversationTurn(
        user_id=req.user_id,
        message=req.message,
        vertical=req.vertical,
        conversation_id=req.conversation_id,
        data_set_id=req.data_set_id,
        org_id=org_id,
    )
    return await _orchestrator.process(turn)


@app.get("/health")
async def health():
    return {"status": "ok"}
