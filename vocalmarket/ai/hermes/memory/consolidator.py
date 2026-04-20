"""
Memory consolidation — runs as a Celery task when episodic turn count
crosses CONSOLIDATION_THRESHOLD.

Takes the last N episodic turns for a user/vertical, asks the LLM to produce
a narrative summary, writes it back to MemorySummary, then prunes old episodic
rows to keep the database lean.

This is intentionally decoupled from the hot path: the Hermes handler fires it
as a fire-and-forget background task after a turn completes.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .store import EpisodicMessage, MemoryContext, UserMemoryStore

CONSOLIDATE_SYSTEM = """You are a memory consolidation assistant.
Given a series of conversation turns between a user and a shopping assistant,
write a concise paragraph (3-5 sentences) summarising what you now know about
the user: their preferences, purchase history, constraints, and any important
personal context relevant to future shopping sessions.

Write in third person. Be factual and specific. Do not include product names
unless they reflect a durable preference.
"""


class MemoryConsolidator:
    """Runs LLM summarisation over episodic history and updates the summary store."""

    def __init__(self, store: UserMemoryStore, llm: ChatOpenAI) -> None:
        self._store = store
        self._llm = llm

    async def consolidate(
        self,
        user_id: str,
        vertical: str,
        conversation_id: str,
        context: MemoryContext,
    ) -> None:
        if not context.episodic_messages:
            return

        # Format episodic messages as a readable transcript
        lines: list[str] = []
        for msg in context.episodic_messages:
            role = "User" if msg.__class__.__name__ == "HumanMessage" else "Assistant"
            lines.append(f"{role}: {msg.content}")
        transcript = "\n".join(lines)

        existing = f"\nExisting summary:\n{context.summary}" if context.summary else ""
        prompt = f"Vertical: {vertical}{existing}\n\nRecent conversation:\n{transcript}"

        try:
            response = await self._llm.ainvoke([
                SystemMessage(content=CONSOLIDATE_SYSTEM),
                HumanMessage(content=prompt),
            ])
            new_summary = response.content.strip()
        except Exception:
            return  # Don't fail a conversation turn because of consolidation

        await self._store.update_summary(
            user_id=user_id,
            vertical=vertical,
            content=new_summary,
            turn_count=context.turn_count,
        )
        await self._store.prune_episodic(conversation_id, keep_last=100)
