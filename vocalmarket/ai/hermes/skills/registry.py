"""
Skill registry — loads and manages Hermes skills from the database.

Skills are stored as JSON in the memory_facts table with fact_type='skill'.
On startup the registry fetches all skills for the user/vertical and returns
them as LangChain tools so Hermes can invoke them directly.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..memory.store import MemoryFact
from .base import BaseSkill, SkillMetadata

if TYPE_CHECKING:
    from langchain.tools import BaseTool


class SkillRegistry:
    """Loads per-user skills from PostgreSQL and exposes them as tools."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def load_skills(self, user_id: str, vertical: str) -> list["BaseTool"]:
        """Return tools for all stored skills for this user/vertical."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MemoryFact)
                .where(
                    MemoryFact.user_id == user_id,
                    MemoryFact.vertical == vertical,
                    MemoryFact.fact_type == "skill",
                )
                .order_by(MemoryFact.importance.desc())
            )
            facts = result.scalars().all()

        tools: list[BaseTool] = []
        for fact in facts:
            try:
                skill_data = json.loads(fact.content)
                meta = SkillMetadata(
                    skill_id=str(fact.id),
                    name=skill_data["name"],
                    description=skill_data["description"],
                    vertical=vertical,
                    usage_count=skill_data.get("usage_count", 0),
                    success_rate=skill_data.get("success_rate", 1.0),
                )
                skill = _StoredSkill(meta, skill_data.get("steps", []))
                tools.append(skill.as_tool())
            except (json.JSONDecodeError, KeyError):
                continue
        return tools

    async def register_skill(
        self,
        user_id: str,
        vertical: str,
        name: str,
        description: str,
        steps: list[dict],
    ) -> str:
        """Persist a new skill to the memory store. Returns the skill_id."""
        skill_id = str(uuid.uuid4())
        content = json.dumps({
            "name": name,
            "description": description,
            "steps": steps,
            "usage_count": 0,
            "success_rate": 1.0,
        })
        async with self._session_factory() as session:
            async with session.begin():
                session.add(MemoryFact(
                    id=uuid.UUID(skill_id),
                    user_id=user_id,
                    vertical=vertical,
                    fact_type="skill",
                    content=content,
                    importance=0.9,
                ))
        return skill_id


class _StoredSkill(BaseSkill):
    """A skill loaded from the database. Steps are descriptive strings for now."""

    def __init__(self, metadata: SkillMetadata, steps: list[dict]) -> None:
        super().__init__(metadata)
        self._steps = steps

    async def execute(self, params: dict, user_id: str) -> str:
        # Future: interpret steps as tool-call sequences
        return f"Skill '{self.metadata.name}' triggered with params: {params}"
