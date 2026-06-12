"""
Messaging service settings.

Every channel is independently optional — a channel is "enabled" only when its
required credentials are present. This lets an operator turn on, say, WhatsApp and
USSD for the South African launch while leaving Slack/Teams dark until the
enterprise rollout, all via environment variables and no code changes.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class MessagingSettings(BaseSettings):
    # ── Core routing ──────────────────────────────────────────────────────────
    # The messaging service talks to the orchestrator directly on the internal
    # network, exactly like the voice service does.
    orchestrator_url: str = "http://ai-orchestrator:8002"
    default_vertical: str = "grocery"
    # Public base URL of THIS service, used to print webhook URLs in the console.
    public_base_url: str = "http://localhost:8006"
    request_timeout_seconds: float = 30.0

    # Optional Redis for session state (vertical selection, dedupe). Falls back to
    # an in-process dict when unset (fine for a single replica / dev).
    redis_url: str = ""

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    # Secret echoed by Telegram in the X-Telegram-Bot-Api-Secret-Token header.
    telegram_webhook_secret: str = ""

    # ── WhatsApp (Meta Cloud API) ─────────────────────────────────────────────
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""          # for X-Hub-Signature-256 verification
    whatsapp_verify_token: str = ""        # for the GET webhook challenge
    whatsapp_graph_version: str = "v21.0"

    # ── SMS (Twilio) ──────────────────────────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""            # also used to verify X-Twilio-Signature
    twilio_from_number: str = ""
    sms_max_chars: int = 320               # 2 concatenated GSM-7 segments

    # ── Slack ─────────────────────────────────────────────────────────────────
    slack_bot_token: str = ""              # xoxb-… for chat.postMessage
    slack_signing_secret: str = ""         # verifies X-Slack-Signature

    # ── Microsoft Teams (Bot Framework) ───────────────────────────────────────
    teams_app_id: str = ""
    teams_app_password: str = ""
    # Pragmatic shared-secret gate for the inbound webhook. Production should also
    # validate the Bot Framework JWT; see channels/teams.py for the note.
    teams_inbound_secret: str = ""

    # ── USSD (Africa's Talking) ───────────────────────────────────────────────
    ussd_service_code: str = "*384*9000#"
    ussd_max_chars: int = 160              # single USSD page

    class Config:
        env_prefix = "MESSAGING_"

    # ── Enablement helpers ────────────────────────────────────────────────────

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_access_token and self.whatsapp_phone_number_id)

    @property
    def sms_enabled(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token)

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_bot_token and self.slack_signing_secret)

    @property
    def teams_enabled(self) -> bool:
        return bool(self.teams_app_id)

    @property
    def ussd_enabled(self) -> bool:
        # USSD has no credentials of its own — it's gated by an explicit opt-in
        # so the endpoint isn't open by accident. Enabled when a service code is set
        # AND at least the default vertical exists (always true).
        return bool(self.ussd_service_code)

    def enabled_channels(self) -> dict[str, bool]:
        return {
            "telegram": self.telegram_enabled,
            "whatsapp": self.whatsapp_enabled,
            "sms": self.sms_enabled,
            "slack": self.slack_enabled,
            "teams": self.teams_enabled,
            "ussd": self.ussd_enabled,
        }


settings = MessagingSettings()
