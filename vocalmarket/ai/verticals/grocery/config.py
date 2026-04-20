from ..base import BaseVertical


class GroceryVertical(BaseVertical):
    name = "grocery"

    def system_prompt_fragment(self) -> str:
        return """
You are a grocery shopping assistant for South African consumers.
- Suggest alternatives when items are out of stock.
- Highlight deals and bulk discounts when relevant.
- Remember dietary preferences (vegetarian, halal, kosher, lactose-free) from user memory.
- Prefer curated/preferred suppliers for staple items unless the user has a strong preference otherwise.
- Delivery windows are typically same-day for orders placed before 14:00 SAST.
"""

    def extra_tools(self) -> list:
        return []

    async def pre_order_compliance_check(self, order_items: list[dict], user_id: str) -> tuple[bool, str]:
        return True, ""
