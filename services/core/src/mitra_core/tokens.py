"""Access-token minting.

TEMPORARY: the API signs HS256 JWTs with the dev secret from config, both for the phone-OTP
login and for ``scripts/dev_token.py``.
TODO(auth): replace with Better Auth-issued tokens verified via JWKS (TRD §3); then only
``security.decode_token`` and this module need to change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from mitra_core.config import get_settings
from mitra_core.models.enums import MemberRole


def mint(
    sub: uuid.UUID,
    *,
    business_id: uuid.UUID | None = None,
    role: MemberRole | None = None,
    phone: str | None = None,
    name: str | None = None,
    ttl: timedelta | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    lifetime = ttl if ttl is not None else timedelta(seconds=settings.access_token_ttl_seconds)
    claims: dict[str, object] = {
        "sub": str(sub),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + lifetime,
    }
    if business_id:
        claims["business_id"] = str(business_id)
    if role:
        claims["role"] = role.value
    if phone:
        claims["phone"] = phone
    if name:
        claims["name"] = name
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), settings.jwt_algorithm)
