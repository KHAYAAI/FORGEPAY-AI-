"""
Long-term user memory store for Hermes (V2).

Uses PostgreSQL + pgvector (same instance as Enthusiast, separate schema).
Two memory types:
  - Episodic: recent conversation messages (Redis TTL cache → PostgreSQL)
  - Semantic: user preferences, order history, personalization vectors (pgvector)
"""

import json
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import Column, DateTime, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column

from vocalmarket.shared.config.feature_flags import Vertical


class Base(DeclarativeBase):
    pass


class UserMemoryRecord(Base):
    __tablename__ = "vocalmarket_user_memory"
    __table_args__ = {"schema": "vocalmarket"}

    id: str = mapped_column(String, primary_key=True)
    user_id: str = mapped_column(String, index=True)
    vertical: str = mapped_column(String)
    memory_type: str = mapped_column(String)  # "preference" | "order" | "health" | "summary"
    content: str = mapped_column(Text)
    created_at: datetime = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: datetime = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConversationMessage(Base):
    __tablename__ = "vocalmarket_conversation_messages"
    __table_args__ = {"schema": "vocalmarket"}

    id: str = mapped_column(String, primary_key=True)
    conversation_id: str = mapped_column(String, index=True)
    role: str = mapped_column(String)  # "human" | "assistant"
    content: str = mapped_column(Text)
    created_at: datetime = mapped_column(DateTime, default=datetime.utcnow)


class UserMemoryStore:
    """
    Manages two memory tiers:
      - Recent messages: PostgreSQL (last N turns per conversation)
      - Long-term preferences: PostgreSQL free-text + (future) pgvector embeddings
    """

    def __init__(self, db_url: str) -> None:
        self._engine = create_async_engine(db_url, echo=False)

    async def initialise(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vocalmarket"))
            await conn.run_sync(Base.metadata.create_all)

    async def retrieve_summary(self, user_id: str, vertical: Vertical) -> str:
        """Return a human-readable memory summary for prompt injection."""
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text(
                    "SELECT content FROM vocalmarket.vocalmarket_user_memory "
                    "WHERE user_id = :uid AND vertical = :v AND memory_type = 'summary' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"uid": user_id, "v": vertical.value},
            )
            row = result.first()
            return row[0] if row else "No prior history for this user."

    async def get_recent_messages(self, conversation_id: str, limit: int = 10) -> list[BaseMessage]:
        """Return the last N messages as LangChain message objects."""
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                text(
                    "SELECT role, content FROM vocalmarket.vocalmarket_conversation_messages "
                    "WHERE conversation_id = :cid ORDER BY created_at DESC LIMIT :lim"
                ),
                {"cid": conversation_id, "lim": limit},
            )
            rows = list(reversed(result.fetchall()))

        messages: list[BaseMessage] = []
        for role, content in rows:
            messages.append(HumanMessage(content=content) if role == "human" else AIMessage(content=content))
        return messages

    async def record_turn(
        self,
        user_id: str,
        conversation_id: str,
        vertical: Vertical,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Persist a conversation turn and update the user's memory summary."""
        import uuid

        async with AsyncSession(self._engine) as session:
            async with session.begin():
                for role, content in [("human", user_message), ("assistant", assistant_message)]:
                    session.add(ConversationMessage(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        role=role,
                        content=content,
                    ))
                # Naive summary update — in production, run an LLM summarization task
                await session.execute(
                    text(
                        "INSERT INTO vocalmarket.vocalmarket_user_memory "
                        "(id, user_id, vertical, memory_type, content, created_at, updated_at) "
                        "VALUES (:id, :uid, :v, 'summary', :content, now(), now()) "
                        "ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, updated_at = now()"
                    ),
                    {
                        "id": f"{user_id}-{vertical.value}-summary",
                        "uid": user_id,
                        "v": vertical.value,
                        "content": f"Last interaction: {user_message[:200]}",
                    },
                )

    async def aclose(self) -> None:
        await self._engine.dispose()
