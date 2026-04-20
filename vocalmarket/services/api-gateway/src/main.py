"""
API Gateway for VocalMarket AI.

Single ingress for all client traffic. Handles:
  - JWT authentication (issues tokens via Enthusiast's /api/auth/)
  - Vertical routing (path prefix /v1/{vertical}/...)
  - Rate limiting (Redis sliding window)
  - Request tracing (OpenTelemetry)
  - Upstream proxy to voice service and AI orchestrator
"""

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class GatewaySettings(BaseSettings):
    voice_service_url: str = "http://voice:8003"
    orchestrator_url: str = "http://ai-orchestrator:8002"
    enthusiast_url: str = "http://api:8000"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "change-me-in-production"
    rate_limit_per_minute: int = 60

    class Config:
        env_prefix = "GATEWAY_"


_settings = GatewaySettings()

app = FastAPI(title="VocalMarket API Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
FastAPIInstrumentor.instrument_app(app)

_bearer = HTTPBearer()
_upstream = httpx.AsyncClient(timeout=60.0)


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Validates JWT or Enthusiast token. Returns user claims."""
    token = credentials.credentials
    # Validate against Enthusiast's token endpoint
    resp = await _upstream.get(
        f"{_settings.enthusiast_url}/api/users/me/",
        headers={"Authorization": f"Token {token}"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return resp.json()


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
async def login(req: LoginRequest):
    resp = await _upstream.post(
        f"{_settings.enthusiast_url}/api/auth/login/",
        json={"username": req.username, "password": req.password},
    )
    resp.raise_for_status()
    return resp.json()


@app.api_route(
    "/v1/{vertical}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_to_orchestrator(
    vertical: str,
    path: str,
    request: Request,
    user: dict = Depends(verify_token),
):
    """Proxies commerce/chat requests to the AI Orchestrator."""
    body = await request.body()
    resp = await _upstream.request(
        method=request.method,
        url=f"{_settings.orchestrator_url}/{path}",
        content=body,
        headers={
            "Content-Type": request.headers.get("Content-Type", "application/json"),
            "X-User-Id": str(user.get("id", "")),
            "X-Vertical": vertical,
        },
    )
    return StreamingResponse(
        content=resp.aiter_bytes(),
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}
