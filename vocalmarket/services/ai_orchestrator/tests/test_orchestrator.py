"""
Tests for AIOrchestrator routing (vocalmarket/services/ai_orchestrator/src/orchestrator.py).

The V2 path pulls in a heavy transitive dependency chain (langchain, sqlalchemy,
the Hermes agent) that isn't relevant to what this module actually does — decide
which handler receives a turn. We stub v1.enthusiast_handler and v2.hermes_handler
in sys.modules before importing orchestrator.py so these are true unit tests of
the routing/feature-flag logic, independent of whichever LLM stack V2 happens to
be wired to.

Key paths covered:
  - Default flag (enthusiast) routes to EnthusiastHandler
  - Global hybrid flag routes to HermesHandler
  - Per-vertical override takes precedence over the global flag
  - Hermes handler is lazily constructed (only on first hybrid call)
  - Response fields are mapped correctly for both paths
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest


def _install_stub_handlers():
    """
    Replace the real v1/v2 handler modules with lightweight stubs in sys.modules
    so `import orchestrator` never touches langchain/sqlalchemy/httpx clients.
    """
    v1_module = types.ModuleType("vocalmarket.services.ai_orchestrator.src.v1.enthusiast_handler")
    v1_module.EnthusiastHandler = MagicMock(name="EnthusiastHandlerClass")
    sys.modules["vocalmarket.services.ai_orchestrator.src.v1.enthusiast_handler"] = v1_module

    v2_module = types.ModuleType("vocalmarket.services.ai_orchestrator.src.v2.hermes_handler")
    v2_module.HermesHandler = MagicMock(name="HermesHandlerClass")
    sys.modules["vocalmarket.services.ai_orchestrator.src.v2.hermes_handler"] = v2_module

    return v1_module.EnthusiastHandler, v2_module.HermesHandler


EnthusiastHandlerClass, HermesHandlerClass = _install_stub_handlers()

from vocalmarket.services.ai_orchestrator.src.orchestrator import (  # noqa: E402
    AIOrchestrator,
    ConversationTurn,
)
from vocalmarket.shared.config.feature_flags import AILayer, Vertical, flags  # noqa: E402


@dataclass
class _FakeResult:
    text: str
    conversation_id: str
    products: list | None = None
    suggested_actions: list | None = None


@pytest.fixture(autouse=True)
def _reset_flags():
    """Every test starts from the default (enthusiast, no per-vertical overrides)."""
    flags.ai_layer = AILayer.ENTHUSIAST
    flags.grocery_ai_layer = None
    flags.b2b_procurement_ai_layer = None
    flags.healthcare_ai_layer = None
    yield
    flags.ai_layer = AILayer.ENTHUSIAST
    flags.grocery_ai_layer = None
    flags.b2b_procurement_ai_layer = None
    flags.healthcare_ai_layer = None


@pytest.fixture()
def orchestrator():
    orch = AIOrchestrator()
    orch._enthusiast = MagicMock()
    orch._enthusiast.chat = AsyncMock(
        return_value=_FakeResult(text="v1 reply", conversation_id="conv-1", products=[{"id": "p1"}])
    )
    return orch


def _turn(vertical: Vertical = Vertical.GROCERY, **overrides) -> ConversationTurn:
    defaults = dict(
        user_id="user-1",
        message="find me milk",
        vertical=vertical,
        conversation_id="conv-1",
    )
    defaults.update(overrides)
    return ConversationTurn(**defaults)


class TestV1Routing:
    """Default feature flag state — everything goes through Enthusiast directly."""

    @pytest.mark.asyncio
    async def test_default_flag_routes_to_enthusiast(self, orchestrator):
        response = await orchestrator.process(_turn())

        orchestrator._enthusiast.chat.assert_awaited_once_with(
            conversation_id="conv-1",
            message="find me milk",
            vertical=Vertical.GROCERY,
            data_set_id=None,
        )
        assert response.text == "v1 reply"
        assert response.conversation_id == "conv-1"
        assert response.products == [{"id": "p1"}]
        assert response.memory_updated is False

    @pytest.mark.asyncio
    async def test_hermes_handler_never_constructed_on_v1_path(self, orchestrator):
        await orchestrator.process(_turn())
        assert orchestrator._hermes is None


class TestV2Routing:
    """Hybrid flag — Hermes orchestrates and memory_updated is always True."""

    @pytest.mark.asyncio
    async def test_global_hybrid_flag_routes_to_hermes(self, orchestrator):
        flags.ai_layer = AILayer.HYBRID
        fake_hermes = MagicMock()
        fake_hermes.chat = AsyncMock(
            return_value=_FakeResult(text="hermes reply", conversation_id="conv-1")
        )
        HermesHandlerClass.return_value = fake_hermes

        response = await orchestrator.process(_turn())

        orchestrator._enthusiast.chat.assert_not_awaited()
        fake_hermes.chat.assert_awaited_once_with(
            user_id="user-1",
            conversation_id="conv-1",
            message="find me milk",
            vertical=Vertical.GROCERY,
            org_id=None,
        )
        assert response.text == "hermes reply"
        assert response.memory_updated is True

    @pytest.mark.asyncio
    async def test_hermes_handler_constructed_lazily_once(self, orchestrator):
        flags.ai_layer = AILayer.HYBRID
        fake_hermes = MagicMock()
        fake_hermes.chat = AsyncMock(return_value=_FakeResult(text="ok", conversation_id="conv-1"))
        HermesHandlerClass.reset_mock(return_value=True)
        HermesHandlerClass.return_value = fake_hermes

        await orchestrator.process(_turn())
        await orchestrator.process(_turn(conversation_id="conv-2"))

        # Constructed once, reused for the second turn.
        assert HermesHandlerClass.call_count == 1

    @pytest.mark.asyncio
    async def test_org_id_forwarded_for_b2b(self, orchestrator):
        flags.ai_layer = AILayer.HYBRID
        fake_hermes = MagicMock()
        fake_hermes.chat = AsyncMock(return_value=_FakeResult(text="ok", conversation_id="conv-1"))
        HermesHandlerClass.return_value = fake_hermes

        await orchestrator.process(_turn(vertical=Vertical.B2B_PROCUREMENT, org_id="org-42"))

        fake_hermes.chat.assert_awaited_once_with(
            user_id="user-1",
            conversation_id="conv-1",
            message="find me milk",
            vertical=Vertical.B2B_PROCUREMENT,
            org_id="org-42",
        )


class TestPerVerticalOverride:
    """Per-vertical flags take precedence over the global default."""

    @pytest.mark.asyncio
    async def test_vertical_override_wins_over_global_default(self, orchestrator):
        # Global stays "enthusiast", but grocery is opted into hybrid.
        flags.grocery_ai_layer = AILayer.HYBRID
        fake_hermes = MagicMock()
        fake_hermes.chat = AsyncMock(return_value=_FakeResult(text="ok", conversation_id="conv-1"))
        HermesHandlerClass.return_value = fake_hermes

        await orchestrator.process(_turn(vertical=Vertical.GROCERY))

        fake_hermes.chat.assert_awaited_once()
        orchestrator._enthusiast.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_other_verticals_unaffected_by_grocery_override(self, orchestrator):
        flags.grocery_ai_layer = AILayer.HYBRID

        response = await orchestrator.process(_turn(vertical=Vertical.HEALTHCARE))

        orchestrator._enthusiast.chat.assert_awaited_once()
        assert response.memory_updated is False

    @pytest.mark.asyncio
    async def test_vertical_override_can_downgrade_from_global_hybrid(self, orchestrator):
        flags.ai_layer = AILayer.HYBRID
        flags.healthcare_ai_layer = AILayer.ENTHUSIAST

        response = await orchestrator.process(_turn(vertical=Vertical.HEALTHCARE))

        orchestrator._enthusiast.chat.assert_awaited_once()
        assert response.memory_updated is False
