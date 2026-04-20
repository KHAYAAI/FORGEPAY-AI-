"""
x402 Payment Required protocol support.

x402 is an open standard for machine-to-machine HTTP micropayments.
When a resource returns 402, the client reads the payment details from
the response headers, pays, and retries with the receipt in headers.

VocalMarket uses x402 for:
  - B2B API access fees (per-call pricing for procurement data)
  - Healthcare document access (prescription verification fees)
  - Premium real-time market data (grocery price intelligence)

Reference: https://x402.org
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class X402Settings(BaseSettings):
    forgepay_receipt_url: str = "https://api.forgepay.io/v1/payments/receipts/verify"
    forgepay_api_key: str = ""

    class Config:
        env_prefix = "FORGEPAY_"


_x402_settings = X402Settings()


@dataclass
class X402PaymentDetails:
    """Structured payment details returned in a 402 response."""
    amount: int          # In smallest currency unit (USDC micro-units = 1e-6 USDC)
    currency: str        # "USDC" | "USDT" | "ETH"
    chain_id: int        # EVM chain ID (e.g. 8453 for Base mainnet)
    recipient: str       # Wallet address
    resource: str        # What is being paid for
    expires_at: int      # Unix timestamp
    memo: str = ""


def build_402_response(payment: X402PaymentDetails) -> JSONResponse:
    """
    Return a standards-compliant 402 response with x402 payment headers.

    Headers set:
      X-Payment-Required: base64-encoded JSON payment details
      X-Payment-Network: chain identifier
      X-Payment-Recipient: wallet address
    """
    details = {
        "amount": payment.amount,
        "currency": payment.currency,
        "chain_id": payment.chain_id,
        "recipient": payment.recipient,
        "resource": payment.resource,
        "expires_at": payment.expires_at,
        "memo": payment.memo,
    }
    encoded = base64.b64encode(json.dumps(details).encode()).decode()

    return JSONResponse(
        status_code=402,
        content={"error": "Payment required", "resource": payment.resource},
        headers={
            "X-Payment-Required": encoded,
            "X-Payment-Network": f"eip155:{payment.chain_id}",
            "X-Payment-Recipient": payment.recipient,
            "X-Payment-Amount": str(payment.amount),
            "X-Payment-Currency": payment.currency,
        },
    )


async def verify_x402_payment(request: Request) -> tuple[bool, str | None]:
    """
    Verify the X-Payment-Receipt header on an incoming request.

    Validates:
      1. Receipt header presence and decodability
      2. Receipt expiry (client-side)
      3. On-chain / ForgePay receipt validity (server-side)

    Returns (valid, error_message). If valid=True the request can proceed.
    """
    receipt = request.headers.get("X-Payment-Receipt")
    if not receipt:
        return False, "Missing X-Payment-Receipt header"

    try:
        decoded = json.loads(base64.b64decode(receipt))
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"Invalid receipt encoding: {e}"

    # 1. Validate receipt expiry
    if decoded.get("expires_at", 0) < int(time.time()):
        return False, "Payment receipt expired"

    # 2. Require a transaction hash for on-chain receipts
    tx_hash = decoded.get("tx_hash") or decoded.get("transaction_hash")
    if not tx_hash:
        return False, "Receipt missing transaction hash"

    # 3. Verify with ForgePay receipt API (authoritative on-chain check)
    if not _x402_settings.forgepay_api_key:
        logger.warning("FORGEPAY_API_KEY not set — skipping receipt verification (dev mode only)")
        return True, None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _x402_settings.forgepay_receipt_url,
                json={
                    "tx_hash": tx_hash,
                    "chain_id": decoded.get("chain_id"),
                    "recipient": decoded.get("recipient"),
                    "amount": decoded.get("amount"),
                    "currency": decoded.get("currency"),
                },
                headers={
                    "Authorization": f"Bearer {_x402_settings.forgepay_api_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.RequestError as e:
        logger.error("ForgePay receipt verification network error: %s", e)
        return False, "Payment verification service unavailable"

    if resp.status_code == 200:
        result = resp.json()
        if result.get("verified"):
            return True, None
        return False, result.get("reason", "Receipt verification failed")

    if resp.status_code == 404:
        return False, "Transaction not found on-chain"

    logger.error("ForgePay receipt API returned %s: %s", resp.status_code, resp.text[:200])
    return False, f"Receipt verification failed (status {resp.status_code})"


# Standard micropayment amounts for VocalMarket resources (in USDC micro-units, 1e-6 USDC)
PAYMENT_AMOUNTS = {
    "procurement_data_query": 10_000,     # 0.01 USDC per query
    "prescription_verification": 50_000,  # 0.05 USDC per verification
    "market_price_feed": 5_000,           # 0.005 USDC per request
}
