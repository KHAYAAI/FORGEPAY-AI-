"""
Tests for x402 payment verification (vocalmarket/services/payments/src/x402.py).

Key paths covered:
  - Missing receipt header → rejected
  - Invalid base64 → rejected
  - Expired receipt → rejected
  - Missing tx_hash → rejected
  - Dev mode (no API key) → accepted with warning
  - ForgePay API: verified=True → accepted
  - ForgePay API: verified=False with reason → rejected
  - ForgePay API: 404 → rejected
  - ForgePay API: network error → rejected
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# We test the function directly, not through FastAPI, to avoid real settings loading.


def _encode_receipt(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _valid_receipt(*, offset: int = 300, tx_hash: str = "0xabc123") -> dict:
    return {
        "tx_hash": tx_hash,
        "chain_id": 8453,
        "recipient": "0xRecipient",
        "amount": 50_000,
        "currency": "USDC",
        "expires_at": int(time.time()) + offset,
    }


@pytest.fixture()
def mock_request_with_receipt(receipt_header: str | None = "PLACEHOLDER"):
    """Returns a callable that builds a mock FastAPI Request."""
    def _make(header_value: str | None):
        req = MagicMock()
        headers = {}
        if header_value is not None:
            headers["X-Payment-Receipt"] = header_value
        req.headers = headers
        return req
    return _make


class TestVerifyX402Payment:
    """Unit tests for verify_x402_payment()."""

    @pytest.mark.asyncio
    async def test_missing_receipt_header(self):
        from vocalmarket.services.payments.src.x402 import verify_x402_payment

        req = MagicMock()
        req.headers = {}
        valid, err = await verify_x402_payment(req)
        assert not valid
        assert "Missing" in err

    @pytest.mark.asyncio
    async def test_invalid_base64(self):
        from vocalmarket.services.payments.src.x402 import verify_x402_payment

        req = MagicMock()
        req.headers = {"X-Payment-Receipt": "!!!notbase64!!!"}
        valid, err = await verify_x402_payment(req)
        assert not valid
        assert "Invalid" in err

    @pytest.mark.asyncio
    async def test_expired_receipt(self):
        from vocalmarket.services.payments.src.x402 import verify_x402_payment

        receipt = _valid_receipt(offset=-10)  # 10 seconds in the past
        req = MagicMock()
        req.headers = {"X-Payment-Receipt": _encode_receipt(receipt)}
        valid, err = await verify_x402_payment(req)
        assert not valid
        assert "expired" in err.lower()

    @pytest.mark.asyncio
    async def test_missing_tx_hash(self):
        from vocalmarket.services.payments.src.x402 import verify_x402_payment

        receipt = _valid_receipt()
        del receipt["tx_hash"]
        req = MagicMock()
        req.headers = {"X-Payment-Receipt": _encode_receipt(receipt)}
        valid, err = await verify_x402_payment(req)
        assert not valid
        assert "transaction hash" in err.lower()

    @pytest.mark.asyncio
    async def test_dev_mode_no_api_key(self):
        """When FORGEPAY_API_KEY is not set, verification is skipped (dev only)."""
        from vocalmarket.services.payments.src import x402

        receipt = _valid_receipt()
        req = MagicMock()
        req.headers = {"X-Payment-Receipt": _encode_receipt(receipt)}

        with patch.object(x402._x402_settings, "forgepay_api_key", ""):
            valid, err = await x402.verify_x402_payment(req)

        assert valid
        assert err is None

    @pytest.mark.asyncio
    async def test_forgepay_api_verified_true(self):
        from vocalmarket.services.payments.src import x402

        receipt = _valid_receipt()
        req = MagicMock()
        req.headers = {"X-Payment-Receipt": _encode_receipt(receipt)}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"verified": True}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(x402._x402_settings, "forgepay_api_key", "test-key"),
            patch("vocalmarket.services.payments.src.x402.httpx.AsyncClient", return_value=mock_client),
        ):
            valid, err = await x402.verify_x402_payment(req)

        assert valid
        assert err is None

    @pytest.mark.asyncio
    async def test_forgepay_api_verified_false(self):
        from vocalmarket.services.payments.src import x402

        receipt = _valid_receipt()
        req = MagicMock()
        req.headers = {"X-Payment-Receipt": _encode_receipt(receipt)}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"verified": False, "reason": "insufficient funds"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(x402._x402_settings, "forgepay_api_key", "test-key"),
            patch("vocalmarket.services.payments.src.x402.httpx.AsyncClient", return_value=mock_client),
        ):
            valid, err = await x402.verify_x402_payment(req)

        assert not valid
        assert "insufficient funds" in err

    @pytest.mark.asyncio
    async def test_forgepay_api_404(self):
        from vocalmarket.services.payments.src import x402

        receipt = _valid_receipt()
        req = MagicMock()
        req.headers = {"X-Payment-Receipt": _encode_receipt(receipt)}

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(x402._x402_settings, "forgepay_api_key", "test-key"),
            patch("vocalmarket.services.payments.src.x402.httpx.AsyncClient", return_value=mock_client),
        ):
            valid, err = await x402.verify_x402_payment(req)

        assert not valid
        assert "not found" in err.lower()

    @pytest.mark.asyncio
    async def test_forgepay_network_error(self):
        import httpx as _httpx
        from vocalmarket.services.payments.src import x402

        receipt = _valid_receipt()
        req = MagicMock()
        req.headers = {"X-Payment-Receipt": _encode_receipt(receipt)}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_httpx.RequestError("timeout"))

        with (
            patch.object(x402._x402_settings, "forgepay_api_key", "test-key"),
            patch("vocalmarket.services.payments.src.x402.httpx.AsyncClient", return_value=mock_client),
        ):
            valid, err = await x402.verify_x402_payment(req)

        assert not valid
        assert "unavailable" in err.lower()


class TestBuild402Response:
    def test_correct_status_and_headers(self):
        from vocalmarket.services.payments.src.x402 import X402PaymentDetails, build_402_response

        payment = X402PaymentDetails(
            amount=50_000,
            currency="USDC",
            chain_id=8453,
            recipient="0xRecipient",
            resource="prescription_verification",
            expires_at=int(time.time()) + 60,
        )
        resp = build_402_response(payment)
        assert resp.status_code == 402
        assert resp.headers["X-Payment-Currency"] == "USDC"
        assert resp.headers["X-Payment-Amount"] == "50000"
        assert resp.headers["X-Payment-Network"] == "eip155:8453"

        # Encoded header must be decodable
        decoded = json.loads(base64.b64decode(resp.headers["X-Payment-Required"]))
        assert decoded["amount"] == 50_000
        assert decoded["currency"] == "USDC"
