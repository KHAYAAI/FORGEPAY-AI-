"""
Tests for PrescriptionStore verification logic.

Uses an in-memory SQLite database to avoid requiring a real PostgreSQL instance.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import MagicMock, patch


def _fernet_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def _encrypt(key: str, value: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(key.encode()).encrypt(value.encode()).decode()


class TestPrescriptionVerification:
    """Unit tests for PrescriptionStore.verify_for_product()."""

    @pytest.mark.asyncio
    async def test_no_encryption_key_returns_invalid(self):
        from vocalmarket.ai.verticals.healthcare.prescription_store import PrescriptionStore

        store = PrescriptionStore.__new__(PrescriptionStore)
        store._fernet = None
        store._session_factory = None

        with patch(
            "vocalmarket.ai.verticals.healthcare.prescription_store._settings"
        ) as mock_settings:
            mock_settings.prescription_encryption_key = ""
            result = await store.verify_for_product("user-1", "amoxicillin-500mg")

        assert not result.is_valid
        assert "not configured" in result.reason

    @pytest.mark.asyncio
    async def test_valid_prescription_accepted(self):
        from vocalmarket.ai.verticals.healthcare.prescription_store import (
            Prescription,
            PrescriptionStore,
            PrescriptionVerification,
        )

        key = _fernet_key()
        today = date.today()
        expiry = today + timedelta(days=30)

        rx = MagicMock(spec=Prescription)
        rx.id = "rx-001"
        rx.user_id = "user-1"
        rx.revoked = "false"
        rx.verified_at = "2026-01-01T10:00:00"
        rx.encrypted_medication = _encrypt(key, "amoxicillin")
        rx.encrypted_prescriber = _encrypt(key, "Dr Smith")
        rx.encrypted_issue_date = _encrypt(key, today.isoformat())
        rx.encrypted_expiry_date = _encrypt(key, expiry.isoformat())

        store = PrescriptionStore.__new__(PrescriptionStore)
        store._fernet = __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet(key.encode())

        # Mock the DB session to return our fake prescription
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [rx]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = MagicMock()
        mock_session.execute = asyncio.coroutine(lambda _: mock_result) if False else MagicMock(
            return_value=asyncio.coroutine(lambda: mock_result)()
        )

        # Use AsyncMock for the async context manager
        from unittest.mock import AsyncMock
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=mock_result)

        store._session_factory = MagicMock(return_value=mock_session_cm)

        with patch(
            "vocalmarket.ai.verticals.healthcare.prescription_store._settings"
        ) as mock_settings:
            mock_settings.prescription_encryption_key = key
            result = await store.verify_for_product("user-1", "amoxicillin-500mg")

        assert result.is_valid
        assert result.prescription_id == "rx-001"
        assert result.expiry_date == expiry

    @pytest.mark.asyncio
    async def test_expired_prescription_rejected(self):
        from vocalmarket.ai.verticals.healthcare.prescription_store import (
            Prescription,
            PrescriptionStore,
        )
        from unittest.mock import AsyncMock

        key = _fernet_key()
        today = date.today()
        expired = today - timedelta(days=1)

        rx = MagicMock(spec=Prescription)
        rx.id = "rx-002"
        rx.encrypted_medication = _encrypt(key, "amoxicillin")
        rx.encrypted_expiry_date = _encrypt(key, expired.isoformat())

        store = PrescriptionStore.__new__(PrescriptionStore)
        store._fernet = __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet(key.encode())

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [rx]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        store._session_factory = MagicMock(return_value=mock_session_cm)

        with patch(
            "vocalmarket.ai.verticals.healthcare.prescription_store._settings"
        ) as mock_settings:
            mock_settings.prescription_encryption_key = key
            result = await store.verify_for_product("user-1", "amoxicillin-500mg")

        assert not result.is_valid
        assert "expired" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_sku_mismatch_returns_not_found(self):
        from vocalmarket.ai.verticals.healthcare.prescription_store import (
            Prescription,
            PrescriptionStore,
        )
        from unittest.mock import AsyncMock

        key = _fernet_key()
        expiry = date.today() + timedelta(days=30)

        rx = MagicMock(spec=Prescription)
        rx.id = "rx-003"
        rx.encrypted_medication = _encrypt(key, "ibuprofen")
        rx.encrypted_expiry_date = _encrypt(key, expiry.isoformat())

        store = PrescriptionStore.__new__(PrescriptionStore)
        store._fernet = __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet(key.encode())

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [rx]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)
        store._session_factory = MagicMock(return_value=mock_session_cm)

        with patch(
            "vocalmarket.ai.verticals.healthcare.prescription_store._settings"
        ) as mock_settings:
            mock_settings.prescription_encryption_key = key
            result = await store.verify_for_product("user-1", "amoxicillin-500mg")

        assert not result.is_valid
        assert "no valid prescription" in result.reason.lower()


import pytest
