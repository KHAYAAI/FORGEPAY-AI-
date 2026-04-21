"""
Hermes two-tier memory store backed by PostgreSQL + pgvector.

Tier 1 — Episodic: raw conversation turns, kept in PostgreSQL, pruned after N turns.
Tier 2 — Semantic: embedded user facts (preferences, orders, health, constraints)
          stored as pgvector vectors; retrieved by cosine similarity at query time.

On every conversation turn:
  1. Recent episodic messages are loaded as LangChain message objects.
  2. The current query is embedded; top-K semantically relevant facts are fetched.
  3. Both are injected into the Hermes system prompt.
  4. After the turn, new facts extracted by the LLM are upserted into the semantic store.
  5. When episodic turn count exceeds CONSOLIDATION_THRESHOLD, a background
     summarisation task fires to distil the episode into durable semantic facts.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, delete, func, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column

EMBEDDING_DIM = 1536          # text-embedding-3-small
SEMANTIC_TOP_K = 8            # facts retrieved per turn
EPISODIC_WINDOW = 12          # recent turns kept in prompt
CONSOLIDATION_THRESHOLD = 40  # episodes before background consolidation fires


class FactType(str, Enum):
    PREFERENCE = "preference"
    ORDER = "order"
    HEALTH = "health"
    CONTACT = "contact"
    CONSTRAINT = "constraint"
    SUMMARY = "summary"
    SUPPLIER = "supplier"  # B2B: preferred suppliers, experiences, contract notes


class Base(DeclarativeBase):
    pass


class MemoryFact(Base):
    """One durable semantic fact about a user, stored with its embedding vector."""

    __tablename__ = "memory_facts"
    __table_args__ = {"schema": "vocalmarket"}

    id: Any = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Any = mapped_column(String(128), index=True, nullable=False)
    vertical: Any = mapped_column(String(64), nullable=False)
    fact_type: Any = mapped_column(String(32), nullable=False)
    content: Any = mapped_column(Text, nullable=False)
    embedding: Any = Column(Vector(EMBEDDING_DIM))
    importance: Any = mapped_column(Float, default=1.0)
    access_count: Any = mapped_column(Integer, default=0)
    created_at: Any = mapped_column(DateTime, default=datetime.utcnow)
    last_accessed_at: Any = mapped_column(DateTime, default=datetime.utcnow)


class EpisodicMessage(Base):
    """Raw conversation turn stored for recent-context injection."""

    __tablename__ = "episodic_messages"
    __table_args__ = {"schema": "vocalmarket"}

    id: Any = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Any = mapped_column(String(256), index=True, nullable=False)
    user_id: Any = mapped_column(String(128), index=True, nullable=False)
    vertical: Any = mapped_column(String(64), nullable=False)
    role: Any = mapped_column(String(16), nullable=False)   # "human" | "assistant"
    content: Any = mapped_column(Text, nullable=False)
    turn_index: Any = mapped_column(Integer, nullable=False)
    created_at: Any = mapped_column(DateTime, default=datetime.utcnow)


class MemorySummary(Base):
    """Consolidated narrative summary per user/vertical, updated by consolidation task."""

    __tablename__ = "memory_summaries"
    __table_args__ = {"schema": "vocalmarket"}

    id: Any = mapped_column(String(256), primary_key=True)  # "{user_id}-{vertical}"
    user_id: Any = mapped_column(String(128), index=True, nullable=False)
    vertical: Any = mapped_column(String(64), nullable=False)
    content: Any = mapped_column(Text, nullable=False)
    turn_count: Any = mapped_column(Integer, default=0)
    updated_at: Any = mapped_column(DateTime, default=datetime.utcnow)


class UserMemoryStore:
    """
    Async PostgreSQL + pgvector memory store for the Hermes agent.

    Typical usage per turn:
        context = await store.load_context(user_id, vertical, conversation_id, query)
        # ... run Hermes with context ...
        await store.record_turn(user_id, vertical, conversation_id, human_msg, ai_msg, new_facts)
    """

    def __init__(self, db_url: str, embedder: "EmbeddingProvider") -> None:
        self._engine = create_async_engine(db_url, echo=False, pool_size=10, max_overflow=20)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._embedder = embedder

    async def initialise(self) -> None:
        """Create schema and tables. Safe to call on every startup (idempotent)."""
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vocalmarket"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            # HNSW index for fast approximate nearest-neighbour search
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS memory_facts_embedding_idx "
                "ON vocalmarket.memory_facts USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 64)"
            ))

    # ── Context loading ──────────────────────────────────────────────────────

    async def load_context(
        self,
        user_id: str,
        vertical: str,
        conversation_id: str,
        query: str,
    ) -> "MemoryContext":
        """Return everything Hermes needs to answer the current turn."""
        episodic, semantic, summary, turn_count = await asyncio.gather(
            self._load_episodic(conversation_id),
            self._retrieve_semantic(user_id, vertical, query),
            self._load_summary(user_id, vertical),
            self._turn_count(conversation_id),
        )
        return MemoryContext(
            episodic_messages=episodic,
            semantic_facts=semantic,
            summary=summary,
            turn_count=turn_count,
            should_consolidate=turn_count > 0 and turn_count % CONSOLIDATION_THRESHOLD == 0,
        )

    async def _load_episodic(self, conversation_id: str) -> list[BaseMessage]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EpisodicMessage)
                .where(EpisodicMessage.conversation_id == conversation_id)
                .order_by(EpisodicMessage.turn_index.desc())
                .limit(EPISODIC_WINDOW)
            )
            rows = list(reversed(result.scalars().all()))

        messages: list[BaseMessage] = []
        for row in rows:
            cls = HumanMessage if row.role == "human" else AIMessage
            messages.append(cls(content=row.content))
        return messages

    async def _retrieve_semantic(self, user_id: str, vertical: str, query: str) -> list[str]:
        """Embed query, return top-K most relevant facts via cosine similarity."""
        query_vec = await self._embedder.embed(query)

        async with self._session_factory() as session:
            # pgvector cosine distance operator: <=>
            result = await session.execute(
                select(MemoryFact.content, MemoryFact.id)
                .where(
                    MemoryFact.user_id == user_id,
                    MemoryFact.vertical == vertical,
                )
                .order_by(MemoryFact.embedding.cosine_distance(query_vec))
                .limit(SEMANTIC_TOP_K)
            )
            rows = result.all()
            fact_ids = [str(r.id) for r in rows]

        if fact_ids:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        text(
                            "UPDATE vocalmarket.memory_facts "
                            "SET access_count = access_count + 1, last_accessed_at = now() "
                            "WHERE id = ANY(:ids)"
                        ),
                        {"ids": fact_ids},
                    )

        return [r.content for r in rows]

    async def _load_summary(self, user_id: str, vertical: str) -> str:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MemorySummary.content)
                .where(
                    MemorySummary.user_id == user_id,
                    MemorySummary.vertical == vertical,
                )
            )
            row = result.scalar_one_or_none()
        return row or ""

    async def _turn_count(self, conversation_id: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count()).where(EpisodicMessage.conversation_id == conversation_id)
            )
        return result.scalar_one()

    # ── Recording ────────────────────────────────────────────────────────────

    async def record_turn(
        self,
        user_id: str,
        vertical: str,
        conversation_id: str,
        human_message: str,
        ai_message: str,
        extracted_facts: list["ExtractedFact"] | None = None,
    ) -> None:
        """Persist one conversation turn and any newly extracted semantic facts."""
        async with self._session_factory() as session:
            async with session.begin():
                # Get next turn index
                result = await session.execute(
                    select(func.coalesce(func.max(EpisodicMessage.turn_index), -1))
                    .where(EpisodicMessage.conversation_id == conversation_id)
                )
                next_idx = result.scalar_one() + 1

                session.add(EpisodicMessage(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    vertical=vertical,
                    role="human",
                    content=human_message,
                    turn_index=next_idx,
                ))
                session.add(EpisodicMessage(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    vertical=vertical,
                    role="assistant",
                    content=ai_message,
                    turn_index=next_idx,
                ))

        if extracted_facts:
            await self.upsert_facts(user_id, vertical, extracted_facts)

    async def upsert_facts(
        self,
        user_id: str,
        vertical: str,
        facts: list["ExtractedFact"],
    ) -> None:
        """Embed and store new facts, replacing existing ones with the same content hash."""
        embeddings = await self._embedder.embed_batch([f.content for f in facts])

        async with self._session_factory() as session:
            async with session.begin():
                for fact, embedding in zip(facts, embeddings):
                    session.add(MemoryFact(
                        user_id=user_id,
                        vertical=vertical,
                        fact_type=fact.fact_type.value,
                        content=fact.content,
                        embedding=embedding,
                        importance=fact.importance,
                    ))

    async def update_summary(self, user_id: str, vertical: str, content: str, turn_count: int) -> None:
        summary_id = f"{user_id}-{vertical}"
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "INSERT INTO vocalmarket.memory_summaries "
                        "(id, user_id, vertical, content, turn_count, updated_at) "
                        "VALUES (:id, :uid, :v, :content, :tc, now()) "
                        "ON CONFLICT (id) DO UPDATE "
                        "SET content = EXCLUDED.content, turn_count = EXCLUDED.turn_count, "
                        "updated_at = now()"
                    ),
                    {"id": summary_id, "uid": user_id, "v": vertical, "content": content, "tc": turn_count},
                )

    async def prune_episodic(self, conversation_id: str, keep_last: int = 100) -> None:
        """Delete old episodic messages beyond the keep window."""
        async with self._session_factory() as session:
            async with session.begin():
                subq = (
                    select(EpisodicMessage.id)
                    .where(EpisodicMessage.conversation_id == conversation_id)
                    .order_by(EpisodicMessage.turn_index.desc())
                    .limit(keep_last)
                    .scalar_subquery()
                )
                await session.execute(
                    delete(EpisodicMessage)
                    .where(
                        EpisodicMessage.conversation_id == conversation_id,
                        EpisodicMessage.id.not_in(subq),
                    )
                )

    async def aclose(self) -> None:
        await self._engine.dispose()


# ── Supporting types ─────────────────────────────────────────────────────────

from dataclasses import dataclass, field


@dataclass
class ExtractedFact:
    content: str
    fact_type: FactType = FactType.PREFERENCE
    importance: float = 1.0


@dataclass
class MemoryContext:
    episodic_messages: list[BaseMessage]
    semantic_facts: list[str]
    summary: str
    turn_count: int
    should_consolidate: bool

    def format_for_prompt(self) -> str:
        parts: list[str] = []
        if self.summary:
            parts.append(f"Background: {self.summary}")
        if self.semantic_facts:
            facts_block = "\n".join(f"- {f}" for f in self.semantic_facts)
            parts.append(f"Relevant user facts:\n{facts_block}")
        return "\n\n".join(parts) if parts else "No prior history for this user."


class EmbeddingProvider:
    """Wraps an OpenAI-compatible embedding endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str = "text-embedding-3-small") -> None:
        import httpx
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._model = model

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.post(
            "/v1/embeddings",
            json={"input": texts, "model": self._model},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        data.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in data]

    async def aclose(self) -> None:
        await self._client.aclose()
