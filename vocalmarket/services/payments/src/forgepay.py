"""
ForgePay client.

Supports three payment methods:
  1. card       — standard card charge via ForgePay gateway
  2. stablecoin — USDC/USDT on-chain payment (EVM)
  3. x402       — HTTP 402 Payment Required micro-payment protocol

All methods return a PaymentSession with a redirect URL or payment address
depending on the method. Webhooks confirm final settlement.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from enum import Enum

import httpx
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ForgePaySettings(BaseSettings):
    forgepay_base_url: str = "https://api.forgepay.io/v1"
    forgepay_api_key: str = ""
    forgepay_webhook_secret: str = ""
    forgepay_merchant_id: str = ""

    class Config:
        env_prefix = "FORGEPAY_"


_settings = ForgePaySettings()


class PaymentMethod(str, Enum):
    CARD = "card"
    STABLECOIN = "stablecoin"
    X402 = "x402"


class Currency(str, Enum):
    ZAR = "ZAR"
    USDC = "USDC"
    USDT = "USDT"


@dataclass
class PaymentSession:
    session_id: str
    order_id: str
    method: PaymentMethod
    amount: float
    currency: Currency
    # card / stablecoin: redirect URL  |  x402: payment address
    payment_url: str
    wallet_address: str | None = None
    chain_id: int | None = None       # EVM chain ID for stablecoin
    expires_at: int | None = None     # Unix timestamp


class InitiatePaymentRequest(BaseModel):
    order_id: str
    amount: float
    currency: Currency = Currency.ZAR
    method: PaymentMethod = PaymentMethod.CARD
    return_url: str = ""
    cancel_url: str = ""
    metadata: dict = {}


class ForgePayClient:
    """Async ForgePay API client."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=_settings.forgepay_base_url,
            headers={
                "Authorization": f"Bearer {_settings.forgepay_api_key}",
                "X-Merchant-Id": _settings.forgepay_merchant_id,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def initiate(self, req: InitiatePaymentRequest) -> PaymentSession:
        resp = await self._http.post(
            "/payments/sessions",
            json={
                "order_id": req.order_id,
                "amount": int(req.amount * 100),  # cents
                "currency": req.currency.value,
                "method": req.method.value,
                "return_url": req.return_url,
                "cancel_url": req.cancel_url,
                "metadata": req.metadata,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        return PaymentSession(
            session_id=data["session_id"],
            order_id=req.order_id,
            method=req.method,
            amount=req.amount,
            currency=req.currency,
            payment_url=data.get("payment_url", ""),
            wallet_address=data.get("wallet_address"),
            chain_id=data.get("chain_id"),
            expires_at=data.get("expires_at"),
        )

    async def get_session(self, session_id: str) -> dict:
        resp = await self._http.get(f"/payments/sessions/{session_id}")
        resp.raise_for_status()
        return resp.json()

    async def refund(self, payment_id: str, amount: float | None = None) -> dict:
        body = {"payment_id": payment_id}
        if amount is not None:
            body["amount"] = int(amount * 100)
        resp = await self._http.post("/payments/refunds", json=body)
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify ForgePay webhook HMAC-SHA256 signature."""
        expected = hmac.new(
            _settings.forgepay_webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


# Module-level singleton
forgepay = ForgePayClient()
