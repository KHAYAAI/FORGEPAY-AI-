"""
VocalMarket Messaging Service — omnichannel ingress.

One FastAPI app that fans every supported channel (Telegram, WhatsApp, SMS, Slack,
Teams, USSD) into a single `ConversationBridge`, which runs the same AI orchestrator
turn the voice and web clients use. Channels self-enable based on which credentials
are present, so an operator turns each one on purely via environment variables.

Endpoints:
  /channels/<name>/...   channel webhooks (mounted only when the channel is enabled)
  /console               admin console: channel status + webhook URLs to register
  /channels              JSON status of every channel
  /health                liveness
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .bridge import ConversationBridge
from .channels.sms import SMSAdapter
from .channels.slack import SlackAdapter
from .channels.teams import TeamsAdapter
from .channels.telegram import TelegramAdapter
from .channels.ussd import USSDAdapter
from .channels.whatsapp import WhatsAppAdapter
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("messaging")

# Map channel name → (adapter class, enabled flag). USSD and the bridge are always
# constructed; the webhook is only mounted when the channel is enabled.
_ADAPTER_CLASSES = {
    "telegram": TelegramAdapter,
    "whatsapp": WhatsAppAdapter,
    "sms": SMSAdapter,
    "slack": SlackAdapter,
    "teams": TeamsAdapter,
    "ussd": USSDAdapter,
}

_bridge: ConversationBridge | None = None
_adapters: dict[str, object] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bridge
    _bridge = ConversationBridge()
    enabled = settings.enabled_channels()
    for name, cls in _ADAPTER_CLASSES.items():
        if not enabled.get(name):
            continue
        adapter = cls(_bridge)
        _adapters[name] = adapter
        app.include_router(adapter.router())
        logger.info("Channel enabled: %s", name)

    if not _adapters:
        logger.warning("No channels enabled — set channel credentials to activate webhooks.")

    yield

    for adapter in _adapters.values():
        aclose = getattr(adapter, "aclose", None)
        if aclose:
            await aclose()
    if _bridge:
        await _bridge.aclose()


app = FastAPI(title="VocalMarket Messaging Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "messaging", "channels": settings.enabled_channels()}


@app.get("/channels")
async def channels():
    """Machine-readable channel status + the webhook URL each platform must call."""
    base = settings.public_base_url.rstrip("/")
    enabled = settings.enabled_channels()
    return {
        "channels": [
            {
                "name": name,
                "enabled": enabled[name],
                "webhook_url": base + _WEBHOOK_PATHS[name],
                "method": _WEBHOOK_METHODS[name],
            }
            for name in _ADAPTER_CLASSES
        ]
    }


_WEBHOOK_PATHS = {
    "telegram": "/channels/telegram/webhook",
    "whatsapp": "/channels/whatsapp/webhook",
    "sms": "/channels/sms/webhook",
    "slack": "/channels/slack/events",
    "teams": "/channels/teams/messages",
    "ussd": "/channels/ussd",
}
_WEBHOOK_METHODS = {
    "telegram": "POST",
    "whatsapp": "GET+POST",
    "sms": "POST",
    "slack": "POST",
    "teams": "POST",
    "ussd": "POST",
}

_CHANNEL_META = {
    "telegram": ("Telegram", "Set webhook via setWebhook with your bot token + secret."),
    "whatsapp": ("WhatsApp Business", "Meta Cloud API. Configure webhook + verify token in the Meta app dashboard."),
    "sms": ("SMS", "Twilio. Point your number's Messaging webhook here."),
    "slack": ("Slack", "Slack app: Event Subscriptions + Slash Command request URLs."),
    "teams": ("Microsoft Teams", "Azure Bot: set the Messaging endpoint to this URL."),
    "ussd": ("USSD", "Africa's Talking: set the USSD callback URL to this endpoint."),
}


@app.get("/console", response_class=HTMLResponse)
async def console():
    """
    Channel operations console.

    A production-styled admin surface (matching the polish of the Enthusiast admin
    UI) that shows, at a glance, which channels are live and the exact webhook URL to
    register with each platform. This is what an operator opens to wire up a channel.
    """
    base = settings.public_base_url.rstrip("/")
    enabled = settings.enabled_channels()
    rows = []
    for name in _ADAPTER_CLASSES:
        label, hint = _CHANNEL_META[name]
        on = enabled[name]
        status = (
            '<span class="badge on">● live</span>'
            if on
            else '<span class="badge off">○ not configured</span>'
        )
        webhook = base + _WEBHOOK_PATHS[name]
        rows.append(
            f"""
            <tr>
              <td><strong>{label}</strong><div class="hint">{hint}</div></td>
              <td>{status}</td>
              <td><code class="url">{webhook}</code>
                  <span class="method">{_WEBHOOK_METHODS[name]}</span></td>
            </tr>"""
        )
    live = sum(1 for v in enabled.values() if v)
    return HTMLResponse(_CONSOLE_HTML.replace("{{ROWS}}", "".join(rows)).replace("{{LIVE}}", str(live)))


_CONSOLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VocalMarket — Channel Console</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #0b0d12; color: #e6e8ee; margin: 0; padding: 2.5rem 1.5rem; }
    .wrap { max-width: 920px; margin: 0 auto; }
    h1 { font-size: 1.6rem; margin: 0 0 0.25rem; }
    .sub { color: #8b91a3; margin: 0 0 2rem; font-size: 0.92rem; }
    .summary { display: inline-block; background: #151923; border: 1px solid #232838; border-radius: 10px; padding: 0.6rem 1rem; margin-bottom: 1.5rem; font-size: 0.9rem; }
    .summary b { color: #5b9dff; }
    table { width: 100%; border-collapse: collapse; background: #11141c; border: 1px solid #232838; border-radius: 12px; overflow: hidden; }
    th, td { text-align: left; padding: 1rem 1.1rem; border-bottom: 1px solid #1d2230; vertical-align: top; }
    th { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: #6f7689; background: #0e1118; }
    tr:last-child td { border-bottom: none; }
    .hint { color: #6f7689; font-size: 0.78rem; margin-top: 0.3rem; max-width: 320px; }
    .badge { font-size: 0.82rem; font-weight: 600; white-space: nowrap; }
    .badge.on { color: #3ddc84; }
    .badge.off { color: #6f7689; }
    code.url { display: inline-block; background: #0e1118; border: 1px solid #232838; border-radius: 6px; padding: 0.35rem 0.55rem; font-size: 0.8rem; color: #cdd3e1; word-break: break-all; }
    .method { display: inline-block; margin-left: 0.5rem; font-size: 0.68rem; color: #8b91a3; border: 1px solid #232838; border-radius: 4px; padding: 0.15rem 0.4rem; }
    footer { margin-top: 2rem; color: #565c6e; font-size: 0.8rem; }
  </style>
</head>
<body>
<div class="wrap">
  <h1>Channel Console</h1>
  <p class="sub">Omnichannel ingress for the VocalMarket assistant. Every channel below routes into the same AI orchestrator, memory, and compliance pipeline.</p>
  <div class="summary"><b>{{LIVE}}</b> of 6 channels live</div>
  <table>
    <thead><tr><th>Channel</th><th>Status</th><th>Webhook URL to register</th></tr></thead>
    <tbody>{{ROWS}}</tbody>
  </table>
  <footer>A channel goes live automatically once its credentials are set as environment variables. No code deploy required.</footer>
</div>
</body>
</html>"""
