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
from fastapi.responses import HTMLResponse
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


@app.get("/supplier-portal", response_class=HTMLResponse)
async def supplier_portal():
    """
    Self-service supplier onboarding portal.
    Served at http://intelligence:8004/supplier-portal
    Submits to POST /suppliers/onboard.
    """
    return HTMLResponse(content=_SUPPLIER_PORTAL_HTML)


_SUPPLIER_PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VocalMarket — Supplier Onboarding</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; margin: 0; padding: 2rem; color: #1a1a1a; }
    .card { background: white; border-radius: 12px; padding: 2rem; max-width: 680px; margin: 0 auto; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
    h1 { font-size: 1.5rem; margin: 0 0 0.25rem; }
    .sub { color: #666; margin: 0 0 2rem; font-size: 0.9rem; }
    label { display: block; font-weight: 600; font-size: 0.85rem; margin-bottom: 0.25rem; margin-top: 1rem; }
    input, select, textarea { width: 100%; padding: 0.6rem 0.8rem; border: 1px solid #ddd; border-radius: 6px; font-size: 0.95rem; }
    textarea { resize: vertical; min-height: 80px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .certs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.4rem; }
    .cert-chip { display: flex; align-items: center; gap: 0.3rem; background: #f0f0f0; border-radius: 4px; padding: 0.25rem 0.5rem; font-size: 0.8rem; }
    .cert-chip input[type=checkbox] { width: auto; margin: 0; }
    button { margin-top: 1.5rem; width: 100%; padding: 0.85rem; background: #0070f3; color: white; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; }
    button:hover { background: #0060d3; }
    #result { margin-top: 1rem; padding: 1rem; border-radius: 8px; display: none; }
    #result.ok { background: #e6f9ed; color: #1a6b35; border: 1px solid #a3d9b1; }
    #result.err { background: #fde8e8; color: #8b1a1a; border: 1px solid #f5a5a5; }
  </style>
</head>
<body>
<div class="card">
  <h1>VocalMarket Supplier Portal</h1>
  <p class="sub">Register your capabilities so buyers can discover you via voice search.</p>
  <form id="form">
    <div class="row">
      <div>
        <label for="supplier_id">Supplier ID *</label>
        <input id="supplier_id" name="supplier_id" required placeholder="e.g. sup_steelsa_001">
      </div>
      <div>
        <label for="supplier_name">Company Name *</label>
        <input id="supplier_name" name="supplier_name" required placeholder="e.g. Steel SA (Pty) Ltd">
      </div>
    </div>
    <div class="row">
      <div>
        <label for="vertical">Vertical *</label>
        <select id="vertical" name="vertical">
          <option value="b2b_procurement">B2B Procurement</option>
          <option value="grocery">Grocery</option>
          <option value="healthcare">Healthcare</option>
        </select>
      </div>
      <div>
        <label for="country_code">Country *</label>
        <select id="country_code" name="country_code">
          <option value="ZA">South Africa</option>
          <option value="IN">India</option>
          <option value="US">United States</option>
          <option value="DE">Germany</option>
          <option value="FR">France</option>
        </select>
      </div>
    </div>
    <label for="region">Region / Province</label>
    <input id="region" name="region" placeholder="e.g. Gauteng, Maharashtra">
    <label for="description">Capability Description *</label>
    <textarea id="description" name="description" required placeholder="Describe your products, manufacturing capabilities, materials, and specialisations..."></textarea>
    <label>Certifications</label>
    <div class="certs">
      <label class="cert-chip"><input type="checkbox" value="ISO_9001"> ISO 9001</label>
      <label class="cert-chip"><input type="checkbox" value="IATF_16949"> IATF 16949</label>
      <label class="cert-chip"><input type="checkbox" value="ISO_14001"> ISO 14001</label>
      <label class="cert-chip"><input type="checkbox" value="ISO_45001"> ISO 45001</label>
      <label class="cert-chip"><input type="checkbox" value="SABS"> SABS</label>
      <label class="cert-chip"><input type="checkbox" value="CE"> CE</label>
      <label class="cert-chip"><input type="checkbox" value="FDA_510K"> FDA 510(k)</label>
      <label class="cert-chip"><input type="checkbox" value="CDSCO"> CDSCO</label>
    </div>
    <div class="row">
      <div>
        <label for="lead_time_days_min">Min Lead Time (days)</label>
        <input id="lead_time_days_min" name="lead_time_days_min" type="number" min="1" value="7">
      </div>
      <div>
        <label for="lead_time_days_typical">Typical Lead Time (days)</label>
        <input id="lead_time_days_typical" name="lead_time_days_typical" type="number" min="1" value="14">
      </div>
    </div>
    <div class="row">
      <div>
        <label for="moq">Min Order Quantity (MOQ)</label>
        <input id="moq" name="moq" type="number" min="1" value="1">
      </div>
      <div>
        <label for="capacity_units_per_month">Monthly Capacity (units)</label>
        <input id="capacity_units_per_month" name="capacity_units_per_month" type="number" min="0" placeholder="Optional">
      </div>
    </div>
    <button type="submit">Register as Supplier</button>
  </form>
  <div id="result"></div>
</div>
<script>
document.getElementById('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const certInputs = document.querySelectorAll('.certs input[type=checkbox]:checked');
  const certs = Array.from(certInputs).map(i => i.value);
  const capacity = fd.get('capacity_units_per_month');
  const payload = {
    supplier_id: fd.get('supplier_id'),
    supplier_name: fd.get('supplier_name'),
    vertical: fd.get('vertical'),
    country_code: fd.get('country_code'),
    region: fd.get('region') || '',
    description: fd.get('description'),
    certifications: certs,
    lead_time_days_min: parseInt(fd.get('lead_time_days_min')),
    lead_time_days_typical: parseInt(fd.get('lead_time_days_typical')),
    moq: parseInt(fd.get('moq')),
    capacity_units_per_month: capacity ? parseInt(capacity) : null,
  };
  const el = document.getElementById('result');
  try {
    const res = await fetch('/suppliers/onboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      el.className = 'ok';
      el.textContent = `✓ Registered successfully! Supplier ID: ${data.supplier_id}. Buyers can now discover you via voice search.`;
    } else {
      el.className = 'err';
      el.textContent = `Error: ${data.detail || JSON.stringify(data)}`;
    }
  } catch (err) {
    el.className = 'err';
    el.textContent = `Network error: ${err.message}`;
  }
  el.style.display = 'block';
});
</script>
</body>
</html>"""


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
