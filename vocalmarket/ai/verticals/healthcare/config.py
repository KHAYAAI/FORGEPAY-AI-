"""
Healthcare vertical — the most regulated of the three verticals.

Compliance is geography-aware: POPIA (SA), DPDPA (India), HIPAA (US), GDPR (EU).
The active framework is selected from GeographyConfig based on the user's country_code,
which the orchestrator passes via the X-Country-Code header (set by the API gateway
after fetching org-member-context from Enthusiast).
"""

from ..base import BaseVertical
from .compliance import get_compliance_rule, write_phi_audit_log
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
- If the user describes a medical emergency, immediately direct them to emergency services
  (10177 in South Africa, 112 in India/EU, 911 in the United States).
"""

    def extra_tools(self) -> list:
        # Implemented in Phase 2 — placeholder for prescription_tool.py
        return []

    async def pre_order_compliance_check(
        self,
        order_items: list[dict],
        user_id: str,
        country_code: str = "ZA",
        user_context: dict | None = None,
    ) -> tuple[bool, str]:
        """
        Two-stage compliance check:
        1. Geography-specific rule (age, consent, controlled substance restrictions).
        2. Prescription verification for items that require_prescription=True.

        user_context may include: age (int), consent_given (bool).
        country_code drives which ComplianceRule is applied.
        """
        from vocalmarket.shared.config.geographies import get_geography

        geo = get_geography(country_code)
        rule = get_compliance_rule(geo.compliance_framework)

        ctx = {
            "user_id": user_id,
            "country_code": country_code,
            "consent_given": True,   # default; caller should pass real value
            **(user_context or {}),
        }

        decision = rule.check(order_items, ctx)

        if not decision.allowed:
            return False, decision.reason

        # HIPAA / GDPR require an audit record for every PHI access
        if decision.requires_audit_log:
            await write_phi_audit_log(
                user_id=user_id,
                action="pre_order_compliance_check",
                framework=decision.framework,
                details=f"country={country_code} items={len(order_items)}",
            )

        # Stage 2: prescription verification (unchanged across geographies)
        store = await get_prescription_store()
        for item in order_items:
            if item.get("requires_prescription"):
                sku = item.get("sku") or item.get("product_id", "")
                result = await store.verify_for_product(user_id, sku)
                if not result.is_valid:
                    return False, result.reason

        return True, ""
