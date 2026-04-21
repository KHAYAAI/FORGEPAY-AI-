"""
Supplier Intelligence Store — the data moat.

Records structured performance metrics per supplier across ALL transactions from ALL users.
This cross-org aggregation is what makes VocalMarket irreplaceable after Year 2:
  - delivery_rate: fraction of orders delivered on time
  - response_time_hours: average time to respond to an RFQ
  - defect_rate: fraction of orders with reported defects/returns
  - quote_acceptance_rate: fraction of RFQ quotes accepted by buyers
  - capacity_utilisation: rolling signal of supplier volume trend

Data is written on every payment.completed webhook via record_transaction().
It is read by GetSupplierIntelligenceTool so Hermes can answer
"which supplier has the best delivery record for steel fasteners?".

All metrics are running averages updated with Welford's online algorithm to
avoid needing to store every raw data point.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic_settings import BaseSettings
from sqlalchemy import Float, Integer, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column

logger = logging.getLogger(__name__)


class IntelligenceSettings(BaseSettings):
    intelligence_db_url: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/vocalmarket"
    )

    class Config:
        env_prefix = "INTELLIGENCE_"


_settings = IntelligenceSettings()


class Base(DeclarativeBase):
    pass


class SupplierMetric(Base):
    """
    One running-average metric for a supplier.

    Uses Welford's online algorithm: new_mean = old_mean + (value - old_mean) / n
    so we never need to store every individual data point.
    """

    __tablename__ = "supplier_metrics"
    __table_args__ = {"schema": "vocalmarket"}

    id: Any = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Any = mapped_column(String(128), index=True, nullable=False)
    # e.g. "delivery_rate", "response_time_hours", "defect_rate",
    #      "quote_acceptance_rate", "capacity_utilisation"
    metric_type: Any = mapped_column(String(64), nullable=False)
    value: Any = mapped_column(Float, nullable=False, default=0.0)
    sample_count: Any = mapped_column(Integer, nullable=False, default=0)
    last_updated: Any = mapped_column(Text, nullable=False)  # ISO timestamp


class SupplierProfile(Base):
    """
    Denormalised supplier profile — updated whenever new data comes in.
    Used for quick ranked queries without computing across many metric rows.
    """

    __tablename__ = "supplier_profiles"
    __table_args__ = {"schema": "vocalmarket"}

    supplier_id: Any = mapped_column(String(128), primary_key=True)
    supplier_name: Any = mapped_column(String(256), nullable=False)
    vertical: Any = mapped_column(String(64), index=True, nullable=False)
    # Composite reliability score 0-1, re-computed on each update
    reliability_score: Any = mapped_column(Float, nullable=False, default=0.0)
    total_orders: Any = mapped_column(Integer, nullable=False, default=0)
    last_order_at: Any = mapped_column(Text, nullable=True)  # ISO timestamp


class TransactionRecord(Base):
    """
    Immutable log of every completed transaction — the raw data that drives metrics.
    Kept for auditability and for re-computing metrics if the formula changes.
    """

    __tablename__ = "transaction_records"
    __table_args__ = {"schema": "vocalmarket"}

    id: Any = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Any = mapped_column(String(128), index=True, nullable=False)
    supplier_id: Any = mapped_column(String(128), index=True, nullable=False)
    vertical: Any = mapped_column(String(64), nullable=False)
    # Delivery promise vs actual (seconds). Negative = early, positive = late.
    delivery_delta_seconds: Any = mapped_column(Integer, nullable=True)
    was_on_time: Any = mapped_column(Integer, nullable=True)   # 0 or 1
    had_defect: Any = mapped_column(Integer, nullable=False, default=0)  # 0 or 1
    order_value_cents: Any = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Any = mapped_column(Text, nullable=False)  # ISO timestamp


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _welford_update(old_mean: float, old_n: int, new_value: float) -> tuple[float, int]:
    """Welford's online algorithm: O(1) running mean update."""
    n = old_n + 1
    new_mean = old_mean + (new_value - old_mean) / n
    return new_mean, n


def _reliability_score(delivery_rate: float, defect_rate: float, n: int) -> float:
    """
    Composite reliability score 0-1.
    Weighted: delivery 60%, quality 40%, credibility discount for low sample counts.
    """
    if n == 0:
        return 0.5  # neutral for new suppliers
    raw = delivery_rate * 0.6 + (1.0 - defect_rate) * 0.4
    # Confidence discount: score pulled toward 0.5 when n < 10
    confidence = min(n / 10.0, 1.0)
    return raw * confidence + 0.5 * (1.0 - confidence)


class SupplierIntelligenceStore:
    """
    Async store for cross-org supplier intelligence metrics.

    All updates use Welford's online algorithm — no need to keep every raw
    data point in memory, and updates are O(1) per metric.
    """

    def __init__(self) -> None:
        self._engine = create_async_engine(_settings.intelligence_db_url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def initialise(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vocalmarket"))
            await conn.run_sync(Base.metadata.create_all)

    async def record_transaction(
        self,
        order_id: str,
        supplier_id: str,
        supplier_name: str,
        vertical: str,
        order_value_cents: int,
        was_on_time: bool | None = None,
        had_defect: bool = False,
        delivery_delta_seconds: int | None = None,
    ) -> None:
        """
        Record a completed transaction and update all relevant supplier metrics.
        Called by the payment.completed webhook handler.
        """
        async with self._session_factory() as session:
            # 1. Write immutable transaction log
            record = TransactionRecord(
                order_id=order_id,
                supplier_id=supplier_id,
                vertical=vertical,
                delivery_delta_seconds=delivery_delta_seconds,
                was_on_time=1 if was_on_time else (0 if was_on_time is False else None),
                had_defect=1 if had_defect else 0,
                order_value_cents=order_value_cents,
                recorded_at=_now(),
            )
            session.add(record)

            # 2. Update running metrics
            if was_on_time is not None:
                await self._update_metric(
                    session, supplier_id, "delivery_rate", 1.0 if was_on_time else 0.0
                )
            if had_defect is not None:
                await self._update_metric(
                    session, supplier_id, "defect_rate", 1.0 if had_defect else 0.0
                )

            # 3. Upsert supplier profile
            await self._upsert_profile(session, supplier_id, supplier_name, vertical)

            await session.commit()

        logger.info(
            "Recorded transaction for supplier %s order %s (on_time=%s, defect=%s)",
            supplier_id, order_id, was_on_time, had_defect,
        )

    async def record_rfq_response(
        self,
        supplier_id: str,
        response_time_hours: float,
        was_accepted: bool,
    ) -> None:
        """Record RFQ response metrics — called when supplier responds to a quote request."""
        async with self._session_factory() as session:
            await self._update_metric(
                session, supplier_id, "response_time_hours", response_time_hours
            )
            await self._update_metric(
                session, supplier_id, "quote_acceptance_rate", 1.0 if was_accepted else 0.0
            )
            await session.commit()

    async def get_supplier_intelligence(
        self,
        supplier_ids: list[str] | None = None,
        vertical: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Return ranked supplier intelligence.

        If supplier_ids provided, returns metrics for those specific suppliers.
        Otherwise returns the top-N suppliers by reliability_score for the vertical.
        """
        async with self._session_factory() as session:
            q = select(SupplierProfile)
            if supplier_ids:
                q = q.where(SupplierProfile.supplier_id.in_(supplier_ids))
            if vertical:
                q = q.where(SupplierProfile.vertical == vertical)
            q = q.order_by(SupplierProfile.reliability_score.desc()).limit(limit)
            result = await session.execute(q)
            profiles = result.scalars().all()

            output = []
            for p in profiles:
                metrics = await self._load_metrics(session, p.supplier_id)
                output.append({
                    "supplier_id": p.supplier_id,
                    "supplier_name": p.supplier_name,
                    "reliability_score": round(p.reliability_score, 3),
                    "total_orders": p.total_orders,
                    "delivery_rate": round(metrics.get("delivery_rate", 0.0), 3),
                    "defect_rate": round(metrics.get("defect_rate", 0.0), 3),
                    "avg_rfq_response_hours": round(metrics.get("response_time_hours", 0.0), 1),
                    "quote_acceptance_rate": round(metrics.get("quote_acceptance_rate", 0.0), 3),
                    "sample_count": p.total_orders,
                })
            return output

    async def _update_metric(
        self,
        session: AsyncSession,
        supplier_id: str,
        metric_type: str,
        new_value: float,
    ) -> None:
        result = await session.execute(
            select(SupplierMetric).where(
                SupplierMetric.supplier_id == supplier_id,
                SupplierMetric.metric_type == metric_type,
            )
        )
        metric = result.scalar_one_or_none()

        if metric is None:
            session.add(SupplierMetric(
                supplier_id=supplier_id,
                metric_type=metric_type,
                value=new_value,
                sample_count=1,
                last_updated=_now(),
            ))
        else:
            new_mean, new_n = _welford_update(metric.value, metric.sample_count, new_value)
            metric.value = new_mean
            metric.sample_count = new_n
            metric.last_updated = _now()

    async def _upsert_profile(
        self,
        session: AsyncSession,
        supplier_id: str,
        supplier_name: str,
        vertical: str,
    ) -> None:
        result = await session.execute(
            select(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
        )
        profile = result.scalar_one_or_none()

        metrics = await self._load_metrics(session, supplier_id)
        delivery_rate = metrics.get("delivery_rate", 0.5)
        defect_rate = metrics.get("defect_rate", 0.0)
        n = int(metrics.get("_max_n", 0))
        score = _reliability_score(delivery_rate, defect_rate, n)

        if profile is None:
            session.add(SupplierProfile(
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                vertical=vertical,
                reliability_score=score,
                total_orders=1,
                last_order_at=_now(),
            ))
        else:
            profile.reliability_score = score
            profile.total_orders = (profile.total_orders or 0) + 1
            profile.last_order_at = _now()
            if supplier_name:
                profile.supplier_name = supplier_name

    async def _load_metrics(
        self, session: AsyncSession, supplier_id: str
    ) -> dict[str, float]:
        result = await session.execute(
            select(SupplierMetric).where(SupplierMetric.supplier_id == supplier_id)
        )
        rows = result.scalars().all()
        out: dict[str, float] = {}
        max_n = 0
        for row in rows:
            out[row.metric_type] = row.value
            if row.sample_count > max_n:
                max_n = row.sample_count
        out["_max_n"] = float(max_n)
        return out

    async def aclose(self) -> None:
        await self._engine.dispose()


# Module-level singleton
_store: SupplierIntelligenceStore | None = None


async def get_supplier_intelligence_store() -> SupplierIntelligenceStore:
    global _store
    if _store is None:
        _store = SupplierIntelligenceStore()
        await _store.initialise()
    return _store
