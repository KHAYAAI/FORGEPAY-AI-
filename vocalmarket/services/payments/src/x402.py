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
import time
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import JSONResponse


@dataclass
class X402PaymentDetails:
    """Structured payment details returned in a 402 response."""
    amount: int          # In smallest currency unit (satoshis / USDC micro-units)
    currency: str        # "USDC" | "USDT" | "ETH"
    chain_id: int        # EVM chain ID (e.g. 8453 for Base)
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

    Returns (valid, error_message). If valid=True the request can proceed.
    In production this calls an on-chain verifier or ForgePay's receipt API.
    """
    receipt = request.headers.get("X-Payment-Receipt")
    if not receipt:
        return False, "Missing X-Payment-Receipt header"

    try:
        decoded = json.loads(base64.b64decode(receipt))
        # Validate expiry
        if decoded.get("expires_at", 0) < int(time.time()):
            return False, "Payment receipt expired"
        # TODO: verify on-chain transaction hash via ForgePay receipt API
        return True, None
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"Invalid receipt: {e}"


# Standard micropayment amounts for VocalMarket resources (in USDC micro-units)
PAYMENT_AMOUNTS = {
    "procurement_data_query": 10_000,    # 0.01 USDC per query
    "prescription_verification": 50_000, # 0.05 USDC per verification
    "market_price_feed": 5_000,          # 0.005 USDC per request
}
