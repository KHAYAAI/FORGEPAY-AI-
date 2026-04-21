"""
Tests for SupplierIntelligenceStore and the Welford running-average logic.

Uses mocked SQLAlchemy sessions to avoid requiring a real database.
"""

from __future__ import annotations

import pytest


class TestWelfordUpdate:
    """Unit tests for the Welford online algorithm."""

    def test_first_sample(self):
        from vocalmarket.services.intelligence.supplier_store import _welford_update
        mean, n = _welford_update(0.0, 0, 1.0)
        assert n == 1
        assert mean == pytest.approx(1.0)

    def test_two_samples_average(self):
        from vocalmarket.services.intelligence.supplier_store import _welford_update
        mean, n = _welford_update(0.0, 0, 0.8)
        mean, n = _welford_update(mean, n, 1.0)
        assert n == 2
        assert mean == pytest.approx(0.9)

    def test_running_mean_convergence(self):
        from vocalmarket.services.intelligence.supplier_store import _welford_update
        values = [1.0, 1.0, 0.0, 1.0, 1.0]  # 4 on-time, 1 late → 80% delivery
        mean, n = 0.0, 0
        for v in values:
            mean, n = _welford_update(mean, n, v)
        assert n == 5
        assert mean == pytest.approx(0.8)


class TestReliabilityScore:
    """Unit tests for the composite reliability score."""

    def test_perfect_supplier(self):
        from vocalmarket.services.intelligence.supplier_store import _reliability_score
        score = _reliability_score(delivery_rate=1.0, defect_rate=0.0, n=20)
        assert score == pytest.approx(1.0)

    def test_worst_supplier(self):
        from vocalmarket.services.intelligence.supplier_store import _reliability_score
        score = _reliability_score(delivery_rate=0.0, defect_rate=1.0, n=20)
        assert score == pytest.approx(0.0)

    def test_neutral_new_supplier(self):
        from vocalmarket.services.intelligence.supplier_store import _reliability_score
        # n=0 → neutral 0.5
        score = _reliability_score(delivery_rate=0.9, defect_rate=0.05, n=0)
        assert score == pytest.approx(0.5)

    def test_low_confidence_pulled_toward_neutral(self):
        from vocalmarket.services.intelligence.supplier_store import _reliability_score
        # n=5 → exactly halfway between raw score and 0.5
        raw = 1.0 * 0.6 + (1.0 - 0.0) * 0.4  # = 1.0
        confidence = 5 / 10.0  # = 0.5
        expected = raw * confidence + 0.5 * (1.0 - confidence)
        score = _reliability_score(delivery_rate=1.0, defect_rate=0.0, n=5)
        assert score == pytest.approx(expected)

    def test_delivery_weighted_higher_than_defect(self):
        from vocalmarket.services.intelligence.supplier_store import _reliability_score
        # Supplier A: perfect delivery, 20% defects
        # Supplier B: 80% delivery, no defects
        score_a = _reliability_score(1.0, 0.2, 20)
        score_b = _reliability_score(0.8, 0.0, 20)
        assert score_a > score_b  # delivery (60%) matters more than quality (40%)


class TestSupplierIntelligenceStore:
    """Integration-style tests using mocked DB session."""

    @pytest.mark.asyncio
    async def test_record_transaction_creates_metric(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from vocalmarket.services.intelligence.supplier_store import SupplierIntelligenceStore

        store = SupplierIntelligenceStore.__new__(SupplierIntelligenceStore)

        # Mock session that returns no existing metric (first record)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        store._session_factory = MagicMock(return_value=mock_cm)

        await store.record_transaction(
            order_id="order-001",
            supplier_id="sup-001",
            supplier_name="Acme Industries",
            vertical="b2b_procurement",
            order_value_cents=150_000,
            was_on_time=True,
            had_defect=False,
        )

        # session.add should have been called for TransactionRecord + metric(s) + profile
        assert mock_session.add.call_count >= 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_transaction_updates_existing_metric(self):
        from unittest.mock import AsyncMock, MagicMock
        from vocalmarket.services.intelligence.supplier_store import (
            SupplierIntelligenceStore,
            SupplierMetric,
        )

        store = SupplierIntelligenceStore.__new__(SupplierIntelligenceStore)

        existing_metric = MagicMock(spec=SupplierMetric)
        existing_metric.value = 0.8   # current delivery rate
        existing_metric.sample_count = 10
        existing_metric.metric_type = "delivery_rate"

        # First call (for metric) returns existing; subsequent calls return None
        call_count = [0]
        async def mock_execute(_q):
            r = MagicMock()
            call_count[0] += 1
            if call_count[0] == 2:  # second execute = metric lookup
                r.scalar_one_or_none.return_value = existing_metric
            else:
                r.scalar_one_or_none.return_value = None
            r.scalars.return_value.all.return_value = [existing_metric]
            return r

        mock_session = AsyncMock()
        mock_session.execute = mock_execute
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        store._session_factory = MagicMock(return_value=mock_cm)

        await store.record_transaction(
            order_id="order-002",
            supplier_id="sup-001",
            supplier_name="Acme Industries",
            vertical="b2b_procurement",
            order_value_cents=50_000,
            was_on_time=False,  # late delivery → pulls down the rate
            had_defect=False,
        )

        # Welford update: new_mean = 0.8 + (0.0 - 0.8) / 11 ≈ 0.727
        assert existing_metric.value == pytest.approx(0.8 + (0.0 - 0.8) / 11, rel=1e-3)
        assert existing_metric.sample_count == 11
