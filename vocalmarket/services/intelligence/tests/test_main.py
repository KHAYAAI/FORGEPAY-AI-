"""
Tests for the Intelligence service's FastAPI endpoints
(vocalmarket/services/intelligence/main.py).

The store's DB-backed methods are replaced with a fake in-memory implementation
so these exercise request/response wiring — validation, status codes, query
param parsing — without needing a real Postgres+pgvector instance.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import vocalmarket.services.intelligence.main as main_module


class _FakeStore:
    def __init__(self):
        self.transactions: list[dict] = []
        self.rfq_responses: list[dict] = []
        self.registrations: list[dict] = []
        self._intelligence_response: list[dict] = []

    async def record_transaction(self, **kwargs):
        self.transactions.append(kwargs)

    async def record_rfq_response(self, **kwargs):
        self.rfq_responses.append(kwargs)

    async def register_supplier(self, **kwargs):
        self.registrations.append(kwargs)

    async def get_supplier_intelligence(self, **kwargs):
        return self._intelligence_response


@pytest.fixture()
def fake_store(monkeypatch):
    store = _FakeStore()

    async def _get_store():
        return store

    monkeypatch.setattr(main_module, "get_supplier_intelligence_store", _get_store)
    return store


@pytest.fixture()
def client(fake_store):
    return TestClient(main_module.app)


class TestRecordTransaction:
    def test_records_transaction_and_returns_201(self, client, fake_store):
        resp = client.post(
            "/internal/transactions",
            json={
                "order_id": "order_1",
                "supplier_id": "sup_1",
                "supplier_name": "Steel SA",
                "vertical": "b2b_procurement",
                "order_value_cents": 500_000,
                "was_on_time": True,
                "had_defect": False,
            },
        )
        assert resp.status_code == 201
        assert resp.json() == {"status": "recorded"}
        assert fake_store.transactions[0]["order_id"] == "order_1"
        assert fake_store.transactions[0]["was_on_time"] is True

    def test_rejects_missing_required_fields(self, client):
        resp = client.post("/internal/transactions", json={"order_id": "order_1"})
        assert resp.status_code == 422


class TestDeliveryOutcome:
    def test_records_outcome_with_defaults(self, client, fake_store):
        resp = client.post(
            "/suppliers/delivery-outcome",
            json={"order_id": "order_2", "supplier_id": "sup_2", "was_on_time": False, "had_defect": True},
        )
        assert resp.status_code == 200
        recorded = fake_store.transactions[0]
        assert recorded["vertical"] == "b2b_procurement"
        assert recorded["was_on_time"] is False
        assert recorded["had_defect"] is True


class TestRfqResponse:
    def test_records_rfq_response(self, client, fake_store):
        resp = client.post(
            "/internal/rfq-response",
            json={"supplier_id": "sup_1", "response_time_hours": 3.5, "was_accepted": True},
        )
        assert resp.status_code == 200
        assert fake_store.rfq_responses[0]["response_time_hours"] == 3.5


class TestSupplierIntelligence:
    def test_parses_comma_separated_supplier_ids(self, client, fake_store):
        fake_store._intelligence_response = [{"supplier_id": "sup_1", "reliability_score": 0.9}]

        resp = client.get("/suppliers/intelligence?supplier_ids=sup_1,%20sup_2&vertical=grocery")

        assert resp.status_code == 200
        assert resp.json() == {"suppliers": [{"supplier_id": "sup_1", "reliability_score": 0.9}]}

    def test_limit_is_capped_at_fifty(self, client, fake_store, monkeypatch):
        captured = {}

        async def fake_get(**kwargs):
            captured.update(kwargs)
            return []

        fake_store.get_supplier_intelligence = fake_get

        client.get("/suppliers/intelligence?limit=500")

        assert captured["limit"] == 50


class TestOnboardSupplier:
    def test_registers_supplier_and_echoes_id(self, client, fake_store):
        resp = client.post(
            "/suppliers/onboard",
            json={
                "supplier_id": "sup_9",
                "supplier_name": "Acme Fasteners",
                "vertical": "b2b_procurement",
                "description": "Precision fasteners.",
            },
        )
        assert resp.status_code == 201
        assert resp.json() == {"status": "registered", "supplier_id": "sup_9"}
        assert fake_store.registrations[0]["supplier_name"] == "Acme Fasteners"


class TestSupplierPortal:
    def test_serves_html_form(self, client):
        resp = client.get("/supplier-portal")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Supplier Onboarding" in resp.text


class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "service": "intelligence"}
