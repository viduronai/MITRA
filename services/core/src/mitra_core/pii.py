"""Helpers for handling personal data (phone numbers) without storing it in the clear."""

from __future__ import annotations

import hashlib
import hmac

from mitra_core.config import get_settings


def hash_phone(phone_e164: str, key: str | None = None) -> str:
    """HMAC-SHA256 (hex) of an E.164 phone number: stable per key, not reversible without it."""
    secret = key if key is not None else get_settings().phone_hash_key.get_secret_value()
    return hmac.new(secret.encode(), phone_e164.encode(), hashlib.sha256).hexdigest()


def hash_ip(ip: str, key: str | None = None) -> str:
    """HMAC of a client IP for rate limiting; domain-separated from phone hashes."""
    return hash_phone(f"ip:{ip}", key)


def phone_last4(phone_e164: str) -> str:
    return phone_e164[-4:]
