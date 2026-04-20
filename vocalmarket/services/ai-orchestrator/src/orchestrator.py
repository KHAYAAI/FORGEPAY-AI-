"""
Core AI Orchestrator.

Routes each conversation turn to either:
  - V1: EnthusiastHandler (direct Enthusiast agent call)
  - V2: HermesHandler (Hermes orchestrates with Enthusiast as a tool)

The active path is controlled by the VOCALMARKET_AI_LAYER feature flag, which
can be overridden per-vertical for gradual V2 rollout.
"""

from dataclasses import dataclass

from opentelemetry import trace

from vocalmarket.shared.config.feature_flags import AILayer, Vertical, flags
from .v1.enthusiast_handler import EnthusiastHandler
from .v2.hermes_handler import HermesHandler

tracer = trace.get_tracer(__name__)


@dataclass
class ConversationTurn:
    user_id: str
    message: str
    vertical: Vertical
    conversation_id: str
    data_set_id: str | None = None  # Overrides vertical default if set


@dataclass
class OrchestratorResponse:
    text: str
    conversation_id: str
    products: list[dict] | None = None
    suggested_actions: list[dict] | None = None
    memory_updated: bool = False  # True only in V2


class AIOrchestrator:
    """
    Single entry point for all AI conversation turns.

    Usage:
        orchestrator = AIOrchestrator()
        response = await orchestrator.process(turn)
    """

    def __init__(self) -> None:
        self._enthusiast = EnthusiastHandler()
        self._hermes: HermesHandler | None = None  # Lazy-init: only in V2

    async def process(self, turn: ConversationTurn) -> OrchestratorResponse:
        with tracer.start_as_current_span("orchestrator.process") as span:
            span.set_attribute("vertical", turn.vertical.value)
            span.set_attribute("user_id", turn.user_id)

            active_layer = flags.ai_layer_for(turn.vertical)
            span.set_attribute("ai_layer", active_layer.value)

            if active_layer == AILayer.HYBRID:
                return await self._process_hybrid(turn)
            return await self._process_enthusiast(turn)

    async def _process_enthusiast(self, turn: ConversationTurn) -> OrchestratorResponse:
        """V1 path: direct call to Enthusiast's conversation API."""
        result = await self._enthusiast.chat(
            conversation_id=turn.conversation_id,
            message=turn.message,
            vertical=turn.vertical,
            data_set_id=turn.data_set_id,
        )
        return OrchestratorResponse(
            text=result.text,
            conversation_id=result.conversation_id,
            products=result.products,
            suggested_actions=result.suggested_actions,
        )

    async def _process_hybrid(self, turn: ConversationTurn) -> OrchestratorResponse:
        """V2 path: Hermes orchestrates with Enthusiast + Medusa + ForgePay as tools."""
        if self._hermes is None:
            self._hermes = HermesHandler()

        result = await self._hermes.chat(
            user_id=turn.user_id,
            conversation_id=turn.conversation_id,
            message=turn.message,
            vertical=turn.vertical,
        )
        return OrchestratorResponse(
            text=result.text,
            conversation_id=result.conversation_id,
            products=result.products,
            suggested_actions=result.suggested_actions,
            memory_updated=True,
        )
