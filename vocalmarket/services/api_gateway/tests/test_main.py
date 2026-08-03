"""
Tests for the API Gateway (vocalmarket/services/api_gateway/src/main.py).

GatewaySettings is a module-level singleton built from the environment at
import time, and the JWT-secret guard raises RuntimeError during import — so
most tests here re-import the module fresh under controlled env vars rather
than importing it once at collection time.

Key paths covered:
  - Missing GATEWAY_JWT_SECRET refuses to start
  - CORS origin whitelist parsing (no wildcards, whitespace/empties dropped)
  - verify_token(): valid JWT, expired JWT, non-JWT falling back to Enthusiast,
    and a fully invalid token being rejected
  - /v1/payments/{path} is routed to the payments service, not swallowed by
    the /v1/{vertical}/{path} catch-all registered after it
  - /v1/{vertical}/{path} forwards vertical + user headers to the orchestrator
"""

from __future__ import annotations

import importlib
import sys
import time

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

MODULE_NAME = "vocalmarket.services.api_gateway.src.main"
SECRET = "test-secret-min-32-characters-long-value"


def _fresh_import(monkeypatch, **env_overrides):
    env = {
        "GATEWAY_JWT_SECRET": SECRET,
        "GATEWAY_ALLOWED_ORIGINS": "http://localhost:5173",
        "GATEWAY_ENTHUSIAST_URL": "http://enthusiast.test",
        "GATEWAY_PAYMENTS_SERVICE_URL": "http://payments.test",
        "GATEWAY_ORCHESTRATOR_URL": "http://orchestrator.test",
    }
    env.update(env_overrides)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME)


def _mock_client(handler, base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base_url)


def _token(**claims) -> str:
    payload = {"sub": "1", "exp": int(time.time()) + 3600, **claims}
    return jwt.encode(payload, SECRET, algorithm="HS256")


class TestStartupGuard:
    def test_missing_jwt_secret_refuses_to_start(self, monkeypatch):
        with pytest.raises(RuntimeError, match="GATEWAY_JWT_SECRET"):
            _fresh_import(monkeypatch, GATEWAY_JWT_SECRET=None)

    def test_empty_jwt_secret_refuses_to_start(self, monkeypatch):
        with pytest.raises(RuntimeError, match="GATEWAY_JWT_SECRET"):
            _fresh_import(monkeypatch, GATEWAY_JWT_SECRET="")


class TestCorsOriginWhitelist:
    def test_parses_comma_separated_origins(self, monkeypatch):
        module = _fresh_import(
            monkeypatch, GATEWAY_ALLOWED_ORIGINS="http://a.example, http://b.example"
        )
        assert module._settings.get_allowed_origins() == ["http://a.example", "http://b.example"]

    def test_drops_empty_and_whitespace_entries(self, monkeypatch):
        module = _fresh_import(monkeypatch, GATEWAY_ALLOWED_ORIGINS="http://a.example,, , ")
        assert module._settings.get_allowed_origins() == ["http://a.example"]

    def test_no_origins_configured_yields_empty_whitelist_not_wildcard(self, monkeypatch):
        module = _fresh_import(monkeypatch, GATEWAY_ALLOWED_ORIGINS="")
        assert module._settings.get_allowed_origins() == []


class TestVerifyToken:
    @pytest.mark.asyncio
    async def test_valid_jwt_is_accepted(self, monkeypatch):
        module = _fresh_import(monkeypatch)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_token(sub="42"))

        payload = await module.verify_token(creds)

        assert payload["sub"] == "42"

    @pytest.mark.asyncio
    async def test_expired_jwt_is_rejected(self, monkeypatch):
        module = _fresh_import(monkeypatch)
        expired = jwt.encode(
            {"sub": "1", "exp": int(time.time()) - 10}, SECRET, algorithm="HS256"
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired)

        with pytest.raises(HTTPException) as exc_info:
            await module.verify_token(creds)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_non_jwt_falls_back_to_enthusiast_and_succeeds(self, monkeypatch):
        module = _fresh_import(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Token drf-token-value"
            return httpx.Response(200, json={"id": 7, "email": "amara@vocalmarket.ai"})

        module._upstream = _mock_client(handler, "http://enthusiast.test")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="drf-token-value")

        user = await module.verify_token(creds)

        assert user["id"] == 7

    @pytest.mark.asyncio
    async def test_non_jwt_rejected_when_enthusiast_also_rejects_it(self, monkeypatch):
        module = _fresh_import(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "Invalid token"})

        module._upstream = _mock_client(handler, "http://enthusiast.test")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")

        with pytest.raises(HTTPException) as exc_info:
            await module.verify_token(creds)
        assert exc_info.value.status_code == 401


class TestPaymentsProxyRouting:
    """
    Guards the route-ordering fix: /v1/payments/{path} must be registered
    before the /v1/{vertical}/{path} catch-all, or a request to
    "/v1/payments/initiate" would be swallowed by the vertical proxy with
    vertical="payments" and never reach the payments service.
    """

    def test_payments_path_is_forwarded_to_payments_service_not_orchestrator(self, monkeypatch):
        module = _fresh_import(monkeypatch)
        module.app.dependency_overrides[module.verify_token] = lambda: {"id": "1", "sub": "1"}

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"session_id": "sess_1", "payment_url": "https://pay.example/sess_1"})

        module._upstream = _mock_client(handler, "http://payments.test")

        client = TestClient(module.app)
        resp = client.post(
            "/v1/payments/initiate",
            json={"order_id": "order_1", "amount": 100.0},
            headers={"Authorization": "Bearer irrelevant"},
        )

        assert resp.status_code == 200
        assert captured["url"] == "http://payments.test/payments/initiate"
        assert resp.json()["session_id"] == "sess_1"

    def test_payments_path_carries_user_id_header(self, monkeypatch):
        module = _fresh_import(monkeypatch)
        module.app.dependency_overrides[module.verify_token] = lambda: {"id": "99"}

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["user_id"] = request.headers.get("X-User-Id")
            return httpx.Response(200, json={})

        module._upstream = _mock_client(handler, "http://payments.test")

        client = TestClient(module.app)
        client.post("/v1/payments/initiate", json={"order_id": "o1", "amount": 1})

        assert captured["user_id"] == "99"


class TestOrchestratorProxyRouting:
    def test_vertical_and_user_headers_forwarded(self, monkeypatch):
        module = _fresh_import(monkeypatch)
        module.app.dependency_overrides[module.verify_token] = lambda: {"id": "5", "sub": "5"}

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["vertical"] = request.headers.get("X-Vertical")
            captured["user_id"] = request.headers.get("X-User-Id")
            return httpx.Response(200, json={"text": "hi"})

        module._upstream = _mock_client(handler, "http://orchestrator.test")

        client = TestClient(module.app)
        resp = client.post(
            "/v1/grocery/conversations/conv-1/messages",
            json={"content": "find milk"},
            headers={"Authorization": "Bearer irrelevant"},
        )

        assert resp.status_code == 200
        assert captured["vertical"] == "grocery"
        assert captured["user_id"] == "5"
        assert captured["url"] == "http://orchestrator.test/conversations/conv-1/messages"
