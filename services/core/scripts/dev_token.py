"""Mint a signed dev JWT for local testing (HS256, secret from MITRA_JWT_SECRET / .env).

Examples:
    uv run python scripts/dev_token.py --phone +919876543210 --name "Ravi"
    uv run python scripts/dev_token.py --sub <user-uuid> --business-id <uuid> --role owner

A new --sub is generated when omitted; pass --phone so the API can create the user on first
use. The normal way to get a token is now the OTP login (see README); this script remains for
quick experiments. Temporary until Better Auth issues real tokens (TRD §3).
"""

from __future__ import annotations

import argparse
import uuid
from datetime import timedelta

from mitra_core.models.enums import MemberRole
from mitra_core.tokens import mint

__all__ = ["mint"]


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
