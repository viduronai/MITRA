"""Mint a signed dev JWT for local testing (HS256, secret from MITRA_JWT_SECRET / .env).

Examples:
    uv run python scripts/dev_token.py --phone +919876543210 --name "Ravi"
    uv run python scripts/dev_token.py --sub <user-uuid> --business-id <uuid> --role owner

A new --sub is generated when omitted; pass --phone so the API can create the user on first
use. Temporary until Better Auth issues real tokens (TRD §3).
"""

from __future__ import annotations

import argparse
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
    ttl: timedelta = timedelta(hours=12),
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(sub),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + ttl,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sub", type=uuid.UUID, default=None, help="user id (default: new)")
    parser.add_argument("--business-id", type=uuid.UUID, default=None)
    parser.add_argument("--role", type=MemberRole, choices=list(MemberRole), default=None)
    parser.add_argument("--phone", help="E.164, e.g. +919876543210")
    parser.add_argument("--name")
    parser.add_argument("--hours", type=float, default=12.0, help="token lifetime")
    args = parser.parse_args()
    sub = args.sub or uuid.uuid4()
    token = mint(
        sub,
        business_id=args.business_id,
        role=args.role,
        phone=args.phone,
        name=args.name,
        ttl=timedelta(hours=args.hours),
    )
    print(f"# sub={sub}")
    print(token)


if __name__ == "__main__":
    main()
