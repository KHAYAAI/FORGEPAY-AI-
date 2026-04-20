"""
V2 handler: Hermes agent orchestrates with Enthusiast + Medusa + ForgePay as tools.

Hermes maintains long-term user memory across sessions. On each turn it:
  1. Loads the user's semantic memory (preferences, history) from pgvector
  2. Injects vertical context + memory into the system prompt
  3. Runs the Hermes LLM with the full tool set
  4. Executes any tool calls (Enthusiast, Medusa, ForgePay)
  5. Writes updated memory back to the store
"""

from dataclasses import dataclass

import httpx
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI  # Compatible with vLLM's OpenAI endpoint

from vocalmarket.shared.config.feature_flags import Vertical
from vocalmarket.shared.config.verticals import vertical_settings
from ..config import settings
from ..tools.enthusiast_tools import CheckInventoryTool, PlaceOrderTool, SearchProductsTool
from .memory import UserMemoryStore

SYSTEM_PROMPT = """You are VocalMarket AI, a voice-first shopping assistant.

Vertical: {vertical}
User preferences and history:
{user_memory}

Guidelines:
- Be concise — responses will be read aloud via TTS.
- Always check inventory before confirming an order.
- Prefer curated/preferred suppliers when quality and price are comparable.
- For healthcare: never recommend prescription drugs without prescription verification.
- For B2B: always confirm quantities and quote validity before placing orders.
"""


@dataclass
class HermesResult:
    text: str
    conversation_id: str
    products: list[dict] | None = None
    suggested_actions: list[dict] | None = None


class HermesHandler:
    """
    V2 AI handler. Hermes is the conversation brain; Enthusiast/Medusa/ForgePay
    are tools it calls to take grounded actions.
    """

    def __init__(self) -> None:
        self._memory_store = UserMemoryStore(db_url=settings.memory_db_url)

        # Shared HTTP clients passed into tools
        self._enthusiast_http = httpx.AsyncClient(
            base_url=settings.enthusiast_base_url,
            headers={"Authorization": f"Token {settings.enthusiast_api_key}"},
            timeout=30.0,
        )
        self._medusa_http = httpx.AsyncClient(
            base_url="http://medusa:9000",
            timeout=30.0,
        )
        self._forgepay_http = httpx.AsyncClient(
            base_url="http://payments:8001",
            timeout=30.0,
        )

        self._llm = ChatOpenAI(
            model=settings.hermes_model,
            base_url=settings.hermes_base_url or None,
            api_key=settings.hermes_api_key or "none",
            temperature=0.3,
            streaming=True,
        )

    async def chat(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        vertical: Vertical,
    ) -> HermesResult:
        # 1. Load user memory
        memory_summary = await self._memory_store.retrieve_summary(user_id, vertical)

        # 2. Build vertical-specific tool set
        vertical_cfg = getattr(vertical_settings, vertical.value)()
        tools = [
            SearchProductsTool(
                vertical_config=vertical_cfg,
                enthusiast_client=self._enthusiast_http,
            ),
            CheckInventoryTool(medusa_client=self._medusa_http),
            PlaceOrderTool(
                medusa_client=self._medusa_http,
                forgepay_client=self._forgepay_http,
            ),
        ]

        # 3. Build prompt with memory injection
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        chat_history = await self._memory_store.get_recent_messages(conversation_id, limit=10)

        # 4. Run Hermes
        agent = create_tool_calling_agent(self._llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, max_iterations=5)

        result = await executor.ainvoke({
            "input": message,
            "vertical": vertical.value,
            "user_memory": memory_summary,
            "chat_history": chat_history,
        })

        response_text = result["output"]

        # 5. Update long-term memory
        await self._memory_store.record_turn(
            user_id=user_id,
            conversation_id=conversation_id,
            vertical=vertical,
            user_message=message,
            assistant_message=response_text,
        )

        return HermesResult(
            text=response_text,
            conversation_id=conversation_id,
        )

    async def aclose(self) -> None:
        await self._enthusiast_http.aclose()
        await self._medusa_http.aclose()
        await self._forgepay_http.aclose()
        await self._memory_store.aclose()
