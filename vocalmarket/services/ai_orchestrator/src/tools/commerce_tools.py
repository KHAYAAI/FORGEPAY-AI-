"""
Commerce tools for the Hermes agent — thin wrappers that call the
Medusa.js commerce service and ForgePay payments service over HTTP.

Kept as Python LangChain tools so Hermes can call them alongside
Enthusiast tools without switching languages.
"""

from __future__ import annotations

import httpx
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class GetOrderStatusInput(BaseModel):
    order_id: str = Field(description="Medusa order ID to look up")


class GetOrderStatusTool(BaseTool):
    """Look up the current status and details of an existing order."""

    name: str = "get_order_status"
    description: str = (
        "Get the current status of an order the user has already placed. "
        "Use when the user asks 'where is my order' or 'what happened to order X'."
    )
    args_schema: type[BaseModel] = GetOrderStatusInput
    medusa_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(self, order_id: str) -> str:
        resp = await self.medusa_client.get(f"/store/orders/{order_id}")
        if resp.status_code == 404:
            return f"Order {order_id} not found."
        resp.raise_for_status()
        order = resp.json().get("order", {})
        items = order.get("items", [])
        item_lines = ", ".join(f"{i['title']} x{i['quantity']}" for i in items[:5])
        return (
            f"Order {order_id}: status={order.get('status', 'unknown')}, "
            f"total={order.get('currency_code','ZAR').upper()} {order.get('total', 0) / 100:.2f}, "
            f"items: {item_lines}"
        )

    def _run(self, *args, **kwargs):
        raise NotImplementedError


class GetSuppliersInput(BaseModel):
    vertical: str = Field(description="Vertical: grocery | b2b_procurement | healthcare")
    curated_only: bool = Field(default=False, description="Only return preferred/locked-in suppliers")


class GetSuppliersTool(BaseTool):
    """List available suppliers for a vertical, with preferred suppliers highlighted."""

    name: str = "get_suppliers"
    description: str = (
        "List available suppliers for the current vertical. "
        "Use when the user asks to compare suppliers, or wants to know who is preferred."
    )
    args_schema: type[BaseModel] = GetSuppliersInput
    medusa_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(self, vertical: str, curated_only: bool = False) -> str:
        resp = await self.medusa_client.get(
            "/admin/vendors",
            params={"vertical": vertical, "curated_only": curated_only},
        )
        resp.raise_for_status()
        vendors = resp.json().get("vendors", [])
        if not vendors:
            return "No suppliers found for this vertical."
        lines = []
        for v in vendors[:10]:
            tag = " [PREFERRED]" if v.get("is_curated") else ""
            lines.append(f"- {v['name']}{tag}: {v.get('description', '')[:80]}")
        return "\n".join(lines)

    def _run(self, *args, **kwargs):
        raise NotImplementedError


class RequestQuoteInput(BaseModel):
    items: list[dict] = Field(description="List of {product_id, quantity, notes}")
    supplier_id: str = Field(description="Supplier to request quote from")
    delivery_date: str | None = Field(default=None, description="Required delivery date YYYY-MM-DD")


class RequestQuoteTool(BaseTool):
    """Create an RFQ (Request for Quotation) — used in B2B procurement vertical."""

    name: str = "request_quote"
    description: str = (
        "Create a Request for Quotation (RFQ) for bulk B2B orders. "
        "Use when the user wants pricing for large quantities or custom terms. "
        "Only relevant in the b2b_procurement vertical."
    )
    args_schema: type[BaseModel] = RequestQuoteInput
    medusa_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(self, items: list[dict], supplier_id: str, delivery_date: str | None = None) -> str:
        resp = await self.medusa_client.post(
            "/store/rfq",
            json={"items": items, "supplier_id": supplier_id, "delivery_date": delivery_date},
        )
        resp.raise_for_status()
        rfq = resp.json()
        return (
            f"RFQ #{rfq['id']} submitted to {rfq.get('supplier_name', supplier_id)}. "
            f"You'll receive a quote within {rfq.get('response_sla_hours', 24)} hours."
        )

    def _run(self, *args, **kwargs):
        raise NotImplementedError
