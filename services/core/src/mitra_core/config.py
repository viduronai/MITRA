"""Application settings, read from environment variables (prefix ``MITRA_``) or a ``.env`` file."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

_DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me-0123456789"  # noqa: S105
_DEV_PHONE_HASH_KEY = "dev-only-insecure-phone-hash-key-change-me"
_DEV_OTP_HASH_KEY = "dev-only-insecure-otp-hash-key-change-me"
_DEV_SERVICE_TOKEN = "dev-only-insecure-service-token-change-me"  # noqa: S105
_ROLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MITRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["local", "test", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"

    # The API connects as a NON-superuser role so Postgres RLS applies to every query.
    database_url: str = "postgresql+asyncpg://mitra_app:mitra_app_dev_password@localhost:5433/mitra"
    # Migrations run as the schema owner. The migration also creates/updates the app role using
    # the username + password embedded in ``database_url`` (single source of truth).
    migration_database_url: str = (
        "postgresql+asyncpg://mitra:mitra_dev_password@localhost:5433/mitra"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # Temporary HS256 auth; replaced by Better Auth-issued tokens later (TRD §3).
    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "mitra-dev"
    jwt_audience: str = "mitra-core"
    access_token_ttl_seconds: int = 12 * 3600

    # Phone OTP login (dev: the code is returned in the response when env=local).
    otp_hash_key: SecretStr = SecretStr(_DEV_OTP_HASH_KEY)
    otp_ttl_seconds: int = 300
    otp_resend_seconds: int = 30
    otp_max_attempts: int = 5
    otp_max_requests: int = 3
    otp_window_seconds: int = 600

    # Public "Call me now" demo calls from the marketing site (per phone, then per client IP).
    demo_call_max_per_phone: int = 2
    demo_call_phone_window_seconds: int = 24 * 3600
    demo_call_max_per_ip: int = 5
    demo_call_ip_window_seconds: int = 3600

    # Browser origins allowed by CORS (applied in env=local only).
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3100"]

    # HMAC key for the contact phone-number index (08-COMPLIANCE-SECURITY §6).
    phone_hash_key: SecretStr = SecretStr(_DEV_PHONE_HASH_KEY)

    idempotency_ttl_hours: int = 24

    # Telephony (src/mitra_core/telephony). ``sim`` = local carrier simulator: number requests
    # stay "pending_kyc" and nothing is bought. Switch to ``exotel`` once KYC is approved.
    telephony_carrier: Literal["sim", "exotel", "plivo"] = "sim"
    # DND/NCPR scrub provider; ``mock`` treats the numbers listed here as registered.
    dnd_provider: Literal["mock"] = "mock"
    dnd_mock_registered: list[str] = []
    # Promotional (140-series) calling is off by default (08 section 8.1).
    promotional_calling_enabled: bool = False
    # Require a DLT template id on promotional scripts (CMP-07, Phase 2).
    dlt_enforced: bool = False

    # Shared secret for service-to-service calls (/internal/v1, e.g. the voice service). Unset:
    # the dev placeholder in env=local, and the internal API is DISABLED everywhere else.
    # TODO(auth): replace with signed service JWTs or mTLS.
    service_token: SecretStr | None = None

    # Post-call analysis: "heuristic" (deterministic, default) or "llm" via an OpenAI-compatible
    # endpoint (e.g. the voice brain's provider). The model id comes from env only; any LLM
    # failure falls back to the heuristic.
    summarizer: Literal["heuristic", "llm"] = "heuristic"
    summarizer_llm_url: str | None = None
    summarizer_llm_api_key: SecretStr | None = None
    summarizer_llm_model: str | None = None

    # Wallet top-ups (billing). "mock" credits instantly and is refused in staging/prod.
    # Razorpay keys are read from Razorpay's own variable names, without the MITRA_ prefix
    # (test-mode keys work).
    payment_provider: Literal["mock", "razorpay"] = "mock"
    razorpay_key_id: str = Field(default="", validation_alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="RAZORPAY_KEY_SECRET"
    )
    razorpay_webhook_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="RAZORPAY_WEBHOOK_SECRET"
    )
    # Supplier details printed on GST invoices. TODO(billing): real legal entity + GSTIN.
    billing_supplier_name: str = "Mitra (supplier name not configured)"
    billing_supplier_gstin: str = ""
    billing_supplier_state_code: str = "36"  # Telangana
    billing_supplier_address: str = "Hyderabad, Telangana"

    # WhatsApp (src/mitra_core/whatsapp). "sim" stores messages only (dev page shows them);
    # "cloud" = Meta WhatsApp Cloud API. Cloud credentials use Meta's names, no MITRA_ prefix.
    whatsapp_provider: Literal["sim", "cloud"] = "sim"
    whatsapp_token: SecretStr = Field(default=SecretStr(""), validation_alias="WHATSAPP_TOKEN")
    whatsapp_phone_number_id: str = Field(default="", validation_alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_app_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="WHATSAPP_APP_SECRET"
    )
    whatsapp_verify_token: SecretStr = Field(
        default=SecretStr(""), validation_alias="WHATSAPP_VERIFY_TOKEN"
    )
    # AI Manager (src/mitra_core/manager). "rules" = deterministic intent parser (default, tests);
    # "llm" = a free OpenAI-compatible endpoint (Groq or Gemini's OpenAI endpoint) used only to
    # pick a tool and phrase the answer; numbers always come from tool results.
    manager_llm: Literal["rules", "llm"] = "rules"
    manager_llm_url: str | None = None
    manager_llm_api_key: SecretStr | None = None
    manager_llm_model: str | None = None
    # Voice-note transcription: an OpenAI-compatible /audio/transcriptions endpoint (Groq's free
    # Whisper). Unset = voice notes are answered with "please type it" (TODO in the reply).
    transcribe_url: str | None = None
    transcribe_api_key: SecretStr | None = None
    transcribe_model: str | None = None
    # Public base URL of the web app, used for links in WhatsApp messages.
    app_base_url: str = "http://localhost:3000"

    # Lead intake (src/mitra_core/leads). Public base URL of this API, shown in intake URLs.
    public_api_url: str = "http://localhost:8000"
    lead_intake_max_per_minute: int = 60  # per business, all sources together
    lead_form_max_per_ip_hour: int = 10  # website form (no secret possible in a browser)
    # Meta Lead Ads: "sim" fabricates the lead for a leadgen id; "graph" calls the Graph API.
    # The app secret signs webhooks (X-Hub-Signature-256); Meta's names, no MITRA_ prefix.
    meta_leads_provider: Literal["sim", "graph"] = "sim"
    meta_app_secret: SecretStr = Field(default=SecretStr(""), validation_alias="META_APP_SECRET")
    meta_verify_token: SecretStr = Field(
        default=SecretStr(""), validation_alias="META_VERIFY_TOKEN"
    )
    # IndiaMART pull API: "sim" returns sample enquiries; "api" calls mapi.indiamart.com.
    indiamart_provider: Literal["sim", "api"] = "sim"
    # Outgoing webhooks: private/loopback targets are refused unless allowed (local dev only).
    webhook_allow_private_urls: bool = False
    webhook_timeout_seconds: float = 10.0

    @property
    def effective_service_token(self) -> str | None:
        if self.service_token is not None and self.service_token.get_secret_value():
            return self.service_token.get_secret_value()
        return _DEV_SERVICE_TOKEN if self.env == "local" else None

    @property
    def app_db_role(self) -> str:
        return make_url(self.database_url).username or ""

    @property
    def app_db_password(self) -> str:
        return make_url(self.database_url).password or ""

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not _ROLE_NAME_RE.fullmatch(self.app_db_role):
            raise ValueError("database_url must contain a lowercase Postgres role name")
        if not self.app_db_password:
            raise ValueError("database_url must contain a password for the app role")
        if self.env in {"staging", "prod"}:
            if self.jwt_secret.get_secret_value() == _DEV_JWT_SECRET:
                raise ValueError("MITRA_JWT_SECRET must be set outside local/test environments")
            if self.phone_hash_key.get_secret_value() == _DEV_PHONE_HASH_KEY:
                raise ValueError("MITRA_PHONE_HASH_KEY must be set outside local/test environments")
            if self.otp_hash_key.get_secret_value() == _DEV_OTP_HASH_KEY:
                raise ValueError("MITRA_OTP_HASH_KEY must be set outside local/test environments")
            if self.payment_provider == "mock":
                raise ValueError("MITRA_PAYMENT_PROVIDER=mock is not allowed in staging/prod")
            if self.effective_service_token == _DEV_SERVICE_TOKEN:
                raise ValueError("MITRA_SERVICE_TOKEN must not be the dev placeholder")
        token = self.effective_service_token
        if token is not None and token != _DEV_SERVICE_TOKEN and len(token) < 32:
            raise ValueError("service_token must be at least 32 characters")
        if len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("jwt_secret must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
