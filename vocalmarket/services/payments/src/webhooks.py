"""
ForgePay webhook handler.

ForgePay sends signed POST requests when payment status changes.
We verify the HMAC signature, then trigger downstream actions:
  - payment.completed   → notify Medusa to confirm the order + record supplier metrics
  - payment.failed      → notify the user and release reserved inventory
  - payment.refunded    → update order status and trigger reconciliation
  - payment.expired     → release cart
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from .forgepay import forgepay

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MEDUSA_BASE = "http://medusa:9000"
ORCHESTRATOR_BASE = "http://ai-orchestrator:8002"
INTELLIGENCE_BASE = "http://intelligence:8004"


class WebhookEvent(BaseModel):
    event: str
    session_id: str
    order_id: str
    payment_id: str | None = None
    amount: int | None = None
    currency: str | None = None
    # Supplier fields populated by Medusa order data
    supplier_id: str | None = None
    supplier_name: str | None = None
    vertical: str | None = None
    metadata: dict = {}


@router.post("/forgepay")
async def forgepay_webhook(
    request: Request,
    x_forgepay_signature: str = Header(..., alias="X-ForgePay-Signature"),
):
    payload = await request.body()

    if not forgepay.verify_webhook_signature(payload, x_forgepay_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    import json
    event_data = WebhookEvent(**json.loads(payload))

    async with httpx.AsyncClient(timeout=10.0) as client:
        match event_data.event:
            case "payment.completed":
                await _on_payment_completed(client, event_data)
            case "payment.failed":
                await _on_payment_failed(client, event_data)
            case "payment.refunded":
                await _on_payment_refunded(client, event_data)
            case "payment.expired":
                await _on_payment_expired(client, event_data)
            case _:
                logger.info("Unhandled ForgePay event: %s", event_data.event)

    return {"status": "ok"}


async def _on_payment_completed(client: httpx.AsyncClient, event: WebhookEvent) -> None:
    """Confirm the Medusa order, notify the AI orchestrator, and record supplier metrics."""
    logger.info("Payment completed for order %s", event.order_id)

    # 1. Fetch full order details from Medusa to get supplier info
    supplier_id = event.supplier_id
    supplier_name = event.supplier_name
    vertical = event.vertical or "b2b_procurement"
    order_value_cents = event.amount or 0

    try:
        order_resp = await client.get(
            f"{MEDUSA_BASE}/admin/orders/{event.order_id}",
            headers={"Authorization": f"Bearer {_medusa_token()}"},
        )
        if order_resp.status_code == 200:
            order = order_resp.json().get("order", {})
            # Pull supplier from first line item if not in event metadata
            items = order.get("items", [])
            if items and not supplier_id:
                supplier_id = items[0].get("supplier_id") or items[0].get("vendor_id")
                supplier_name = items[0].get("supplier_name") or supplier_name
            vertical = order.get("metadata", {}).get("vertical", vertical)
            order_value_cents = order_value_cents or order.get("total", 0)
    except httpx.HTTPError as e:
        logger.warning("Could not fetch order details for intelligence pipeline: %s", e)

    # 2. Confirm order in Medusa (mark payment as captured)
    try:
        resp = await client.post(
            f"{MEDUSA_BASE}/admin/orders/{event.order_id}/capture",
            headers={"Authorization": f"Bearer {_medusa_token()}"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("Failed to confirm Medusa order %s: %s", event.order_id, e)
        raise

    # 3. Record supplier metrics in intelligence store (best-effort, non-blocking)
    if supplier_id:
        try:
            await client.post(
                f"{INTELLIGENCE_BASE}/internal/transactions",
                json={
                    "order_id": event.order_id,
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name or supplier_id,
                    "vertical": vertical,
                    "order_value_cents": order_value_cents,
                    # Delivery tracking is updated later when delivery is confirmed
                    "was_on_time": None,
                    "had_defect": False,
                },
            )
        except httpx.HTTPError as e:
            # Non-fatal — intelligence pipeline failure must never block payment confirmation
            logger.warning("Intelligence pipeline record failed for order %s: %s", event.order_id, e)

    # 4. Notify AI orchestrator to update conversation context
    try:
        await client.post(
            f"{ORCHESTRATOR_BASE}/events/payment-completed",
            json={"order_id": event.order_id, "metadata": event.metadata},
        )
    except httpx.HTTPError as e:
        logger.warning("Orchestrator notification failed for order %s: %s", event.order_id, e)


async def _on_payment_failed(client: httpx.AsyncClient, event: WebhookEvent) -> None:
    logger.warning("Payment failed for order %s", event.order_id)
    await client.post(
        f"{ORCHESTRATOR_BASE}/events/payment-failed",
        json={"order_id": event.order_id, "metadata": event.metadata},
    )


async def _on_payment_refunded(client: httpx.AsyncClient, event: WebhookEvent) -> None:
    logger.info("Payment refunded for order %s — amount: %s", event.order_id, event.amount)
    # Record defect signal in supplier intelligence (refund implies product issue)
    if event.supplier_id:
        try:
            await client.post(
                f"{INTELLIGENCE_BASE}/internal/transactions",
                json={
                    "order_id": event.order_id,
                    "supplier_id": event.supplier_id,
                    "supplier_name": event.supplier_name or event.supplier_id,
                    "vertical": event.vertical or "b2b_procurement",
                    "order_value_cents": event.amount or 0,
                    "was_on_time": None,
                    "had_defect": True,
                },
            )
        except httpx.HTTPError as e:
            logger.warning("Intelligence refund signal failed: %s", e)

    await client.post(
        f"{MEDUSA_BASE}/admin/orders/{event.order_id}/refunds",
        json={"amount": event.amount},
        headers={"Authorization": f"Bearer {_medusa_token()}"},
    )


async def _on_payment_expired(client: httpx.AsyncClient, event: WebhookEvent) -> None:
    logger.info("Payment session expired for order %s", event.order_id)
    await client.post(
        f"{ORCHESTRATOR_BASE}/events/payment-expired",
        json={"order_id": event.order_id},
    )


def _medusa_token() -> str:
    import os
    return os.environ.get("MEDUSA_ADMIN_TOKEN", "")
