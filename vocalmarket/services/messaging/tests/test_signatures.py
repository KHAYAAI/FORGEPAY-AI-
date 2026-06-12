"""Signature verification is the security boundary — exercise each algorithm."""

import base64
import hashlib
import hmac
import time

from vocalmarket.services.messaging.src.channels.base import (
    verify_meta_signature,
    verify_slack_signature,
    verify_telegram_secret,
    verify_twilio_signature,
)


def test_meta_signature_roundtrip():
    secret = "app_secret_123"
    body = b'{"entry":[]}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_meta_signature(secret, body, sig)
    assert not verify_meta_signature(secret, body, "sha256=deadbeef")
    assert not verify_meta_signature(secret, body, None)
    assert not verify_meta_signature("", body, sig)


def test_slack_signature_roundtrip_and_replay():
    secret = "slack_signing_secret"
    body = b"token=x&text=hello"
    ts = str(int(time.time()))
    base = b"v0:" + ts.encode() + b":" + body
    sig = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    assert verify_slack_signature(secret, body, ts, sig)

    # Stale timestamp is rejected (replay protection).
    old_ts = str(int(time.time()) - 10_000)
    old_base = b"v0:" + old_ts.encode() + b":" + body
    old_sig = "v0=" + hmac.new(secret.encode(), old_base, hashlib.sha256).hexdigest()
    assert not verify_slack_signature(secret, body, old_ts, old_sig)


def test_twilio_signature_roundtrip():
    token = "twilio_auth_token"
    url = "https://msg.example.com/channels/sms/webhook"
    params = {"From": "+27820001111", "Body": "hi there", "MessageSid": "SM123"}
    data = url + "".join(k + params[k] for k in sorted(params))
    expected = base64.b64encode(
        hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()
    ).decode()
    assert verify_twilio_signature(token, url, params, expected)
    assert not verify_twilio_signature(token, url, params, "wrong")


def test_telegram_secret():
    assert verify_telegram_secret("s3cr3t", "s3cr3t")
    assert not verify_telegram_secret("s3cr3t", "nope")
    assert not verify_telegram_secret("s3cr3t", None)
    # No secret configured → accept (dev mode).
    assert verify_telegram_secret("", None)
