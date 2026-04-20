"""
Enthusiast as Hermes tools.

These LangChain tools let Hermes call Enthusiast's agents as atomic actions.
Hermes never touches the catalog directly — it always goes through these tools,
which preserves Enthusiast's reliability guarantees.
"""

from typing import Any

import httpx
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from vocalmarket.shared.config.verticals import VerticalConfig


class SearchProductsInput(BaseModel):
    query: str = Field(description="Natural language product search query")
    filters: dict[str, Any] | None = Field(default=None, description="Optional filters: price_max, brand, in_stock")


class SearchProductsTool(BaseTool):
    """Search the product catalog for a given vertical using Enthusiast's RAG pipeline."""

    name: str = "search_products"
    description: str = (
        "Search for products in the catalog. Use this when the user asks to find, "
        "browse, or compare products. Returns a ranked list with prices and availability."
    )
    args_schema: type[BaseModel] = SearchProductsInput

    vertical_config: VerticalConfig
    enthusiast_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(self, query: str, filters: dict | None = None) -> str:
        ds_id = self.vertical_config.enthusiast_data_set_id
        agent_id = self.vertical_config.product_search_agent_id

        # Create a one-shot conversation with Enthusiast's product-search agent
        conv_resp = await self.enthusiast_client.post(
            f"/api/data-sets/{ds_id}/conversations/",
            json={"name": f"hermes-tool-search-{query[:30]}"},
        )
        conv_resp.raise_for_status()
        conv_id = conv_resp.json()["id"]

        msg_resp = await self.enthusiast_client.post(
            f"/api/data-sets/{ds_id}/conversations/{conv_id}/messages/",
            json={"content": query, "agent_id": agent_id, "filters": filters},
        )
        msg_resp.raise_for_status()
        data = msg_resp.json()

        products = data.get("products", [])
        if not products:
            return "No products found matching that query."

        lines = [f"Found {len(products)} products:"]
        for p in products[:5]:
            curated = " [PREFERRED SUPPLIER]" if p.get("is_curated") else ""
            lines.append(f"- {p['name']} — {p['currency']} {p['price']}{curated}")
        return "\n".join(lines)

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async version")


class CheckInventoryInput(BaseModel):
    product_ids: list[str] = Field(description="List of product IDs to check")


class CheckInventoryTool(BaseTool):
    """Check real-time stock availability for specific products via Medusa.js."""

    name: str = "check_inventory"
    description: str = (
        "Check if specific products are in stock. Use before confirming an order "
        "or when the user asks about availability."
    )
    args_schema: type[BaseModel] = CheckInventoryInput

    medusa_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(self, product_ids: list[str]) -> str:
        resp = await self.medusa_client.post(
            "/store/inventory/check",
            json={"product_ids": product_ids},
        )
        resp.raise_for_status()
        inventory = resp.json()

        lines = []
        for item in inventory.get("items", []):
            status = "In stock" if item["available"] else f"Out of stock (next restock: {item.get('restock_date', 'unknown')})"
            lines.append(f"- {item['name']}: {status}")
        return "\n".join(lines) if lines else "No inventory data available."

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async version")


class PlaceOrderInput(BaseModel):
    items: list[dict] = Field(description="List of {product_id, quantity, variant_id}")
    shipping_address_id: str | None = Field(default=None)
    payment_method: str = Field(default="card", description="card | stablecoin | x402")


class PlaceOrderTool(BaseTool):
    """Place an order via Medusa.js and initiate payment via ForgePay."""

    name: str = "place_order"
    description: str = (
        "Place an order for the confirmed items. Only call this after the user has "
        "explicitly confirmed they want to purchase. Returns order ID and payment link."
    )
    args_schema: type[BaseModel] = PlaceOrderInput

    medusa_client: httpx.AsyncClient
    forgepay_client: httpx.AsyncClient

    class Config:
        arbitrary_types_allowed = True

    async def _arun(self, items: list[dict], shipping_address_id: str | None = None, payment_method: str = "card") -> str:
        order_resp = await self.medusa_client.post(
            "/store/orders",
            json={"items": items, "shipping_address_id": shipping_address_id},
        )
        order_resp.raise_for_status()
        order = order_resp.json()

        pay_resp = await self.forgepay_client.post(
            "/payments/initiate",
            json={"order_id": order["id"], "method": payment_method, "amount": order["total"]},
        )
        pay_resp.raise_for_status()
        payment = pay_resp.json()

        return f"Order #{order['id']} created. Complete payment at: {payment['payment_url']}"

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async version")
