"""
Healthcare vertical — the most regulated of the three verticals.

Compliance scope: POPIA (SA) with HIPAA-compatible patterns.
Extra tools: prescription verification, appointment booking.
"""

from ..base import BaseVertical
from .prescription_store import get_prescription_store


class HealthcareVertical(BaseVertical):
    name = "healthcare"

    def system_prompt_fragment(self) -> str:
        return """
You are assisting with healthcare and pharmacy needs.
Rules you MUST follow without exception:
- NEVER suggest or dispense prescription medication without a verified prescription on file.
- Always recommend the user consult a licensed healthcare provider for medical advice.
- For over-the-counter products, you may suggest based on symptoms but include a disclaimer.
- Do NOT store or repeat sensitive health information beyond what is necessary for the current order.
- If the user describes a medical emergency, immediately direct them to emergency services (10177 in SA).
"""

    def extra_tools(self) -> list:
        # Implemented in Phase 2 — placeholder for prescription_tool.py
        return []

    async def pre_order_compliance_check(self, order_items: list[dict], user_id: str) -> tuple[bool, str]:
        """Block prescription items if no verified prescription exists."""
        store = await get_prescription_store()
        for item in order_items:
            if item.get("requires_prescription"):
                sku = item.get("sku") or item.get("product_id", "")
                result = await store.verify_for_product(user_id, sku)
                if not result.is_valid:
                    return False, result.reason
        return True, ""
