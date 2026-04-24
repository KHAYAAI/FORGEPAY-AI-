"""
Geography configurations for VocalMarket AI markets.

Each GeographyConfig captures everything that differs between markets:
  - Currency and locale for display formatting
  - TTS voice ID (ElevenLabs) for the regional accent
  - Regulatory compliance framework
  - Tax type and rate for order totals
  - Default spend limits in local currency cents

Add a new entry to GEOGRAPHIES to launch in a new market.
The platform picks the right config from the X-Country header forwarded by the gateway.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeographyConfig:
    country_code: str          # ISO 3166-1 alpha-2
    country_name: str
    currency_code: str         # ISO 4217
    currency_symbol: str
    locale: str                # BCP 47 (used for number/date formatting)
    tts_voice_id: str          # ElevenLabs voice ID for regional accent
    compliance_framework: str  # "popia" | "dpdpa" | "hipaa" | "gdpr"
    tax_type: str              # "VAT" | "GST" | "sales_tax" | "none"
    tax_rate: float            # 0.15 = 15%
    # Default single-order spend limit in local currency CENTS before approval required
    default_spend_limit_cents: int

    def format_amount(self, cents: int) -> str:
        """Format a cent value as a human-readable currency string."""
        amount = cents / 100
        return f"{self.currency_symbol}{amount:,.2f}"

    def tax_inclusive_cents(self, net_cents: int) -> int:
        """Return tax-inclusive total from a net amount."""
        return round(net_cents * (1 + self.tax_rate))


# ─── Market configurations ────────────────────────────────────────────────────

SOUTH_AFRICA = GeographyConfig(
    country_code="ZA",
    country_name="South Africa",
    currency_code="ZAR",
    currency_symbol="R",
    locale="en-ZA",
    tts_voice_id="21m00Tcm4TlvDq8ikWAM",   # ElevenLabs Rachel — SA English accent
    compliance_framework="popia",
    tax_type="VAT",
    tax_rate=0.15,
    default_spend_limit_cents=5_000_000,    # R50,000
)

INDIA = GeographyConfig(
    country_code="IN",
    country_name="India",
    currency_code="INR",
    currency_symbol="₹",
    locale="en-IN",
    tts_voice_id="AZnzlk1XvdvUeBnXmlld",   # ElevenLabs Domi — Indian English
    compliance_framework="dpdpa",            # Digital Personal Data Protection Act 2023
    tax_type="GST",
    tax_rate=0.18,                           # Standard GST rate (manufacturing inputs)
    default_spend_limit_cents=500_000_00,    # ₹5,00,000
)

UNITED_STATES = GeographyConfig(
    country_code="US",
    country_name="United States",
    currency_code="USD",
    currency_symbol="$",
    locale="en-US",
    tts_voice_id="EXAVITQu4vr4xnSDxMaL",   # ElevenLabs Bella — US English
    compliance_framework="hipaa",
    tax_type="sales_tax",                    # State-dependent; applied at checkout
    tax_rate=0.0,                            # Calculated per state at order time
    default_spend_limit_cents=5_000_00,      # $5,000
)

EUROPEAN_UNION = GeographyConfig(
    country_code="EU",                       # Used as a catch-all for EU countries
    country_name="European Union",
    currency_code="EUR",
    currency_symbol="€",
    locale="en-EU",
    tts_voice_id="ThT5KcBeYPX3keUQqHPh",   # ElevenLabs Dorothy
    compliance_framework="gdpr",
    tax_type="VAT",
    tax_rate=0.20,                           # Standard EU VAT approximation
    default_spend_limit_cents=5_000_00,      # €5,000
)

# ─── Registry ────────────────────────────────────────────────────────────────

GEOGRAPHIES: dict[str, GeographyConfig] = {
    "ZA": SOUTH_AFRICA,
    "IN": INDIA,
    "US": UNITED_STATES,
    "EU": EUROPEAN_UNION,
    # Individual EU country codes fall back to EU config
    "DE": EUROPEAN_UNION,
    "FR": EUROPEAN_UNION,
    "NL": EUROPEAN_UNION,
}

DEFAULT_GEOGRAPHY = SOUTH_AFRICA


def get_geography(country_code: str | None) -> GeographyConfig:
    """Return the GeographyConfig for a country code, falling back to SA default."""
    if not country_code:
        return DEFAULT_GEOGRAPHY
    return GEOGRAPHIES.get(country_code.upper(), DEFAULT_GEOGRAPHY)
