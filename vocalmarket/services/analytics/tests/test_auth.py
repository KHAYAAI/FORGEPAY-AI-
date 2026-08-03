"""
Tests for the Analytics API's key-based auth
(vocalmarket/services/analytics/main.py).

This is the only gate between "paying customer" and "open access to
cross-org supplier data" for this service, so it's tested directly rather
than only via the DB-backed endpoints (which need a real Postgres instance
and are thin SQLAlchemy query builders around this auth layer).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from vocalmarket.services.analytics.main import AnalyticsSettings, require_api_key


class TestValidKeysParsing:
    def test_parses_comma_separated_keys(self):
        settings = AnalyticsSettings(api_keys="key-one, key-two,key-three")
        assert settings.valid_keys() == {"key-one", "key-two", "key-three"}

    def test_empty_string_yields_no_keys(self):
        settings = AnalyticsSettings(api_keys="")
        assert settings.valid_keys() == set()

    def test_drops_blank_entries(self):
        settings = AnalyticsSettings(api_keys="key-one,,  ,")
        assert settings.valid_keys() == {"key-one"}


class TestRequireApiKey:
    @pytest.mark.asyncio
    async def test_dev_mode_allows_access_with_no_key_when_none_configured(self, monkeypatch):
        import vocalmarket.services.analytics.main as module

        monkeypatch.setattr(module, "_settings", AnalyticsSettings(api_keys=""))

        result = await require_api_key(api_key=None)

        assert result == "dev"

    @pytest.mark.asyncio
    async def test_valid_key_is_accepted(self, monkeypatch):
        import vocalmarket.services.analytics.main as module

        monkeypatch.setattr(module, "_settings", AnalyticsSettings(api_keys="valid-key"))

        result = await require_api_key(api_key="valid-key")

        assert result == "valid-key"

    @pytest.mark.asyncio
    async def test_missing_key_rejected_when_keys_are_configured(self, monkeypatch):
        import vocalmarket.services.analytics.main as module

        monkeypatch.setattr(module, "_settings", AnalyticsSettings(api_keys="valid-key"))

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_rejected_when_keys_are_configured(self, monkeypatch):
        import vocalmarket.services.analytics.main as module

        monkeypatch.setattr(module, "_settings", AnalyticsSettings(api_keys="valid-key"))

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="wrong-key")
        assert exc_info.value.status_code == 401


class TestHealth:
    def test_health_endpoint_does_not_require_auth(self):
        from fastapi.testclient import TestClient
        from vocalmarket.services.analytics.main import app

        resp = TestClient(app).get("/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "service": "analytics"}
