"""ForgePay payments service — FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from .forgepay import Currency, ForgePayClient, InitiatePaymentRequest, PaymentMethod, forgepay
from .webhooks import router as webhook_router
from .x402 import (
    PAYMENT_AMOUNTS,
    X402PaymentDetails,
    build_402_response,
    verify_x402_payment,
)
import time


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await forgepay.aclose()


app = FastAPI(title="VocalMarket Payments Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(webhook_router)
FastAPIInstrumentor.instrument_app(app)


class InitiateRequest(BaseModel):
    order_id: str
    amount: float
    currency: Currency = Currency.ZAR
    method: PaymentMethod = PaymentMethod.CARD
    return_url: str = ""
    cancel_url: str = ""
    metadata: dict = {}


@app.post("/payments/initiate")
async def initiate_payment(req: InitiateRequest):
    """Initiate a payment session. Returns redirect URL or wallet address."""
    session = await forgepay.initiate(InitiatePaymentRequest(**req.model_dump()))
    return {
        "session_id": session.session_id,
        "payment_url": session.payment_url,
        "wallet_address": session.wallet_address,
        "chain_id": session.chain_id,
        "expires_at": session.expires_at,
        "method": session.method.value,
    }


@app.get("/payments/sessions/{session_id}")
async def get_payment_session(session_id: str):
    return await forgepay.get_session(session_id)


@app.post("/payments/{payment_id}/refund")
async def refund_payment(payment_id: str, amount: float | None = None):
    return await forgepay.refund(payment_id, amount)


@app.get("/resources/procurement-data")
async def procurement_data(request=Depends(lambda r: r)):
    """
    Example x402-gated resource. Returns 402 on first call, data after payment.
    """
    from fastapi import Request
    valid, error = await verify_x402_payment(request)
    if not valid:
        return build_402_response(X402PaymentDetails(
            amount=PAYMENT_AMOUNTS["procurement_data_query"],
            currency="USDC",
            chain_id=8453,  # Base mainnet
            recipient=__import__("os").environ.get("FORGEPAY_WALLET_ADDRESS", ""),
            resource="procurement_data_query",
            expires_at=int(time.time()) + 300,
            memo="VocalMarket B2B procurement data query",
        ))
    return {"data": "Procurement market data payload..."}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "payments"}
