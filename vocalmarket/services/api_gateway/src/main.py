"""
API Gateway for VocalMarket AI.

Single ingress for all client traffic. Handles:
  - JWT authentication (local PyJWT verification + fallback to Enthusiast token)
  - Vertical routing (path prefix /v1/{vertical}/...)
  - Request tracing (OpenTelemetry)
  - Upstream proxy to voice service and AI orchestrator
"""

from __future__ import annotations

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class GatewaySettings(BaseSettings):
    voice_service_url: str = "http://voice:8003"
    orchestrator_url: str = "http://ai_orchestrator:8002"
    enthusiast_url: str = "http://api:8000"
    payments_service_url: str = "http://payments:8001"
    redis_url: str = "redis://redis:6379/0"
    # Required — no default. Service refuses to start if unset.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # Comma-separated allowed CORS origins. Production MUST set this explicitly.
    allowed_origins: str = ""
    # Service-account token for internal Enthusiast calls (org-member-context).
    enthusiast_service_token: str = ""

    class Config:
        env_prefix = "GATEWAY_"

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


_settings = GatewaySettings()

if not _settings.jwt_secret:
    raise RuntimeError(
        "GATEWAY_JWT_SECRET must be set — refusing to start without a JWT secret"
    )

app = FastAPI(title="VocalMarket API Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.get_allowed_origins(),  # explicit whitelist — no wildcards
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Vertical"],
)
FastAPIInstrumentor.instrument_app(app)

_bearer = HTTPBearer()
_upstream = httpx.AsyncClient(timeout=60.0)


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """
    Verify an incoming token.

    1. Tries local JWT verification (fast, no network).
    2. Falls back to Enthusiast DRF token endpoint for service-account tokens.
    """
    token = credentials.credentials

    # Local JWT path (preferred for web/mobile clients)
    try:
        payload = jwt.decode(
            token,
            _settings.jwt_secret,
            algorithms=[_settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        pass  # Not a JWT — try Enthusiast DRF token fallback

    # Fallback: Enthusiast DRF Token (service accounts, CLI)
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
    "/v1/payments/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_to_payments(
    path: str,
    request: Request,
    user: dict = Depends(verify_token),
):
    """
    Authenticated proxy to the payments service.

    Registered BEFORE the /v1/{vertical}/{path:path} catch-all below —
    Starlette matches routes in registration order, so this must come first
    or "/v1/payments/..." would be swallowed by the vertical proxy with
    vertical="payments".

    Keeps ForgePay credentials and the payments service itself off the public
    internet — clients only ever see the gateway, which attaches the caller's
    identity so payment sessions can be tied back to a user.
    """
    user_id = str(user.get("id", user.get("sub", "")))
    body = await request.body()

    resp = await _upstream.request(
        method=request.method,
        url=f"{_settings.payments_service_url}/payments/{path}",
        content=body,
        headers={
            "Content-Type": request.headers.get("Content-Type", "application/json"),
            "X-User-Id": user_id,
        },
    )
    return StreamingResponse(
        content=resp.aiter_bytes(),
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


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
    user_id = str(user.get("id", user.get("sub", "")))
    body = await request.body()

    # Forward org context to orchestrator so B2B compliance checks work correctly.
    # The org-member-context endpoint is internal (service-account only).
    org_headers = await _fetch_org_context(user_id)

    resp = await _upstream.request(
        method=request.method,
        url=f"{_settings.orchestrator_url}/{path}",
        content=body,
        headers={
            "Content-Type": request.headers.get("Content-Type", "application/json"),
            "X-User-Id": user_id,
            "X-Vertical": vertical,
            **org_headers,
        },
    )
    return StreamingResponse(
        content=resp.aiter_bytes(),
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


async def _fetch_org_context(user_id: str) -> dict[str, str]:
    """
    Fetch org membership context from Enthusiast and return as headers.
    Non-fatal — if the call fails (user not in an org, service down) we return
    empty headers and the orchestrator falls back to env-var defaults.
    """
    if not user_id:
        return {}
    try:
        resp = await _upstream.get(
            f"{_settings.enthusiast_url}/api/internal/org-member-context/{user_id}",
            headers={"Authorization": f"Token {_settings.enthusiast_service_token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            headers = {}
            if data.get("org_id"):
                headers["X-Org-Id"] = str(data["org_id"])
            if data.get("role"):
                headers["X-Org-Role"] = data["role"]
            if data.get("spend_limit_cents"):
                headers["X-Spend-Limit-Cents"] = str(data["spend_limit_cents"])
            if data.get("currency_code"):
                headers["X-Currency"] = data["currency_code"]
            if data.get("country_code"):
                headers["X-Country-Code"] = data["country_code"]
            return headers
    except Exception:
        pass
    return {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}
