"""
Prescription store — verifies that a user has a valid verified prescription
for a given product SKU before allowing an order to proceed.

Prescriptions are stored in the vocalmarket.prescriptions table and are
written by the prescription upload flow (OCR → pharmacist review → approval).

Data is stored with field-level encryption (Fernet symmetric key) so sensitive
medical data is never stored in plaintext, satisfying POPIA section 22 requirements.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from cryptography.fernet import Fernet
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from sqlalchemy import String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column

logger = logging.getLogger(__name__)


class PrescriptionSettings(BaseSettings):
    prescription_db_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/vocalmarket"
    # Fernet key for field-level encryption. Generate with: Fernet.generate_key()
    prescription_encryption_key: str = ""

    class Config:
        env_prefix = "HEALTHCARE_"


_settings = PrescriptionSettings()


class Base(DeclarativeBase):
    # Columns below are declared as `Any = mapped_column(...)` rather than
    # `Mapped[...]` — SQLAlchemy 2.0's declarative mapper rejects that without
    # this flag (MappedAnnotationError), which otherwise breaks import of
    # this module entirely under the sqlalchemy = "^2.0" pin in pyproject.toml.
    __allow_unmapped__ = True


class Prescription(Base):
    """One verified prescription entry."""

    __tablename__ = "prescriptions"
    __table_args__ = {"schema": "vocalmarket"}

    id: Any = mapped_column(String(64), primary_key=True)
    user_id: Any = mapped_column(String(128), index=True, nullable=False)
    # Encrypted product SKU / INN (international non-proprietary name)
    encrypted_medication: Any = mapped_column(Text, nullable=False)
    encrypted_prescriber: Any = mapped_column(Text, nullable=False)
    # ISO date strings stored as text (encrypted)
    encrypted_issue_date: Any = mapped_column(Text, nullable=False)
    encrypted_expiry_date: Any = mapped_column(Text, nullable=False)
    verified_at: Any = mapped_column(String(32))  # ISO timestamp; null = pending
    revoked: Any = mapped_column(String(8), default="false")


class PrescriptionVerification(BaseModel):
    is_valid: bool
    reason: str
    prescription_id: str | None = None
    expiry_date: date | None = None


class PrescriptionStore:
    """
    Async store for prescription verification.

    All sensitive fields are encrypted at rest using Fernet symmetric encryption.
    """

    def __init__(self) -> None:
        self._engine = create_async_engine(_settings.prescription_db_url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._fernet = (
            Fernet(_settings.prescription_encryption_key.encode())
            if _settings.prescription_encryption_key
            else None
        )

    async def initialise(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS vocalmarket"))
            await conn.run_sync(Base.metadata.create_all)

    async def verify_for_product(
        self, user_id: str, product_sku: str
    ) -> PrescriptionVerification:
        """
        Check if user_id has a valid, non-expired, non-revoked prescription
        covering product_sku.
        """
        if not _settings.prescription_encryption_key:
            logger.error(
                "HEALTHCARE_PRESCRIPTION_ENCRYPTION_KEY not set — "
                "prescription verification is DISABLED. Do not run in production."
            )
            return PrescriptionVerification(
                is_valid=False,
                reason="Prescription verification is not configured on this server.",
            )

        async with self._session_factory() as session:
            # Load all active prescriptions for this user
            result = await session.execute(
                select(Prescription).where(
                    Prescription.user_id == user_id,
                    Prescription.revoked == "false",
                    Prescription.verified_at.is_not(None),
                )
            )
            prescriptions = result.scalars().all()

        today = date.today()
        for rx in prescriptions:
            try:
                medication = self._decrypt(rx.encrypted_medication)
                expiry_str = self._decrypt(rx.encrypted_expiry_date)
                expiry = date.fromisoformat(expiry_str)
            except Exception as e:
                logger.warning("Failed to decrypt prescription %s: %s", rx.id, e)
                continue

            # Match by SKU or INN (case-insensitive prefix match)
            if not (
                product_sku.lower() in medication.lower()
                or medication.lower() in product_sku.lower()
            ):
                continue

            if expiry < today:
                return PrescriptionVerification(
                    is_valid=False,
                    reason=f"Your prescription for this medication expired on {expiry}. "
                    "Please obtain a new prescription from your healthcare provider.",
                    prescription_id=rx.id,
                    expiry_date=expiry,
                )

            return PrescriptionVerification(
                is_valid=True,
                reason="Valid prescription on file.",
                prescription_id=rx.id,
                expiry_date=expiry,
            )

        return PrescriptionVerification(
            is_valid=False,
            reason="No valid prescription found for this medication. "
            "Please upload a prescription or contact your healthcare provider.",
        )

    def _decrypt(self, value: str) -> str:
        if self._fernet is None:
            raise RuntimeError("Encryption key not configured")
        return self._fernet.decrypt(value.encode()).decode()

    async def aclose(self) -> None:
        await self._engine.dispose()


# Module-level singleton — initialised lazily on first use
_store: PrescriptionStore | None = None


async def get_prescription_store() -> PrescriptionStore:
    global _store
    if _store is None:
        _store = PrescriptionStore()
        await _store.initialise()
    return _store
