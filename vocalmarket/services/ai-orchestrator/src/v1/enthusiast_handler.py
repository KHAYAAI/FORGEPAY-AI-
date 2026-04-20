"""
V1 handler: calls Enthusiast's REST API directly.

Enthusiast already has a full conversation + agent execution pipeline.
This handler is a thin async HTTP wrapper around it — no LLM logic here.
"""

from dataclasses import dataclass

import httpx

from vocalmarket.shared.config.feature_flags import Vertical
from vocalmarket.shared.config.verticals import vertical_settings
from ..config import settings


@dataclass
class EnthusiastResult:
    text: str
    conversation_id: str
    products: list[dict] | None = None
    suggested_actions: list[dict] | None = None


class EnthusiastHandler:
    """Thin async wrapper around the Enthusiast conversation API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.enthusiast_base_url,
            headers={"Authorization": f"Token {settings.enthusiast_api_key}"},
            timeout=30.0,
        )

    async def chat(
        self,
        conversation_id: str,
        message: str,
        vertical: Vertical,
        data_set_id: str | None = None,
    ) -> EnthusiastResult:
        vertical_cfg = self._vertical_config(vertical)
        ds_id = data_set_id or vertical_cfg.enthusiast_data_set_id

        # POST to existing conversation (creates one on first call if needed)
        response = await self._client.post(
            f"/api/data-sets/{ds_id}/conversations/{conversation_id}/messages/",
            json={
                "content": message,
                "agent_id": vertical_cfg.product_search_agent_id,
            },
        )
        response.raise_for_status()
        data = response.json()

        return EnthusiastResult(
            text=data.get("response", ""),
            conversation_id=conversation_id,
            products=data.get("products"),
            suggested_actions=data.get("actions"),
        )

    async def get_or_create_conversation(self, vertical: Vertical, user_id: str) -> str:
        vertical_cfg = self._vertical_config(vertical)
        ds_id = vertical_cfg.enthusiast_data_set_id

        response = await self._client.post(
            f"/api/data-sets/{ds_id}/conversations/",
            json={"name": f"{vertical.value}-{user_id}"},
        )
        response.raise_for_status()
        return response.json()["id"]

    def _vertical_config(self, vertical: Vertical):
        return getattr(vertical_settings, vertical.value)()

    async def aclose(self) -> None:
        await self._client.aclose()
