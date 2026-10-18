"""Application settings, read from environment variables (prefix ``MITRA_``) or a ``.env`` file."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

_DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me-0123456789"  # noqa: S105
_DEV_PHONE_HASH_KEY = "dev-only-insecure-phone-hash-key-change-me"
_DEV_OTP_HASH_KEY = "dev-only-insecure-otp-hash-key-change-me"
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

    # Browser origins allowed by CORS (applied in env=local only).
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3100"]

    # HMAC key for the contact phone-number index (08-COMPLIANCE-SECURITY §6).
    phone_hash_key: SecretStr = SecretStr(_DEV_PHONE_HASH_KEY)

    idempotency_ttl_hours: int = 24

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
        if len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("jwt_secret must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
