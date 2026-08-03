"""
Tests for the Supplier Intelligence Store's core algorithms
(vocalmarket/services/intelligence/supplier_store.py).

Focuses on the pure functions that drive "the data moat" — the running-average
metric updates and composite reliability score — plus the OpenAI embedding
fallback. The DB-backed async methods (record_transaction, discover_suppliers,
etc.) need a real Postgres+pgvector instance and aren't exercised here; they're
thin SQLAlchemy orchestration around these functions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vocalmarket.services.intelligence.supplier_store import (
    _build_capability_text,
    _embed_text,
    _reliability_score,
    _welford_update,
)


class TestWelfordUpdate:
    """Online running-mean update — must never require storing raw history."""

    def test_first_sample_becomes_the_mean(self):
        mean, n = _welford_update(old_mean=0.0, old_n=0, new_value=1.0)
        assert mean == 1.0
        assert n == 1

    def test_converges_toward_repeated_value(self):
        mean, n = 0.0, 0
        for _ in range(20):
            mean, n = _welford_update(mean, n, 1.0)
        assert mean == pytest.approx(1.0)
        assert n == 20

    def test_matches_simple_average_for_known_sequence(self):
        values = [1.0, 0.0, 1.0, 1.0]
        mean, n = 0.0, 0
        for v in values:
            mean, n = _welford_update(mean, n, v)
        assert mean == pytest.approx(sum(values) / len(values))
        assert n == len(values)

    def test_sample_count_always_increments_by_one(self):
        _, n1 = _welford_update(0.5, 7, 1.0)
        assert n1 == 8


class TestReliabilityScore:
    """Composite score: delivery 60% + quality 40%, confidence-discounted for low n."""

    def test_new_supplier_gets_neutral_score(self):
        assert _reliability_score(delivery_rate=1.0, defect_rate=0.0, n=0) == 0.5

    def test_perfect_supplier_with_full_confidence(self):
        score = _reliability_score(delivery_rate=1.0, defect_rate=0.0, n=10)
        assert score == pytest.approx(1.0)

    def test_worst_supplier_with_full_confidence(self):
        score = _reliability_score(delivery_rate=0.0, defect_rate=1.0, n=10)
        assert score == pytest.approx(0.0)

    def test_low_sample_count_pulls_score_toward_neutral(self):
        # A single perfect order shouldn't score as high as ten perfect orders.
        low_n_score = _reliability_score(delivery_rate=1.0, defect_rate=0.0, n=1)
        high_n_score = _reliability_score(delivery_rate=1.0, defect_rate=0.0, n=10)
        assert low_n_score < high_n_score
        assert low_n_score == pytest.approx(1.0 * 0.1 + 0.5 * 0.9)

    def test_confidence_caps_at_ten_samples(self):
        score_10 = _reliability_score(delivery_rate=0.8, defect_rate=0.1, n=10)
        score_100 = _reliability_score(delivery_rate=0.8, defect_rate=0.1, n=100)
        assert score_10 == pytest.approx(score_100)

    def test_delivery_weighted_more_than_quality(self):
        # Same distance from perfect, but on the delivery axis vs defect axis —
        # delivery failure should hurt the score more (60% vs 40% weight).
        late_but_no_defects = _reliability_score(delivery_rate=0.0, defect_rate=0.0, n=10)
        on_time_but_defective = _reliability_score(delivery_rate=1.0, defect_rate=1.0, n=10)
        assert late_but_no_defects < on_time_but_defective


class TestBuildCapabilityText:
    def test_includes_all_signals_for_semantic_embedding(self):
        text = _build_capability_text(
            name="Steel SA (Pty) Ltd",
            vertical="b2b_procurement",
            country="ZA",
            region="Gauteng",
            description="Precision steel fasteners for automotive OEMs.",
            certs=["ISO_9001", "IATF_16949"],
            lead_days=14,
            moq=500,
        )
        assert "Steel SA (Pty) Ltd" in text
        assert "b2b_procurement" in text
        assert "Gauteng, ZA" in text
        assert "ISO_9001, IATF_16949" in text
        assert "14 days" in text
        assert "500" in text
        assert "Precision steel fasteners" in text

    def test_handles_no_certifications(self):
        text = _build_capability_text(
            name="Acme", vertical="grocery", country="ZA", region="",
            description="Fresh produce.", certs=[], lead_days=1, moq=1,
        )
        assert "no certifications listed" in text


class TestEmbedText:
    @pytest.mark.asyncio
    async def test_returns_embedding_on_success(self):
        fake_response = MagicMock()
        fake_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        fake_client = MagicMock()
        fake_client.embeddings.create = AsyncMock(return_value=fake_response)

        fake_openai = MagicMock()
        fake_openai.AsyncOpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai}):
            result = await _embed_text("steel fasteners, ISO 9001, Gauteng")

        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure_instead_of_raising(self):
        fake_client = MagicMock()
        fake_client.embeddings.create = AsyncMock(side_effect=RuntimeError("rate limited"))

        fake_openai = MagicMock()
        fake_openai.AsyncOpenAI.return_value = fake_client

        with patch.dict("sys.modules", {"openai": fake_openai}):
            result = await _embed_text("steel fasteners")

        assert result is None
