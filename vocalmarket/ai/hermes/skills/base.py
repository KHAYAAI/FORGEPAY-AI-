"""
Hermes skill system — autonomous skill creation and refinement.

A Skill is a reusable, parameterised procedure that Hermes discovers has
worked well in past sessions and crystallises into a named, callable unit.
Skills are stored in the memory database and loaded at agent startup.

Example skills Hermes might auto-create:
  - "reorder_weekly_groceries": place last week's grocery order with one confirmation
  - "check_and_restock_ppe": query PPE inventory + create restock order if below threshold
  - "prescription_refill_flow": check prescription validity, find cheapest pharmacy, confirm
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langchain.tools import BaseTool


@dataclass
class SkillMetadata:
    skill_id: str
    name: str
    description: str
    vertical: str
    usage_count: int = 0
    success_rate: float = 1.0


class BaseSkill(ABC):
    """
    A learned procedure Hermes can invoke instead of reasoning from scratch.
    Subclasses implement `execute` and expose themselves as a LangChain tool
    via `as_tool()`.
    """

    def __init__(self, metadata: SkillMetadata) -> None:
        self.metadata = metadata

    @abstractmethod
    async def execute(self, params: dict[str, Any], user_id: str) -> str:
        """Run the skill. Return a plain-text result for Hermes to synthesise."""

    def as_tool(self) -> BaseTool:
        skill = self

        class _SkillTool(BaseTool):
            name: str = skill.metadata.name
            description: str = skill.metadata.description

            async def _arun(self, **kwargs: Any) -> str:
                return await skill.execute(kwargs, user_id="")  # user_id injected at runtime

            def _run(self, **kwargs: Any) -> str:
                raise NotImplementedError("Use async version")

        return _SkillTool()
