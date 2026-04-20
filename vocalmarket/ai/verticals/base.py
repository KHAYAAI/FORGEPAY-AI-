"""Abstract base for vertical-specific AI configuration."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain.tools import BaseTool


class BaseVertical(ABC):
    """
    Each vertical subclass provides:
      - A system prompt fragment with domain-specific guidance
      - Additional tools beyond the base set
      - Compliance checks run before order confirmation
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def system_prompt_fragment(self) -> str:
        """Extra instructions injected into Hermes system prompt for this vertical."""

    @abstractmethod
    def extra_tools(self) -> list["BaseTool"]:
        """Domain-specific tools added on top of the base SearchProducts/PlaceOrder set."""

    @abstractmethod
    async def pre_order_compliance_check(self, order_items: list[dict], user_id: str) -> tuple[bool, str]:
        """
        Returns (ok, reason). If ok=False the order is blocked and reason is
        read back to the user via TTS.
        """
