"""Seal a phone number so a queued call can be dialled later without storing it in the clear.

Stdlib only (no crypto dependency yet): encrypt-then-MAC with HMAC-SHA256 as the PRF in counter
mode for the keystream and a separate HMAC-SHA256 tag over nonce + ciphertext. Keys are derived
from ``MITRA_DIALER_SEAL_KEY`` (else from the phone-hash key) with distinct labels.

TODO(kms): replace with KMS envelope encryption (08-COMPLIANCE-SECURITY section 6).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

from mitra_core.config import get_settings

_VERSION = "v1"
_NONCE = 16
_TAG = 16


class SealError(ValueError):
    """The sealed value is corrupt or was sealed with another key."""


def _master() -> bytes:
    explicit = os.environ.get("MITRA_DIALER_SEAL_KEY", "")
    if explicit:
        return explicit.encode()
    return ("dialer-seal:" + get_settings().phone_hash_key.get_secret_value()).encode()


def _key(label: str) -> bytes:
    return hmac.new(_master(), label.encode(), hashlib.sha256).digest()


def _stream(nonce: bytes, length: int) -> bytes:
    key, out, counter = _key("enc"), b"", 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def seal(plain: str) -> str:
    data = plain.encode()
    nonce = secrets.token_bytes(_NONCE)
    body = bytes(a ^ b for a, b in zip(data, _stream(nonce, len(data)), strict=True))
    tag = hmac.new(_key("mac"), nonce + body, hashlib.sha256).digest()[:_TAG]
    return f"{_VERSION}:" + base64.urlsafe_b64encode(nonce + body + tag).decode()


def unseal(sealed: str) -> str:
    version, _, payload = sealed.partition(":")
    if version != _VERSION:
        raise SealError("unknown seal version")
    try:
        raw = base64.urlsafe_b64decode(payload.encode())
    except ValueError as e:
        raise SealError("corrupt sealed value") from e
    if len(raw) < _NONCE + _TAG:
        raise SealError("corrupt sealed value")
    nonce, body, tag = raw[:_NONCE], raw[_NONCE:-_TAG], raw[-_TAG:]
    expected = hmac.new(_key("mac"), nonce + body, hashlib.sha256).digest()[:_TAG]
    if not hmac.compare_digest(tag, expected):
        raise SealError("sealed value failed authentication")
    return bytes(a ^ b for a, b in zip(body, _stream(nonce, len(body)), strict=True)).decode()
