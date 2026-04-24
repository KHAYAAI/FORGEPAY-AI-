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
- Use discover_suppliers to find new suppliers by capability (certifications, location, MOQ, lead time).
- Use get_supplier_intelligence to compare performance metrics for known suppliers.
- Use record_delivery_outcome when a user confirms or complains about a delivery.
"""

    def extra_tools(self) -> list:
        from vocalmarket.services.ai_orchestrator.src.tools.commerce_tools import SupplierDiscoveryTool
        from vocalmarket.services.ai_orchestrator.src.tools.intelligence_tools import (
            GetSupplierIntelligenceTool,
            RecordDeliveryOutcomeTool,
        )
        client = _get_intelligence_client()
        return [
            SupplierDiscoveryTool(intelligence_client=client),
            GetSupplierIntelligenceTool(intelligence_client=client),
            RecordDeliveryOutcomeTool(intelligence_client=client),
        ]

    async def pre_order_compliance_check(
        self, order_items: list[dict], user_id: str
    ) -> tuple[bool, str]:
        """
        Block orders that exceed the user's effective spend limit.

        Fetches the limit from the OrganizationService (Enthusiast /api/internal/
        org-member-context/<user_id>). Falls back to B2B_DEFAULT_SPEND_LIMIT env
        var if the service is unreachable (dev mode / non-org users).
        """
        total = sum(item.get("unit_price", 0) * item.get("quantity", 1) for item in order_items)
        spend_limit, currency = await self._get_spend_limit(user_id)
        if total > spend_limit:
            return False, (
                f"This order total of {currency} {total / 100:,.2f} exceeds your "
                f"single-order limit of {currency} {spend_limit / 100:,.2f}. "
                "Please request approval from your procurement manager."
            )
        return True, ""

    async def _get_spend_limit(self, user_id: str) -> tuple[int, str]:
        """Fetch org-level spend limit and currency from Enthusiast. Returns (cents, currency)."""
        enthusiast_base = os.environ.get("ORCHESTRATOR_ENTHUSIAST_BASE_URL", "http://api:8000")
        service_token = os.environ.get("ORCHESTRATOR_ENTHUSIAST_API_KEY", "")
        default_limit = int(os.environ.get("B2B_DEFAULT_SPEND_LIMIT", "5000000"))  # R50,000 in cents
        default_currency = "ZAR"

        if not service_token:
            return default_limit, default_currency

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"{enthusiast_base}/api/internal/org-member-context/{user_id}",
                    headers={"Authorization": f"Token {service_token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return (
                        data.get("spend_limit_cents", default_limit),
                        data.get("currency_code", default_currency),
                    )
        except httpx.RequestError:
            pass

        return default_limit, default_currency
