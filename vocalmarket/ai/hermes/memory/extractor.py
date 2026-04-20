"""
LLM-based fact extractor.

After each conversation turn, this runs a small focused LLM call to pull
structured facts from the exchange. Facts are then embedded and written to
the semantic memory store.

Kept as a separate module so the extraction prompt and schema can evolve
independently of the main Hermes system prompt.
"""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .store import ExtractedFact, FactType

EXTRACT_SYSTEM = """You are a memory extraction assistant.
Given a conversation exchange, identify any new facts about the USER that should be
remembered for future sessions. Be precise and brief.

Return a JSON array of facts. Each fact:
{
  "content": "<concise statement in third person, e.g. 'User is vegetarian'>",
  "fact_type": "preference|order|health|contact|constraint",
  "importance": 0.1-1.0
}

Only extract facts that are:
- Durable (not one-time, not about the current session)
- About the USER specifically (not products or policies)
- New or updates to known information

Return [] if nothing new to extract.
"""


class FactExtractor:
    """Extracts durable user facts from a conversation turn using a small LLM call."""

    def __init__(self, llm: ChatOpenAI) -> None:
        self._llm = llm

    async def extract(
        self,
        human_message: str,
        ai_message: str,
        vertical: str,
    ) -> list[ExtractedFact]:
        prompt = f"""Vertical: {vertical}

User said: {human_message}

Assistant said: {ai_message}

Extract any durable facts about the user from this exchange."""

        try:
            response = await self._llm.ainvoke([
                SystemMessage(content=EXTRACT_SYSTEM),
                HumanMessage(content=prompt),
            ])
            raw = response.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            facts_data = json.loads(raw)
            return [
                ExtractedFact(
                    content=f["content"],
                    fact_type=FactType(f.get("fact_type", "preference")),
                    importance=float(f.get("importance", 0.7)),
                )
                for f in facts_data
                if isinstance(f, dict) and f.get("content")
            ]
        except (json.JSONDecodeError, KeyError, ValueError):
            return []
