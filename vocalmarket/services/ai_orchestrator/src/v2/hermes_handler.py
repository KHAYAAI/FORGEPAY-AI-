"""
V2 handler: bootstraps the HermesAgent and delegates each turn to it.
"""

from __future__ import annotations

import httpx
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vocalmarket.ai.hermes.agent import HermesAgent, HermesResponse
from vocalmarket.ai.hermes.memory.store import EmbeddingProvider, UserMemoryStore
from vocalmarket.ai.hermes.skills.registry import SkillRegistry
from vocalmarket.shared.config.feature_flags import Vertical
from ..config import settings


class HermesHandler:
    """
    Singleton wrapper around HermesAgent.
    Owns all long-lived HTTP clients and the memory store connection pool.
    """

    def __init__(self) -> None:
        self._embedder = EmbeddingProvider(
            base_url=settings.hermes_base_url or "https://api.openai.com",
            api_key=settings.hermes_api_key,
            model="text-embedding-3-small",
        )
        self._memory = UserMemoryStore(
            db_url=settings.memory_db_url,
            embedder=self._embedder,
        )
        engine = create_async_engine(settings.memory_db_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        self._skill_registry = SkillRegistry(session_factory)

        # Primary LLM — Hermes-3 via vLLM (OpenAI-compatible endpoint)
        self._llm = ChatOpenAI(
            model=settings.hermes_model,
            base_url=settings.hermes_base_url or None,
            api_key=settings.hermes_api_key or "none",
            temperature=0.3,
            streaming=False,
        )
        # Smaller model for fact extraction / consolidation (cheaper)
        self._extract_llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.hermes_api_key or "none",
            temperature=0.0,
        )

        self._enthusiast_http = httpx.AsyncClient(
            base_url=settings.enthusiast_base_url,
            headers={"Authorization": f"Token {settings.enthusiast_api_key}"},
            timeout=30.0,
        )
        self._medusa_http = httpx.AsyncClient(base_url="http://medusa:9000", timeout=30.0)
        self._forgepay_http = httpx.AsyncClient(base_url="http://payments:8001", timeout=30.0)

        self._agent = HermesAgent(
            memory_store=self._memory,
            embedder=self._embedder,
            skill_registry=self._skill_registry,
            llm=self._llm,
            extract_llm=self._extract_llm,
            enthusiast_http=self._enthusiast_http,
            medusa_http=self._medusa_http,
            forgepay_http=self._forgepay_http,
        )

    async def initialise(self) -> None:
        """Must be called once at startup to create DB schema."""
        await self._memory.initialise()

    async def chat(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        vertical: Vertical,
    ) -> HermesResponse:
        return await self._agent.chat(user_id, conversation_id, message, vertical)

    async def aclose(self) -> None:
        await self._memory.aclose()
        await self._embedder.aclose()
        await self._enthusiast_http.aclose()
        await self._medusa_http.aclose()
        await self._forgepay_http.aclose()
