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


class SupplierDiscoveryInput(BaseModel):
    query: str = Field(
        description=(
            "Natural language description of what you need: product type, "
            "certifications, location, capacity. E.g. 'ISO 9001 steel bolt supplier "
            "South Africa MOQ under 500'."
        )
    )
    vertical: str = Field(
        default="b2b_procurement",
        description="Vertical: grocery | b2b_procurement | healthcare",
    )
    country_code: str | None = Field(
        default=None,
        description="ISO 3166-1 alpha-2 country code to filter by, e.g. 'ZA' or 'IN'",
    )
    certifications: list[str] = Field(
        default_factory=list,
        description="Required certifications, e.g. ['ISO_9001', 'IATF_16949']",
    )
    max_moq: int | None = Field(
        default=None,
        description="Maximum acceptable minimum order quantity",
    )
    max_lead_time_days: int | None = Field(
        default=None,
        description="Maximum acceptable typical lead time in days",
    )
    limit: int = Field(default=5, ge=1, le=20, description="Number of suppliers to return")


class SupplierDiscoveryTool(BaseTool):
    """
    Discover suppliers by capability using semantic search.

    Use when the user asks to find suppliers, compare options, or needs a
    supplier matching specific requirements (certifications, location, MOQ, lead time).
    Returns structured profiles with reliability scores where available.
    Replaces the simpler get_suppliers tool with intelligence-backed discovery.
    """

    name: str = "discover_suppliers"
    description: str = (
        "Find suppliers matching capability requirements using semantic search. "
        "Use when the user asks 'find me a supplier for X', 'who can supply ISO 9001 "
        "fasteners?', or compares supplier options. Supports filtering by country, "
        "certifications, MOQ, and lead time."
    )
    args_schema: type[BaseModel] = SupplierDiscoveryInput
    intelligence_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(
        self,
        query: str,
        vertical: str = "b2b_procurement",
        country_code: str | None = None,
        certifications: list[str] | None = None,
        max_moq: int | None = None,
        max_lead_time_days: int | None = None,
        limit: int = 5,
    ) -> str:
        try:
            resp = await self.intelligence_client.get(
                "/suppliers/discover",
                params={
                    "query": query,
                    "vertical": vertical,
                    "country_code": country_code or "",
                    "certifications": ",".join(certifications) if certifications else "",
                    "max_moq": max_moq,
                    "max_lead_time_days": max_lead_time_days,
                    "limit": limit,
                },
            )
            resp.raise_for_status()
        except httpx.RequestError as e:
            return f"Supplier discovery service unavailable: {e}"
        except httpx.HTTPStatusError as e:
            return f"Discovery failed: {e.response.status_code}"

        suppliers = resp.json().get("suppliers", [])
        if not suppliers:
            return (
                "No suppliers found matching those criteria. "
                "Try broadening your search or contact the procurement team to add suppliers."
            )

        lines = []
        for s in suppliers:
            certs = ", ".join(s.get("certifications", [])) or "none listed"
            lead = s.get("lead_time_days_typical", "?")
            moq = s.get("moq", "?")
            region = s.get("region", "") or s.get("country_code", "")
            score = s.get("reliability_score")
            score_str = f", reliability {score:.0%}" if score is not None else ""
            lines.append(
                f"**{s['supplier_name']}** ({region}): "
                f"certs: {certs}, lead {lead}d, MOQ {moq}{score_str}"
            )

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
