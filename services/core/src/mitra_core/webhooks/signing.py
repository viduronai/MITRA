"""Webhook signatures: ``X-Mitra-Signature: t=<unix seconds>,v1=<hex>``.

``v1`` is HMAC-SHA256 over ``"<t>." + raw body`` with the endpoint's secret. Receivers recompute
it, compare in constant time and reject timestamps older than five minutes (replay protection).
:func:`verify` is the reference implementation shown in the docs.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

SIGNATURE_HEADER = "X-Mitra-Signature"
TOLERANCE_SECONDS = 300


def generate_secret(prefix: str = "whsec_") -> str:
    return prefix + secrets.token_urlsafe(32)


def hint(secret: str) -> str:
    """What the UI may show after creation: the prefix plus four characters."""
    head, _, rest = secret.partition("_")
    return f"{head}_{rest[:4]}" if rest else secret[:6]


def compute(secret: str, timestamp: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def header_value(secret: str, timestamp: int, body: bytes) -> str:
    return f"t={timestamp},v1={compute(secret, timestamp, body)}"


def verify(secret: str, header: str, body: bytes, now: int) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        timestamp = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(now - timestamp) > TOLERANCE_SECONDS:
        return False
    return hmac.compare_digest(parts.get("v1", ""), compute(secret, timestamp, body))
