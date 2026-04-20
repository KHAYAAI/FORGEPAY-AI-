"""
Tests for ForgePayClient and webhook signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import patch


class TestVerifyWebhookSignature:
    """HMAC-SHA256 webhook signature verification."""

    def _sign(self, payload: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def test_valid_signature(self):
        from vocalmarket.services.payments.src.forgepay import ForgePayClient

        client = ForgePayClient.__new__(ForgePayClient)
        payload = b'{"event":"payment.completed"}'
        secret = "test-webhook-secret"

        with patch(
            "vocalmarket.services.payments.src.forgepay._settings"
        ) as mock_settings:
            mock_settings.forgepay_webhook_secret = secret
            sig = self._sign(payload, secret)
            assert client.verify_webhook_signature(payload, sig)

    def test_invalid_signature(self):
        from vocalmarket.services.payments.src.forgepay import ForgePayClient

        client = ForgePayClient.__new__(ForgePayClient)
        payload = b'{"event":"payment.completed"}'
        secret = "test-webhook-secret"

        with patch(
            "vocalmarket.services.payments.src.forgepay._settings"
        ) as mock_settings:
            mock_settings.forgepay_webhook_secret = secret
            assert not client.verify_webhook_signature(payload, "wrong-signature")

    def test_tampered_payload(self):
        from vocalmarket.services.payments.src.forgepay import ForgePayClient

        client = ForgePayClient.__new__(ForgePayClient)
        original = b'{"event":"payment.completed","amount":100}'
        tampered = b'{"event":"payment.completed","amount":999}'
        secret = "test-webhook-secret"

        with patch(
            "vocalmarket.services.payments.src.forgepay._settings"
        ) as mock_settings:
            mock_settings.forgepay_webhook_secret = secret
            sig = self._sign(original, secret)
            assert not client.verify_webhook_signature(tampered, sig)
