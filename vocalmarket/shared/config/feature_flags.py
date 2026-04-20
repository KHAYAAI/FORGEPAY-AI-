"""
Feature flags for VocalMarket AI.

AI_LAYER controls which intelligence layer handles requests:
  - "enthusiast"  → V1: direct Enthusiast agent calls (stable, no memory)
  - "hybrid"      → V2: Hermes orchestrates, Enthusiast is a tool provider
"""

from enum import Enum
from pydantic_settings import BaseSettings


class AILayer(str, Enum):
    ENTHUSIAST = "enthusiast"
    HYBRID = "hybrid"


class Vertical(str, Enum):
    GROCERY = "grocery"
    B2B_PROCUREMENT = "b2b_procurement"
    HEALTHCARE = "healthcare"


class FeatureFlags(BaseSettings):
    ai_layer: AILayer = AILayer.ENTHUSIAST

    # Per-vertical overrides — allows gradual V2 rollout
    grocery_ai_layer: AILayer | None = None
    b2b_procurement_ai_layer: AILayer | None = None
    healthcare_ai_layer: AILayer | None = None

    # Voice
    voice_enabled: bool = True
    elevenlabs_voice_id_za: str = "21m00Tcm4TlvDq8ikWAM"  # SA English accent

    # Commerce
    preferred_supplier_boost: float = 1.5  # Ranking multiplier for curated suppliers

    # Healthcare
    healthcare_compliance_mode: str = "popia"  # "popia" | "hipaa"

    class Config:
        env_prefix = "VOCALMARKET_"

    def ai_layer_for(self, vertical: Vertical) -> AILayer:
        """Return the effective AI layer for a given vertical."""
        override = getattr(self, f"{vertical.value}_ai_layer", None)
        return override if override is not None else self.ai_layer


flags = FeatureFlags()
