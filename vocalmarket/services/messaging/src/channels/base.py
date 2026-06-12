"""
Shared primitives for channel adapters.

Each adapter is a small class that:
  1. Exposes an APIRouter with the channel's inbound webhook(s).
  2. Verifies the request signature (so only the real platform can post to us).
  3. Parses the payload into an `InboundMessage`.
  4. Runs the shared `ConversationBridge`.
  5. Renders the `OutboundMessage` back into the channel's native format and sends it.

The signature helpers here implement the exact algorithms each platform documents,
so they double as a security reference.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time


def hmac_sha256_hex(secret: str, body: bytes) -> str:
    """Hex HMAC-SHA256 — used by Meta (WhatsApp) and Slack."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_meta_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """
    WhatsApp Cloud API / Meta: X-Hub-Signature-256: 'sha256=<hex>'.
    HMAC-SHA256 of the raw request body keyed by the app secret.
    """
    if not app_secret or not header:
        return False
    expected = "sha256=" + hmac_sha256_hex(app_secret, body)
    return hmac.compare_digest(expected, header)


def verify_slack_signature(
    signing_secret: str,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    max_skew_seconds: int = 300,
) -> bool:
    """
    Slack: X-Slack-Signature: 'v0=<hex>' over f"v0:{timestamp}:{body}".
    Rejects stale timestamps to prevent replay.
    """
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > max_skew_seconds:
            return False
    except ValueError:
        return False
    basestring = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac_sha256_hex(signing_secret, basestring)
    return hmac.compare_digest(expected, signature)


def verify_twilio_signature(
    auth_token: str,
    url: str,
    params: dict[str, str],
    signature: str | None,
) -> bool:
    """
    Twilio: X-Twilio-Signature is base64(HMAC-SHA1(auth_token, url + sorted params)).
    The signed string is the full request URL followed by each POST param name and
    value concatenated in alphabetical order by key.
    """
    if not auth_token or not signature:
        return False
    data = url
    for key in sorted(params):
        data += key + params[key]
    digest = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


def verify_telegram_secret(expected: str, header: str | None) -> bool:
    """
    Telegram: the secret set on setWebhook is echoed in
    X-Telegram-Bot-Api-Secret-Token. Constant-time compare.
    """
    if not expected:
        return True  # no secret configured → accept (dev)
    if not header:
        return False
    return hmac.compare_digest(expected, header)
