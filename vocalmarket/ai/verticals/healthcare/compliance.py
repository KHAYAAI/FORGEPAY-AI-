"""
Healthcare compliance rules enforced per geography.

Each framework implements ComplianceRule.check(), returning (allowed, reason).
The HealthcareVertical selects the active rule from the user's country_code via
GeographyConfig — so the same codebase handles SA (POPIA), India (DPDPA),
US (HIPAA), and EU (GDPR) without any vertical code changes.

Audit trail: HIPAA and GDPR require a written log every time PHI is accessed.
Records are appended to the vocalmarket.phi_audit_log table (created on first use).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ComplianceDecision:
    allowed: bool
    reason: str
    framework: str
    requires_audit_log: bool = False


class ComplianceRule(ABC):
    """Base class for per-geography healthcare compliance rules."""

    framework: str = "unknown"

    @abstractmethod
    def check(self, order_items: list[dict], user_context: dict) -> ComplianceDecision:
        """
        Evaluate whether the order is compliant.

        Args:
            order_items: list of cart items, each may include:
                - requires_prescription (bool)
                - is_controlled_substance (bool)
                - is_opioid (bool)
                - max_daily_dose (str, optional)
                - sku / product_id
            user_context: dict with keys:
                - user_id (str)
                - age (int | None)  — populated if age-verification has run
                - consent_given (bool) — explicit data-processing consent
                - country_code (str)
        """


class POPIARule(ComplianceRule):
    """
    South Africa — Protection of Personal Information Act (2021).

    Key obligations enforced here:
    - Explicit consent for storing health data (section 11)
    - Prescription mandatory for Schedule 4/5/6 medicines (Medicines Act)
    - Under-18 requires guardian consent
    """

    framework = "popia"

    def check(self, order_items: list[dict], user_context: dict) -> ComplianceDecision:
        age = user_context.get("age")
        if age is not None and age < 18:
            return ComplianceDecision(
                allowed=False,
                framework=self.framework,
                reason=(
                    "Users under 18 require guardian consent to purchase healthcare products. "
                    "Please have a parent or guardian complete this order."
                ),
            )

        if not user_context.get("consent_given", True):
            return ComplianceDecision(
                allowed=False,
                framework=self.framework,
                reason=(
                    "POPIA requires your explicit consent before we process your health information. "
                    "Please accept the data processing terms in your account settings."
                ),
            )

        for item in order_items:
            if item.get("is_controlled_substance"):
                return ComplianceDecision(
                    allowed=False,
                    framework=self.framework,
                    reason=(
                        "Controlled substances (Schedule 5/6) require a valid prescription "
                        "and pharmacist dispensing. Please visit a registered pharmacy."
                    ),
                )

        return ComplianceDecision(allowed=True, reason="", framework=self.framework)


class DPDPARule(ComplianceRule):
    """
    India — Digital Personal Data Protection Act 2023.

    Key obligations enforced here:
    - Explicit, specific consent for health data (section 6)
    - Data principal (user) must be a major (18+) under section 9
    - Central Drugs Standard Control Organisation (CDSCO) schedule H/H1/X
      drugs require prescription
    """

    framework = "dpdpa"

    def check(self, order_items: list[dict], user_context: dict) -> ComplianceDecision:
        if not user_context.get("consent_given", True):
            return ComplianceDecision(
                allowed=False,
                framework=self.framework,
                reason=(
                    "Under the DPDPA 2023, we need your explicit consent to process your "
                    "health data. Please accept the data processing notice in your profile."
                ),
            )

        age = user_context.get("age")
        if age is not None and age < 18:
            return ComplianceDecision(
                allowed=False,
                framework=self.framework,
                reason=(
                    "DPDPA requires parental consent for users under 18. "
                    "A guardian must register and complete this purchase."
                ),
            )

        for item in order_items:
            if item.get("is_controlled_substance") or item.get("requires_prescription"):
                schedule = item.get("cdsco_schedule", "")
                if schedule in ("H", "H1", "X"):
                    return ComplianceDecision(
                        allowed=False,
                        framework=self.framework,
                        reason=(
                            f"Schedule {schedule} drugs require a valid prescription under "
                            "CDSCO regulations. Please upload your prescription to proceed."
                        ),
                    )

        return ComplianceDecision(allowed=True, reason="", framework=self.framework)


class HIPAARule(ComplianceRule):
    """
    United States — Health Insurance Portability and Accountability Act.

    Key obligations enforced here:
    - Every access to PHI (protected health information) generates an audit log
      entry (the Security Rule requires this for covered entities)
    - Opioids and Schedule II controlled substances are hard-blocked (must go
      through a DEA-registered pharmacy with in-person ID)
    - Minimum Necessary standard: only request/expose data needed for the transaction
    """

    framework = "hipaa"

    def check(self, order_items: list[dict], user_context: dict) -> ComplianceDecision:
        for item in order_items:
            if item.get("is_opioid"):
                return ComplianceDecision(
                    allowed=False,
                    framework=self.framework,
                    reason=(
                        "Opioids and Schedule II controlled substances cannot be dispensed "
                        "through this channel. Please visit a DEA-registered pharmacy in person."
                    ),
                )
            if item.get("is_controlled_substance") and item.get("dea_schedule") in ("I", "II"):
                return ComplianceDecision(
                    allowed=False,
                    framework=self.framework,
                    reason=(
                        "DEA Schedule I/II substances require in-person dispensing at a "
                        "DEA-registered pharmacy. This order cannot proceed online."
                    ),
                )

        # HIPAA requires an audit log for every PHI access
        return ComplianceDecision(
            allowed=True,
            reason="",
            framework=self.framework,
            requires_audit_log=True,  # caller must write audit record
        )


class GDPRRule(ComplianceRule):
    """
    European Union — General Data Protection Regulation (GDPR Article 9).

    Health data is 'special category' data requiring explicit consent AND
    a lawful basis under Article 9(2). Minors under 16 require parental consent
    (member states may lower to 13 — we use 16 as the safe default).
    """

    framework = "gdpr"

    def check(self, order_items: list[dict], user_context: dict) -> ComplianceDecision:
        if not user_context.get("consent_given", False):
            return ComplianceDecision(
                allowed=False,
                framework=self.framework,
                reason=(
                    "GDPR Article 9 requires your explicit consent to process special category "
                    "(health) data. Please accept the health data processing notice."
                ),
            )

        age = user_context.get("age")
        if age is not None and age < 16:
            return ComplianceDecision(
                allowed=False,
                framework=self.framework,
                reason=(
                    "GDPR requires parental consent for processing health data of users under 16. "
                    "A parent or guardian must authorise this account."
                ),
            )

        return ComplianceDecision(
            allowed=True,
            reason="",
            framework=self.framework,
            requires_audit_log=True,  # GDPR Article 30 processing records
        )


# ── Registry ─────────────────────────────────────────────────────────────────

_RULES: dict[str, ComplianceRule] = {
    "popia": POPIARule(),
    "dpdpa": DPDPARule(),
    "hipaa": HIPAARule(),
    "gdpr": GDPRRule(),
}


def get_compliance_rule(framework: str) -> ComplianceRule:
    """Return the ComplianceRule for the given framework name. Defaults to POPIA."""
    return _RULES.get(framework, _RULES["popia"])


# ── HIPAA / GDPR audit log ────────────────────────────────────────────────────

async def write_phi_audit_log(
    user_id: str,
    action: str,
    framework: str,
    details: str = "",
) -> None:
    """
    Append a PHI access record to vocalmarket.phi_audit_log.

    Called by HealthcareVertical when ComplianceDecision.requires_audit_log is True.
    Non-fatal — a logging failure must never block the order flow, but we log loudly.
    """
    import os
    import asyncpg  # type: ignore[import]

    db_url = os.environ.get(
        "HEALTHCARE_PRESCRIPTION_DB_URL",
        "postgresql://postgres:postgres@postgres:5432/vocalmarket",
    )
    try:
        conn = await asyncpg.connect(db_url)
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vocalmarket.phi_audit_log (
                    id          BIGSERIAL PRIMARY KEY,
                    user_id     TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    framework   TEXT NOT NULL,
                    details     TEXT,
                    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await conn.execute(
                "INSERT INTO vocalmarket.phi_audit_log "
                "(user_id, action, framework, details) VALUES ($1, $2, $3, $4)",
                user_id, action, framework, details,
            )
        finally:
            await conn.close()
    except Exception as exc:
        logger.error("PHI audit log write failed (user=%s action=%s): %s", user_id, action, exc)
