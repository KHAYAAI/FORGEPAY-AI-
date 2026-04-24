"""
VocalMarket Analytics Service — the Bloomberg data model.

Exposes aggregated, anonymized supplier intelligence to paying external customers:
consultants, banks, investors, and procurement teams benchmarking their suppliers.

Data is read from the same PostgreSQL schema as the intelligence service (vocalmarket.*)
but this service is read-only and never returns org_id, user_id, or any PII.

Auth: X-Analytics-API-Key header checked against ANALYTICS_API_KEYS env var
(comma-separated list of valid keys). Production should use short-lived JWTs
issued by a separate billing/subscription service.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import APIKeyHeader
from pydantic_settings import BaseSettings
from sqlalchemy import Float, Integer, String, Text, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column
from typing import Any

logger = logging.getLogger(__name__)


class AnalyticsSettings(BaseSettings):
    analytics_db_url: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/vocalmarket"
    )
    # Comma-separated list of valid API keys. At least one must be set in production.
    api_keys: str = ""

    class Config:
        env_prefix = "ANALYTICS_"

    def valid_keys(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


_settings = AnalyticsSettings()


# ─── Database (read-only mirror of intelligence service tables) ───────────────

class Base(DeclarativeBase):
    pass


class _SupplierMetric(Base):
    __tablename__ = "supplier_metrics"
    __table_args__ = {"schema": "vocalmarket"}
    id: Any = mapped_column(Integer, primary_key=True)
    supplier_id: Any = mapped_column(String(128), index=True, nullable=False)
    metric_type: Any = mapped_column(String(64), nullable=False)
    value: Any = mapped_column(Float, nullable=False, default=0.0)
    sample_count: Any = mapped_column(Integer, nullable=False, default=0)
    last_updated: Any = mapped_column(Text, nullable=False)


class _SupplierProfile(Base):
    __tablename__ = "supplier_profiles"
    __table_args__ = {"schema": "vocalmarket"}
    supplier_id: Any = mapped_column(String(128), primary_key=True)
    supplier_name: Any = mapped_column(String(256), nullable=False)
    vertical: Any = mapped_column(String(64), index=True, nullable=False)
    reliability_score: Any = mapped_column(Float, nullable=False, default=0.0)
    total_orders: Any = mapped_column(Integer, nullable=False, default=0)
    last_order_at: Any = mapped_column(Text, nullable=True)


class _SupplierCapabilityProfile(Base):
    __tablename__ = "supplier_capability_profiles"
    __table_args__ = {"schema": "vocalmarket"}
    supplier_id: Any = mapped_column(String(128), primary_key=True)
    supplier_name: Any = mapped_column(String(256), nullable=False)
    vertical: Any = mapped_column(String(64), nullable=False)
    country_code: Any = mapped_column(String(2), nullable=False)
    region: Any = mapped_column(String(128), nullable=False)
    certifications: Any = mapped_column(Text, nullable=False)
    lead_time_days_typical: Any = mapped_column(Integer, nullable=False)
    moq: Any = mapped_column(Integer, nullable=False)


_engine = create_async_engine(_settings.analytics_db_url, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


# ─── Auth ─────────────────────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-Analytics-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Depends(_api_key_header)) -> str:
    valid = _settings.valid_keys()
    if not valid:
        # Dev mode: no keys configured → open access
        return "dev"
    if not api_key or api_key not in valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid X-Analytics-API-Key header required",
        )
    return api_key


AuthDep = Annotated[str, Depends(require_api_key)]


# ─── App ──────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await _engine.dispose()


app = FastAPI(
    title="VocalMarket Analytics API",
    description=(
        "Aggregated, anonymized supplier intelligence. "
        "All responses are cross-org aggregates — no org_id, user_id, or PII is returned."
    ),
    lifespan=lifespan,
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/analytics/suppliers/top")
async def top_suppliers(
    _: AuthDep,
    vertical: str = Query(default="b2b_procurement", description="Vertical to filter by"),
    metric: str = Query(
        default="reliability_score",
        description="Sort metric: reliability_score | delivery_rate | defect_rate | response_time_hours",
    ),
    country_code: str | None = Query(default=None, description="Filter by ISO country code"),
    min_orders: int = Query(default=5, description="Minimum order count for inclusion (credibility filter)"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Top suppliers by reliability score or a specific metric.
    Only includes suppliers with at least min_orders completed orders.
    Response is anonymized — no buyer org data is included.
    """
    async with _session_factory() as session:
        if metric == "reliability_score":
            q = (
                select(
                    _SupplierProfile.supplier_id,
                    _SupplierProfile.supplier_name,
                    _SupplierProfile.vertical,
                    _SupplierProfile.reliability_score,
                    _SupplierProfile.total_orders,
                )
                .where(_SupplierProfile.vertical == vertical)
                .where(_SupplierProfile.total_orders >= min_orders)
                .order_by(_SupplierProfile.reliability_score.desc())
                .limit(limit)
            )
            result = await session.execute(q)
            rows = result.fetchall()
            suppliers = [
                {
                    "supplier_id": r.supplier_id,
                    "supplier_name": r.supplier_name,
                    "vertical": r.vertical,
                    "reliability_score": round(r.reliability_score, 3),
                    "total_orders": r.total_orders,
                    "rank": i + 1,
                }
                for i, r in enumerate(rows)
            ]
        else:
            # Fetch from metric table for a specific metric type
            q = (
                select(
                    _SupplierMetric.supplier_id,
                    _SupplierMetric.value,
                    _SupplierMetric.sample_count,
                    _SupplierProfile.supplier_name,
                    _SupplierProfile.vertical,
                    _SupplierProfile.reliability_score,
                )
                .join(_SupplierProfile, _SupplierMetric.supplier_id == _SupplierProfile.supplier_id)
                .where(_SupplierMetric.metric_type == metric)
                .where(_SupplierProfile.vertical == vertical)
                .where(_SupplierMetric.sample_count >= min_orders)
                .order_by(
                    _SupplierMetric.value.asc()
                    if metric in ("defect_rate", "response_time_hours")
                    else _SupplierMetric.value.desc()
                )
                .limit(limit)
            )
            result = await session.execute(q)
            rows = result.fetchall()
            suppliers = [
                {
                    "supplier_id": r.supplier_id,
                    "supplier_name": r.supplier_name,
                    "vertical": r.vertical,
                    metric: round(r.value, 3),
                    "sample_count": r.sample_count,
                    "reliability_score": round(r.reliability_score, 3),
                    "rank": i + 1,
                }
                for i, r in enumerate(rows)
            ]

    return {
        "vertical": vertical,
        "metric": metric,
        "suppliers": suppliers,
        "count": len(suppliers),
    }


@app.get("/analytics/market/summary")
async def market_summary(
    _: AuthDep,
    vertical: str = Query(default="b2b_procurement"),
):
    """
    Market-wide aggregated statistics for a vertical.
    Returns averages, percentiles, and counts across all suppliers — no supplier names.
    This is the core of the Bloomberg data model: macro signals across the supply chain.
    """
    async with _session_factory() as session:
        # Supplier count
        count_result = await session.execute(
            select(func.count(_SupplierProfile.supplier_id))
            .where(_SupplierProfile.vertical == vertical)
        )
        supplier_count = count_result.scalar_one() or 0

        # Aggregate metrics per type
        metrics_result = await session.execute(
            select(
                _SupplierMetric.metric_type,
                func.avg(_SupplierMetric.value).label("mean"),
                func.min(_SupplierMetric.value).label("min"),
                func.max(_SupplierMetric.value).label("max"),
                func.sum(_SupplierMetric.sample_count).label("total_samples"),
            )
            .join(_SupplierProfile, _SupplierMetric.supplier_id == _SupplierProfile.supplier_id)
            .where(_SupplierProfile.vertical == vertical)
            .group_by(_SupplierMetric.metric_type)
        )
        metrics_by_type = {
            row.metric_type: {
                "mean": round(row.mean, 3),
                "min": round(row.min, 3),
                "max": round(row.max, 3),
                "total_samples": row.total_samples,
            }
            for row in metrics_result.fetchall()
        }

        # Average reliability
        reliability_result = await session.execute(
            select(
                func.avg(_SupplierProfile.reliability_score).label("avg"),
                func.min(_SupplierProfile.reliability_score).label("min"),
                func.max(_SupplierProfile.reliability_score).label("max"),
                func.sum(_SupplierProfile.total_orders).label("total_orders"),
            )
            .where(_SupplierProfile.vertical == vertical)
        )
        r = reliability_result.fetchone()

    return {
        "vertical": vertical,
        "supplier_count": supplier_count,
        "total_orders_indexed": int(r.total_orders or 0),
        "reliability": {
            "market_average": round(float(r.avg or 0), 3),
            "best": round(float(r.max or 0), 3),
            "worst": round(float(r.min or 0), 3),
        },
        "metrics": metrics_by_type,
    }


@app.get("/analytics/market/benchmarks")
async def market_benchmarks(
    _: AuthDep,
    vertical: str = Query(default="b2b_procurement"),
    metric: str = Query(
        default="delivery_rate",
        description="Metric to benchmark: delivery_rate | defect_rate | response_time_hours",
    ),
):
    """
    Distribution percentiles for a specific metric across the market.
    Enables buyers to benchmark their suppliers: 'Is 85% on-time delivery good or average?'
    """
    async with _session_factory() as session:
        result = await session.execute(
            select(_SupplierMetric.value)
            .join(_SupplierProfile, _SupplierMetric.supplier_id == _SupplierProfile.supplier_id)
            .where(_SupplierMetric.metric_type == metric)
            .where(_SupplierProfile.vertical == vertical)
            .where(_SupplierMetric.sample_count >= 3)
            .order_by(_SupplierMetric.value)
        )
        values = [row[0] for row in result.fetchall()]

    if not values:
        return {"vertical": vertical, "metric": metric, "message": "Insufficient data", "percentiles": {}}

    n = len(values)

    def percentile(p: float) -> float:
        idx = int(p / 100 * (n - 1))
        return round(values[idx], 3)

    return {
        "vertical": vertical,
        "metric": metric,
        "sample_size": n,
        "percentiles": {
            "p10": percentile(10),
            "p25": percentile(25),
            "p50": percentile(50),
            "p75": percentile(75),
            "p90": percentile(90),
        },
        "mean": round(sum(values) / n, 3),
    }


@app.get("/analytics/suppliers/{supplier_id}/metrics")
async def supplier_metrics_detail(
    supplier_id: str,
    _: AuthDep,
):
    """Full metric breakdown for a single supplier (public supplier ID, no buyer data)."""
    async with _session_factory() as session:
        profile_result = await session.execute(
            select(_SupplierProfile).where(_SupplierProfile.supplier_id == supplier_id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            raise HTTPException(status_code=404, detail="Supplier not found")

        metrics_result = await session.execute(
            select(_SupplierMetric).where(_SupplierMetric.supplier_id == supplier_id)
        )
        metrics = {
            row.metric_type: {"value": round(row.value, 3), "sample_count": row.sample_count}
            for row in metrics_result.scalars().all()
        }

    return {
        "supplier_id": profile.supplier_id,
        "supplier_name": profile.supplier_name,
        "vertical": profile.vertical,
        "reliability_score": round(profile.reliability_score, 3),
        "total_orders": profile.total_orders,
        "metrics": metrics,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analytics"}
