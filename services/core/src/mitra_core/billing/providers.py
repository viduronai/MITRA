"""Payment provider adapters for wallet top-ups.

* ``mock`` (default, local/test only): orders are paid the moment they are created.
* ``razorpay``: creates an Order through the Razorpay API; the browser completes Checkout and the
  payment is credited on a verified checkout signature or a verified webhook, whichever comes
  first (both are idempotent). Test-mode keys work unchanged.

Signatures (Razorpay docs): checkout = HMAC-SHA256(key_secret, "<order_id>|<payment_id>");
webhook = HMAC-SHA256(webhook_secret, raw request body). Both hex, compared in constant time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

from mitra_core.config import Settings, get_settings
from mitra_core.errors import AppError

RAZORPAY_API = "https://api.razorpay.com/v1"


@dataclass(frozen=True, slots=True)
class ProviderOrder:
    order_id: str
    status: Literal["created", "paid"]
    payment_id: str | None = None
    # What the browser needs to open the provider's checkout (None when already paid).
    checkout: dict[str, Any] | None = None


class PaymentProvider(Protocol):
    name: str

    async def create_order(
        self, *, amount_paise: int, receipt: str, notes: dict[str, str]
    ) -> ProviderOrder: ...

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool: ...


def hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_hmac(secret: str, message: bytes, signature: str) -> bool:
    if not secret or not signature:
        return False
    return hmac.compare_digest(hmac_hex(secret, message), signature.strip())


class MockProvider:
    """Instant success, no network. Never selectable in staging/prod (see Settings)."""

    name = "mock"

    async def create_order(
        self, *, amount_paise: int, receipt: str, notes: dict[str, str]
    ) -> ProviderOrder:
        token = secrets.token_hex(8)
        return ProviderOrder(
            order_id=f"mock_order_{token}", status="paid", payment_id=f"mock_pay_{token}"
        )

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        return False  # mock orders are paid on creation; nothing to confirm


class RazorpayProvider:
    name = "razorpay"

    def __init__(self, key_id: str, key_secret: str, client: httpx.AsyncClient | None = None):
        self.key_id = key_id
        self._secret = key_secret
        self._client = client

    async def create_order(
        self, *, amount_paise: int, receipt: str, notes: dict[str, str]
    ) -> ProviderOrder:
        body = {"amount": amount_paise, "currency": "INR", "receipt": receipt, "notes": notes}
        auth = httpx.BasicAuth(self.key_id, self._secret)
        try:
            if self._client is not None:
                resp = await self._client.post(f"{RAZORPAY_API}/orders", json=body, auth=auth)
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{RAZORPAY_API}/orders", json=body, auth=auth)
        except httpx.HTTPError as exc:
            raise AppError(
                502, "payment_provider_unavailable", "Payment provider unreachable"
            ) from exc
        if resp.status_code >= 400:
            raise AppError(502, "payment_provider_error", "Payment provider rejected the order")
        order_id = str(resp.json()["id"])
        checkout = {
            "provider": self.name,
            "key_id": self.key_id,
            "order_id": order_id,
            "amount": amount_paise,
            "currency": "INR",
        }
        return ProviderOrder(order_id=order_id, status="created", checkout=checkout)

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        return verify_hmac(self._secret, f"{order_id}|{payment_id}".encode(), signature)


def get_payment_provider() -> PaymentProvider:
    """FastAPI dependency (override in tests)."""
    return provider_for(get_settings())


def provider_for(settings: Settings) -> PaymentProvider:
    if settings.payment_provider == "razorpay":
        secret = settings.razorpay_key_secret.get_secret_value()
        if not settings.razorpay_key_id or not secret:
            raise AppError(503, "payments_not_configured", "Payments are not configured")
        return RazorpayProvider(settings.razorpay_key_id, secret)
    return MockProvider()
