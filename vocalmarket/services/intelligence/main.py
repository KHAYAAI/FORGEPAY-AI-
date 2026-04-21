"""
Supplier Intelligence Service — FastAPI app.

Exposes the SupplierIntelligenceStore over HTTP for:
  - Internal use: webhooks service posts transactions
  - Hermes tools: orchestrator queries supplier rankings
  - Future public API: analytics endpoints (Sprint 4)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .supplier_store import SupplierIntelligenceStore, get_supplier_intelligence_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_supplier_intelligence_store()
    yield
    global _store_instance
    if _store_instance := app.state.store if hasattr(app.state, "store") else None:
        await _store_instance.aclose()


app = FastAPI(title="VocalMarket Intelligence Service", lifespan=lifespan)


class TransactionRequest(BaseModel):
    order_id: str
    supplier_id: str
    supplier_name: str
    vertical: str
    order_value_cents: int = 0
    was_on_time: bool | None = None
    had_defect: bool = False
    delivery_delta_seconds: int | None = None


class DeliveryOutcomeRequest(BaseModel):
    order_id: str
    supplier_id: str
    was_on_time: bool
    had_defect: bool = False


class RFQResponseRequest(BaseModel):
    supplier_id: str
    response_time_hours: float
    was_accepted: bool


@app.post("/internal/transactions", status_code=201)
async def record_transaction(req: TransactionRequest):
    store = await get_supplier_intelligence_store()
    await store.record_transaction(
        order_id=req.order_id,
        supplier_id=req.supplier_id,
        supplier_name=req.supplier_name,
        vertical=req.vertical,
        order_value_cents=req.order_value_cents,
        was_on_time=req.was_on_time,
        had_defect=req.had_defect,
        delivery_delta_seconds=req.delivery_delta_seconds,
    )
    return {"status": "recorded"}


@app.post("/suppliers/delivery-outcome")
async def record_delivery_outcome(req: DeliveryOutcomeRequest):
    store = await get_supplier_intelligence_store()
    await store.record_transaction(
        order_id=req.order_id,
        supplier_id=req.supplier_id,
        supplier_name="",
        vertical="b2b_procurement",
        order_value_cents=0,
        was_on_time=req.was_on_time,
        had_defect=req.had_defect,
    )
    return {"status": "recorded"}


@app.post("/internal/rfq-response")
async def record_rfq_response(req: RFQResponseRequest):
    store = await get_supplier_intelligence_store()
    await store.record_rfq_response(
        supplier_id=req.supplier_id,
        response_time_hours=req.response_time_hours,
        was_accepted=req.was_accepted,
    )
    return {"status": "recorded"}


@app.get("/suppliers/intelligence")
async def get_supplier_intelligence(
    supplier_ids: str = "",
    vertical: str | None = None,
    limit: int = 10,
):
    store = await get_supplier_intelligence_store()
    ids = [s.strip() for s in supplier_ids.split(",") if s.strip()] if supplier_ids else None
    suppliers = await store.get_supplier_intelligence(
        supplier_ids=ids,
        vertical=vertical,
        limit=min(limit, 50),
    )
    return {"suppliers": suppliers}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "intelligence"}
