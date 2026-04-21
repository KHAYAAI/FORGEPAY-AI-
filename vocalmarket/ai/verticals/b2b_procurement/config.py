from __future__ import annotations

import os

import httpx

from ..base import BaseVertical

_intelligence_http: httpx.AsyncClient | None = None


def _get_intelligence_client() -> httpx.AsyncClient:
    global _intelligence_http
    if _intelligence_http is None:
        _intelligence_http = httpx.AsyncClient(
            base_url=os.environ.get("INTELLIGENCE_BASE_URL", "http://intelligence:8004"),
            timeout=5.0,
        )
    return _intelligence_http


class B2BProcurementVertical(BaseVertical):
    name = "b2b_procurement"

    def system_prompt_fragment(self) -> str:
        return """
You are a B2B procurement assistant for business buyers.
- Always confirm quantities, unit prices, and quote validity before placing orders.
- For orders above the user's single-order limit, flag for approval workflow.
- Surface pricing tiers and volume discounts proactively.
- Support RFQ (Request for Quotation) workflows — help the user draft and send RFQs.
- Track preferred supplier contracts — highlight when a non-contracted supplier is cheaper.
- Use get_supplier_intelligence to recommend the most reliable supplier before placing orders.
- Use record_delivery_outcome when a user confirms or complains about a delivery.
"""

    def extra_tools(self) -> list:
        from vocalmarket.services.ai_orchestrator.src.tools.intelligence_tools import (
            GetSupplierIntelligenceTool,
            RecordDeliveryOutcomeTool,
        )
        client = _get_intelligence_client()
        return [
            GetSupplierIntelligenceTool(intelligence_client=client),
            RecordDeliveryOutcomeTool(intelligence_client=client),
        ]

    async def pre_order_compliance_check(
        self, order_items: list[dict], user_id: str
    ) -> tuple[bool, str]:
        """Block orders that exceed the user's single-order spend limit."""
        total = sum(item.get("unit_price", 0) * item.get("quantity", 1) for item in order_items)
        # Sprint 2: replace with org profile lookup via OrganizationService
        spend_limit = int(os.environ.get("B2B_DEFAULT_SPEND_LIMIT", "50000"))
        if total > spend_limit:
            return False, (
                f"This order total of R{total:,.0f} exceeds your single-order limit "
                f"of R{spend_limit:,.0f}. "
                "Please request approval from your procurement manager."
            )
        return True, ""
