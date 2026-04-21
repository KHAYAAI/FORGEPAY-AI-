"""
Intelligence tools — give Hermes access to the supplier intelligence store.

These tools answer questions like:
  "Which supplier has the best delivery record for steel fasteners?"
  "What is Acme Industries' defect rate?"
  "Compare supplier reliability for hydraulic components"

They call the intelligence service over HTTP rather than hitting the DB directly,
keeping the orchestrator stateless and the intelligence store independently scalable.
"""

from __future__ import annotations

import httpx
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

INTELLIGENCE_BASE = "http://intelligence:8004"


class GetSupplierIntelligenceInput(BaseModel):
    supplier_ids: list[str] = Field(
        default_factory=list,
        description="Optional list of specific supplier IDs to query. Leave empty to get top suppliers.",
    )
    vertical: str = Field(
        default="b2b_procurement",
        description="Vertical to filter suppliers by (grocery|b2b_procurement|healthcare).",
    )
    limit: int = Field(
        default=5,
        description="Maximum number of suppliers to return, sorted by reliability score.",
        ge=1,
        le=20,
    )


class GetSupplierIntelligenceTool(BaseTool):
    """
    Query the supplier intelligence store for performance metrics.

    Use this when the user asks about supplier reliability, delivery performance,
    defect rates, or wants to compare suppliers before placing an order.
    Returns ranked suppliers with delivery_rate, defect_rate, and reliability_score.
    """

    name: str = "get_supplier_intelligence"
    description: str = (
        "Get performance intelligence on suppliers: delivery rate, defect rate, "
        "reliability score, and RFQ response time. Use when the user asks 'which supplier "
        "is most reliable?', 'what is supplier X's delivery record?', or wants to compare "
        "suppliers. Only available in b2b_procurement and healthcare verticals."
    )
    args_schema: type[BaseModel] = GetSupplierIntelligenceInput
    intelligence_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(
        self,
        supplier_ids: list[str] | None = None,
        vertical: str = "b2b_procurement",
        limit: int = 5,
    ) -> str:
        try:
            resp = await self.intelligence_client.get(
                f"{INTELLIGENCE_BASE}/suppliers/intelligence",
                params={
                    "supplier_ids": ",".join(supplier_ids) if supplier_ids else "",
                    "vertical": vertical,
                    "limit": limit,
                },
            )
            resp.raise_for_status()
        except httpx.RequestError as e:
            return f"Supplier intelligence service unavailable: {e}"
        except httpx.HTTPStatusError as e:
            return f"Failed to fetch supplier intelligence: {e.response.status_code}"

        suppliers = resp.json().get("suppliers", [])
        if not suppliers:
            return "No supplier intelligence data available yet. Data builds up as orders are placed."

        lines = []
        for s in suppliers:
            score = s.get("reliability_score", 0)
            delivery = s.get("delivery_rate", 0)
            defects = s.get("defect_rate", 0)
            orders = s.get("total_orders", 0)
            rfq_hours = s.get("avg_rfq_response_hours")

            confidence = "low confidence" if orders < 5 else f"{orders} orders"
            rfq_str = f", RFQ response {rfq_hours:.1f}h" if rfq_hours else ""
            lines.append(
                f"{s['supplier_name']}: reliability {score:.0%}, "
                f"on-time {delivery:.0%}, defect rate {defects:.0%}{rfq_str} ({confidence})"
            )

        return "\n".join(lines)

    def _run(self, *args, **kwargs):
        raise NotImplementedError


class RecordDeliveryOutcomeInput(BaseModel):
    order_id: str = Field(description="Medusa order ID that was delivered")
    supplier_id: str = Field(description="Supplier who fulfilled the order")
    was_on_time: bool = Field(description="Whether delivery arrived on or before promised date")
    had_defect: bool = Field(default=False, description="Whether the delivery had quality issues")


class RecordDeliveryOutcomeTool(BaseTool):
    """
    Record the delivery outcome for a completed order.

    Use this when the user confirms they received their order and reports whether
    it arrived on time and in good condition. This feeds the supplier intelligence
    data moat and improves future recommendations.
    """

    name: str = "record_delivery_outcome"
    description: str = (
        "Record whether a delivery arrived on time and without defects. "
        "Use when the user says their order arrived, especially if they mention "
        "it was late or had quality issues. This improves future supplier recommendations."
    )
    args_schema: type[BaseModel] = RecordDeliveryOutcomeInput
    intelligence_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(
        self,
        order_id: str,
        supplier_id: str,
        was_on_time: bool,
        had_defect: bool = False,
    ) -> str:
        try:
            resp = await self.intelligence_client.post(
                f"{INTELLIGENCE_BASE}/suppliers/delivery-outcome",
                json={
                    "order_id": order_id,
                    "supplier_id": supplier_id,
                    "was_on_time": was_on_time,
                    "had_defect": had_defect,
                },
            )
            resp.raise_for_status()
        except httpx.RequestError as e:
            return f"Could not record delivery outcome: {e}"
        except httpx.HTTPStatusError:
            return "Failed to record delivery outcome."

        if had_defect:
            return (
                "Noted — I've recorded that this delivery had quality issues. "
                "This will factor into future supplier recommendations."
            )
        if not was_on_time:
            return (
                "Noted — I've recorded the late delivery. "
                "This will factor into this supplier's reliability score."
            )
        return "Great — I've recorded the on-time delivery. This helps improve supplier recommendations."

    def _run(self, *args, **kwargs):
        raise NotImplementedError
