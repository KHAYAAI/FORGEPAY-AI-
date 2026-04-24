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

from .supplier_store import SupplierCapabilityProfile, SupplierIntelligenceStore, get_supplier_intelligence_store


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


class OnboardSupplierRequest(BaseModel):
    supplier_id: str
    supplier_name: str
    vertical: str
    description: str
    country_code: str = "ZA"
    region: str = ""
    certifications: list[str] = []
    lead_time_days_min: int = 7
    lead_time_days_typical: int = 14
    moq: int = 1
    capacity_units_per_month: int | None = None


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


@app.post("/suppliers/onboard", status_code=201)
async def onboard_supplier(req: OnboardSupplierRequest):
    """
    Register or update a supplier capability profile.
    Called by the supplier portal on signup, or by admin when adding a curated supplier.
    Generates a pgvector embedding from the capability text for semantic discovery.
    """
    store = await get_supplier_intelligence_store()
    await store.register_supplier(
        supplier_id=req.supplier_id,
        supplier_name=req.supplier_name,
        vertical=req.vertical,
        description=req.description,
        country_code=req.country_code,
        region=req.region,
        certifications=req.certifications,
        lead_time_days_min=req.lead_time_days_min,
        lead_time_days_typical=req.lead_time_days_typical,
        moq=req.moq,
        capacity_units_per_month=req.capacity_units_per_month,
    )
    return {"status": "registered", "supplier_id": req.supplier_id}


@app.get("/suppliers/discover")
async def discover_suppliers(
    query: str,
    vertical: str | None = None,
    country_code: str | None = None,
    certifications: str = "",
    max_lead_time_days: int | None = None,
    max_moq: int | None = None,
    limit: int = 10,
):
    """
    Semantic supplier discovery. Uses pgvector cosine similarity when embeddings are
    configured, falls back to keyword search otherwise.
    """
    store = await get_supplier_intelligence_store()
    cert_list = [c.strip() for c in certifications.split(",") if c.strip()] if certifications else None
    suppliers = await store.discover_suppliers(
        query=query,
        vertical=vertical,
        country_code=country_code,
        certifications=cert_list,
        max_lead_time_days=max_lead_time_days,
        max_moq=max_moq,
        limit=min(limit, 50),
    )
    return {"suppliers": suppliers, "count": len(suppliers)}


@app.get("/suppliers/{supplier_id}/profile")
async def get_supplier_profile(supplier_id: str):
    """Return the full capability profile for a specific supplier."""
    store = await get_supplier_intelligence_store()
    async with store._session_factory() as session:
        from sqlalchemy import select as sa_select
        result = await session.execute(
            sa_select(SupplierCapabilityProfile).where(
                SupplierCapabilityProfile.supplier_id == supplier_id
            )
        )
        profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Supplier not found")
    import json
    return {
        "supplier_id": profile.supplier_id,
        "supplier_name": profile.supplier_name,
        "vertical": profile.vertical,
        "country_code": profile.country_code,
        "region": profile.region,
        "description": profile.description,
        "certifications": json.loads(profile.certifications or "[]"),
        "lead_time_days_min": profile.lead_time_days_min,
        "lead_time_days_typical": profile.lead_time_days_typical,
        "moq": profile.moq,
        "capacity_units_per_month": profile.capacity_units_per_month,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "intelligence"}
