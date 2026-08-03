# VocalMarket AI — Go-Live Checklist

This tracks what's needed to take real, paying customers. It's split into two
kinds of work:

- **Code work** — anything an engineer (or an AI agent with repo access) can
  do. Most of this is now done; what's left is listed under [Remaining code
  work](#remaining-code-work).
- **Provisioning work** — external accounts, API keys, and infrastructure
  decisions that only someone with billing/ownership authority over this
  business can do. No agent can create a merchant account or an AWS org on
  your behalf. This is listed under [External accounts & keys
  needed](#external-accounts--keys-needed).

## What changed in this pass

Building toward "first real customers" surfaced several bugs that would have
blocked launch even after all accounts were provisioned. All were found by
actually exercising the code (not just reading it) and are now fixed, with
regression tests:

- **Intelligence, Analytics, and the V2 Hermes AI layer could not start at
  all.** All three define SQLAlchemy models using `Any = mapped_column(...)`
  columns, which SQLAlchemy 2.0's declarative mapper rejects
  (`MappedAnnotationError`) unless `__allow_unmapped__ = True` is set on the
  base class. Under the `sqlalchemy = "^2.0"` pin already in each service's
  `pyproject.toml`, every one of these modules raised on import. Fixed in
  `services/intelligence/supplier_store.py`, `services/analytics/main.py`,
  and `ai/hermes/memory/store.py`.
- **The healthcare compliance module (prescription verification) could not
  import at all** — `ai/verticals/healthcare/prescription_store.py` imported
  `Any` from `sqlalchemy.types` instead of `typing`, plus the same
  `__allow_unmapped__` issue. This meant the POPIA-compliant prescription
  gate was completely non-functional, and its test file couldn't even
  collect (missing `import pytest`), so this had never been caught.
- **The voice service crashed on every normal client disconnect.** Starlette
  returns a disconnect event as a plain message from `websocket.receive()`
  rather than raising `WebSocketDisconnect` (that only happens on the
  `receive_text()`/`receive_bytes()`/`receive_json()` wrappers), so the
  session loop called `receive()` again on an already-closed socket and threw
  `RuntimeError` — on every single voice session ending normally. Fixed in
  `services/voice/src/service.py`.
- **`/v1/payments/...` requests would have silently gone to the AI
  orchestrator instead of the payments service** — the gateway's
  `/v1/{vertical}/{path}` catch-all route was registered first, so it would
  have matched with `vertical="payments"` before a dedicated payments route
  ever got a chance. Fixed by registering the payments proxy route first in
  `services/api_gateway/src/main.py`, with a regression test guarding the
  ordering.
- **Checkout was entirely simulated** (`setTimeout` + instant "success") —
  the web app now calls a real ForgePay payment session through the gateway
  (`POST /v1/payments/initiate`), with a network-failure fallback to the
  simulated flow so local dev still works without the full microservices
  stack running.
- **The web app's TypeScript build had real gaps**, not just cosmetic
  warnings: `@types/node` was never installed (so `vite.config.ts` itself
  didn't type-check), and there was no `vite-env.d.ts`, so every
  `import.meta.env.VITE_*` access needed an unsafe manual cast. Both fixed;
  `tsc -b --noEmit` is now clean.

Every Python service now has a test suite (123 tests total across
`ai_orchestrator`, `api_gateway`, `voice`, `intelligence`, `analytics`,
`messaging`, and the root `vocalmarket/tests/`), and
`.github/workflows/vocalmarket-tests.yml` runs all of them plus the web
app's typecheck and vitest suite on every push/PR touching `vocalmarket/**`
— so none of the above can silently regress again.

## External accounts & keys needed

Nothing below can be done by an agent — these require your own accounts,
billing relationships, and business decisions.

### Required for any launch

| # | What | Why | Where |
|---|------|-----|-------|
| 1 | An LLM provider key (OpenAI, Azure OpenAI, Google, Mistral, or Anthropic) | Powers every Enthusiast agent (product search, order intake) | Plugin already exists for each in `plugins/enthusiast-model-*` — pick one and set its key |
| 2 | ElevenLabs API key | TTS voice replies | `VOICE_ELEVENLABS_API_KEY` |
| 3 | ForgePay merchant account, API key, webhook secret | Card & stablecoin payments | `FORGEPAY_API_KEY`, `FORGEPAY_WEBHOOK_SECRET`. If ForgePay is your own product rather than a third party, confirm the production base URL in `services/payments/src/forgepay.py` (currently `https://api.forgepay.io/v1`) |
| 4 | Medusa.js instance, seeded with a real product catalog | Order/commerce engine of record | Self-hosted (`docker-compose.vocalmarket.yml` runs it), but the catalog is currently just mock data in `apps/web/src/data/products.ts` — needs real products imported into Medusa |
| 5 | PostgreSQL with the `pgvector` extension available | Shared DB for Enthusiast + all microservices | RDS via Terraform, or self-hosted `pgvector/pgvector` image |
| 6 | Redis | Celery broker, session state, gateway caching | |
| 7 | A domain + TLS certificate (ACM or otherwise) | Production ingress | `infra/k8s/base` has an `ACM_CERT_ARN` placeholder in the Ingress — needs a real cert once you have a domain |
| 8 | Cloud account (AWS, per the existing Terraform) | RDS, Secrets Manager, hosting for K8s | `infra/terraform/` provisions RDS + Secrets Manager; you still need to `terraform apply` against a real account and wire the K8s cluster it deploys to |

### Vertical-specific / optional

| What | Why | Where |
|------|-----|-------|
| OpenAI key for the Intelligence service | Supplier-discovery semantic search embeddings — falls back to keyword search if unset | `INTELLIGENCE_OPENAI_API_KEY` |
| Telegram bot token + Payments provider token | Telegram channel + in-chat checkout | Create via @BotFather |
| WhatsApp Business (Meta Cloud API) credentials | WhatsApp channel | Meta App dashboard |
| Twilio account SID/token/number | SMS channel | Twilio console |
| Slack bot token + signing secret | Slack channel | Slack app with Event Subscriptions |
| Azure Bot registration | Microsoft Teams channel | |
| Africa's Talking service code | USSD (feature-phone) access | |
| Legal/compliance review for the Healthcare vertical | Field-level Fernet encryption satisfies POPIA §22 at the code level, but launching healthcare needs an actual legal sign-off, not just encrypted columns | Not a code task |

### Missing entirely — needs sourcing

- **A delivery/courier API.** The Grocery vertical's whole pitch is
  Gopuff-style delivery in minutes, but there is no courier/dispatch
  integration anywhere in `vocalmarket/services/` — no Uber Direct, no
  regional courier aggregator, no in-house dispatch. This needs a vendor
  decision before Grocery can actually fulfill an order end to end.

## Remaining code work

Roughly in the order it blocks a real checkout:

1. **Wire the web Shop page to Medusa's real catalog** instead of the
   hardcoded `apps/web/src/data/products.ts`. Once products exist in Medusa
   (see item 4 above), replace the mock catalog with calls to Medusa's Store
   API.
2. **Persist orders through Medusa's cart → order flow** before payment
   initiation. Right now `checkout.tsx` generates a client-side
   `order_id` (`web_${Date.now()}`) and goes straight to ForgePay — there's
   no real Medusa cart/order behind it yet, so the ForgePay webhook's
   `_on_payment_completed` handler (which fetches the order from Medusa to
   confirm/capture it) has nothing real to confirm. This is the biggest
   remaining gap between "payment session" and "fulfilled order."
3. **Delivery dispatch integration**, once a courier vendor is chosen (see
   above) — triggered from the same `payment.completed` webhook path that
   already records supplier/delivery metrics in the Intelligence service.
4. **Mobile app** (`apps/mobile/`) is a skeleton — one screen and a voice
   button component, no auth, no navigation stack, no cart. Not
   launch-ready by any measure; treat as a separate build.
5. **Populate production secrets.** `infra/k8s/base/secrets.yaml` references
   `ExternalSecrets` pointing at AWS Secrets Manager, and Terraform
   provisions the Secrets Manager entries, but nothing is populated with
   real values yet — this is the last step after every account above is
   provisioned.
6. **GPU node for self-hosted Whisper**, or swap to a hosted STT API. The
   `whisper` service in `docker-compose.vocalmarket.yml` requests an NVIDIA
   GPU (`large-v3` model) — this is a real infra cost and a placement
   constraint on whichever cluster runs it. If that's not worth it before
   revenue, `services/voice/src/stt.py` is already written against the
   OpenAI-compatible `/v1/audio/transcriptions` shape, so pointing
   `VOICE_WHISPER_BASE_URL` at a hosted Whisper API instead is a
   config-only change.
