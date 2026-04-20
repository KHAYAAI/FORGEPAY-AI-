from ..base import BaseVertical


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
"""

    def extra_tools(self) -> list:
        # RFQ tools implemented in Phase 2
        return []

    async def pre_order_compliance_check(self, order_items: list[dict], user_id: str) -> tuple[bool, str]:
        """Block orders that exceed the user's single-order spend limit."""
        total = sum(item.get("unit_price", 0) * item.get("quantity", 1) for item in order_items)
        spend_limit = 50_000  # ZAR — in production, fetch from user profile
        if total > spend_limit:
            return False, (
                f"This order total of R{total:,.0f} exceeds your single-order limit of R{spend_limit:,.0f}. "
                "Please request approval from your procurement manager."
            )
        return True, ""
