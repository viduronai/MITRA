"""Phone OTP helpers. Codes are never stored or logged: only ``hash_code`` output is."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable

from mitra_core.config import get_settings

CodeGenerator = Callable[[], str]


def generate_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def get_code_generator() -> CodeGenerator:
    """FastAPI dependency so tests can pin the code."""
    return generate_code


def hash_code(request_id: uuid.UUID, code: str) -> str:
    """HMAC-SHA256 bound to the request id, so equal codes on different requests differ."""
    key = get_settings().otp_hash_key.get_secret_value()
    return hmac.new(key.encode(), f"{request_id}:{code}".encode(), hashlib.sha256).hexdigest()
