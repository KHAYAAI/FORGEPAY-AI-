# VocalMarket Messaging Service

Omnichannel ingress. Brings the VocalMarket AI assistant to six messaging channels,
all routed through a single `ConversationBridge` into the same AI orchestrator turn
that the voice and web clients use — same memory, same compliance, same supplier
intelligence.

```
Telegram ┐
WhatsApp ┤
SMS      ┤   ┌──────────────────┐   ┌───────────────────┐
Slack    ┼──▶│ ConversationBridge│──▶│  AI Orchestrator  │──▶ Hermes / Enthusiast
Teams    ┤   └──────────────────┘   └───────────────────┘
USSD     ┘        (channel-neutral)        (POST /chat)
```

## Channels

| Channel | Inbound webhook | Verification | Voice | Buttons |
|---------|-----------------|--------------|-------|---------|
| Telegram | `POST /channels/telegram/webhook` | `X-Telegram-Bot-Api-Secret-Token` | ✅ (voice notes → STT) | inline keyboard |
| WhatsApp (Meta Cloud API) | `GET`+`POST /channels/whatsapp/webhook` | `X-Hub-Signature-256` (HMAC-SHA256) | ⏳ media TODO | reply buttons (≤3) |
| SMS (Twilio) | `POST /channels/sms/webhook` | `X-Twilio-Signature` (HMAC-SHA1) | ❌ text only | bracketed hints |
| Slack | `POST /channels/slack/{events,commands}` | `X-Slack-Signature` (v0 HMAC-SHA256) | ❌ | Block Kit buttons |
| MS Teams | `POST /channels/teams/messages` | shared secret (JWT hook) | ❌ | suggestedActions |
| USSD (Africa's Talking) | `POST /channels/ussd` | gateway/IP allowlist | ❌ | numeric menu |

## Enabling a channel

Each channel self-enables when its credentials are present as environment variables —
no code deploy. Open `/console` to see which are live and the exact webhook URL to
register with each platform.

```bash
# Telegram
MESSAGING_TELEGRAM_BOT_TOKEN=123:abc
MESSAGING_TELEGRAM_WEBHOOK_SECRET=<random>

# WhatsApp (Meta Cloud API)
MESSAGING_WHATSAPP_ACCESS_TOKEN=...
MESSAGING_WHATSAPP_PHONE_NUMBER_ID=...
MESSAGING_WHATSAPP_APP_SECRET=...
MESSAGING_WHATSAPP_VERIFY_TOKEN=<random>

# SMS (Twilio)
MESSAGING_TWILIO_ACCOUNT_SID=AC...
MESSAGING_TWILIO_AUTH_TOKEN=...
MESSAGING_TWILIO_FROM_NUMBER=+27...

# Slack
MESSAGING_SLACK_BOT_TOKEN=xoxb-...
MESSAGING_SLACK_SIGNING_SECRET=...

# MS Teams
MESSAGING_TEAMS_APP_ID=...
MESSAGING_TEAMS_APP_PASSWORD=...
MESSAGING_TEAMS_INBOUND_SECRET=<random>

# USSD (Africa's Talking)
MESSAGING_USSD_SERVICE_CODE=*384*9000#
```

Shared:
```bash
MESSAGING_ORCHESTRATOR_URL=http://ai-orchestrator:8002
MESSAGING_PUBLIC_BASE_URL=https://msg.vocalmarket.ai
MESSAGING_DEFAULT_VERTICAL=grocery
MESSAGING_REDIS_URL=redis://redis:6379/3   # optional; in-memory fallback if unset
```

## Register the webhooks

```bash
# Telegram
curl "https://api.telegram.org/bot$TOKEN/setWebhook" \
  -d url=https://msg.vocalmarket.ai/channels/telegram/webhook \
  -d secret_token=$MESSAGING_TELEGRAM_WEBHOOK_SECRET

# WhatsApp / Slack / Teams / Twilio / Africa's Talking:
# paste the URL from /console into each platform's dashboard.
```

## How a turn flows

1. Adapter verifies the signature and parses the platform payload into `InboundMessage`.
2. `ConversationBridge` resolves the user's vertical (typed alias, menu choice, or
   stored session default) and maps the channel identity to a platform user id
   (`telegram:12345`, `whatsapp:27821234567`, …).
3. It POSTs one turn to the orchestrator `/chat` — identical to the voice service.
4. The `OutboundMessage` (text + product lines + suggested actions) is rendered into
   the channel's native format and sent back.

## Run locally

```bash
poetry install
uvicorn vocalmarket.services.messaging.src.main:app --port 8006 --reload
open http://localhost:8006/console
```

## Tests

```bash
pytest vocalmarket/services/messaging/tests -v
```
