"""
HermesAgent — the V2 conversation brain.

Wraps the full Hermes pipeline:
  1. Load memory context (episodic + semantic retrieval)
  2. Load user skills from registry
  3. Build dynamic tool set (base + vertical + skills)
  4. Run LangChain tool-calling agent with Hermes LLM
  5. Extract new facts from the exchange
  6. Record turn + upsert facts
  7. Fire consolidation if threshold crossed (non-blocking)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from vocalmarket.shared.config.feature_flags import Vertical
from vocalmarket.shared.config.verticals import vertical_settings
from ..verticals.base import BaseVertical
from ..verticals.grocery.config import GroceryVertical
from ..verticals.b2b_procurement.config import B2BProcurementVertical
from ..verticals.healthcare.config import HealthcareVertical
from .memory.consolidator import MemoryConsolidator
from .memory.extractor import FactExtractor
from .memory.store import EmbeddingProvider, UserMemoryStore
from .skills.registry import SkillRegistry

VERTICAL_CLASSES: dict[str, type[BaseVertical]] = {
    "grocery": GroceryVertical,
    "b2b_procurement": B2BProcurementVertical,
    "healthcare": HealthcareVertical,
}

SYSTEM_BASE = """You are VocalMarket AI, a voice-first commerce assistant for South African users.
Vertical: {vertical}

{memory_context}

{vertical_guidance}

Important voice-channel rules:
- Keep responses short and clear — they will be read aloud via TTS.
- Numbers and prices must be spoken naturally (e.g. "twelve rand fifty" not "R12.50").
- Never output markdown, bullet points, or lists in your final answer — use natural speech.
- Confirm orders by repeating the key details before calling place_order.
"""


@dataclass
class HermesResponse:
    text: str
    conversation_id: str
    products: list[dict] | None = None
    suggested_actions: list[dict] | None = None


class HermesAgent:
    """
    Stateless per-request agent. All state lives in the memory store.
    One instance is shared across requests — HTTP clients are reused.
    """

    def __init__(
        self,
        memory_store: UserMemoryStore,
        embedder: EmbeddingProvider,
        skill_registry: SkillRegistry,
        llm: ChatOpenAI,
        extract_llm: ChatOpenAI,
        enthusiast_http: httpx.AsyncClient,
        medusa_http: httpx.AsyncClient,
        forgepay_http: httpx.AsyncClient,
    ) -> None:
        self._memory = memory_store
        self._skill_registry = skill_registry
        self._extractor = FactExtractor(extract_llm)
        self._consolidator = MemoryConsolidator(memory_store, extract_llm)
        self._llm = llm
        self._enthusiast_http = enthusiast_http
        self._medusa_http = medusa_http
        self._forgepay_http = forgepay_http

    async def chat(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        vertical: Vertical,
    ) -> HermesResponse:
        vertical_str = vertical.value
        vertical_cfg = getattr(vertical_settings, vertical_str)()
        vertical_obj = VERTICAL_CLASSES[vertical_str]()

        # 1. Load memory context
        context = await self._memory.load_context(user_id, vertical_str, conversation_id, message)

        # 2. Load user skills
        skill_tools = await self._skill_registry.load_skills(user_id, vertical_str)

        # 3. Build tool set
        from vocalmarket.services.ai_orchestrator.src.tools.enthusiast_tools import (
            CheckInventoryTool,
            PlaceOrderTool,
            SearchProductsTool,
        )
        base_tools = [
            SearchProductsTool(vertical_config=vertical_cfg, enthusiast_client=self._enthusiast_http),
            CheckInventoryTool(medusa_client=self._medusa_http),
            PlaceOrderTool(medusa_client=self._medusa_http, forgepay_client=self._forgepay_http),
        ]
        extra_tools = vertical_obj.extra_tools()
        all_tools = base_tools + extra_tools + skill_tools

        # 4. Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_BASE),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(self._llm, all_tools, prompt)
        executor = AgentExecutor(agent=agent, tools=all_tools, max_iterations=6, handle_parsing_errors=True)

        result = await executor.ainvoke({
            "input": message,
            "vertical": vertical_str,
            "memory_context": context.format_for_prompt(),
            "vertical_guidance": vertical_obj.system_prompt_fragment(),
            "chat_history": context.episodic_messages,
        })
        response_text: str = result["output"]

        # 5. Extract facts and record turn (fire-and-forget)
        asyncio.create_task(self._post_turn(
            user_id=user_id,
            vertical=vertical_str,
            conversation_id=conversation_id,
            human_message=message,
            ai_message=response_text,
            context=context,
        ))

        return HermesResponse(text=response_text, conversation_id=conversation_id)

    async def _post_turn(
        self,
        user_id: str,
        vertical: str,
        conversation_id: str,
        human_message: str,
        ai_message: str,
        context,
    ) -> None:
        """Non-blocking post-processing: fact extraction + optional consolidation."""
        facts = await self._extractor.extract(human_message, ai_message, vertical)
        await self._memory.record_turn(
            user_id=user_id,
            vertical=vertical,
            conversation_id=conversation_id,
            human_message=human_message,
            ai_message=ai_message,
            extracted_facts=facts or None,
        )
        if context.should_consolidate:
            await self._consolidator.consolidate(user_id, vertical, conversation_id, context)
