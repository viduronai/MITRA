"""Payment-link providers for the business's own collections (INT-08).

* ``sim`` (default, needs no account): nothing leaves the machine; the short URL opens core's
  dev-only simulator page (``/v1/payments/sim/{link_id}``) whose Pay / Fail buttons post a
  Razorpay-shaped webhook signed with the business's own webhook secret.
* ``razorpay``: the Razorpay Payment Links API with the *business's* key id and secret (never
  Mitra's own billing keys). Test-mode keys work unchanged.

Webhook signature (Razorpay docs): HMAC-SHA256(webhook_secret, raw body), hex; verified with
``billing.providers.verify_hmac`` (constant time).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

import httpx

from mitra_core.config import Settings, get_settings
from mitra_core.errors import AppError

RAZORPAY_API = "https://api.razorpay.com/v1"


@dataclass(frozen=True, slots=True)
class CreatedLink:
    link_id: str
    short_url: str


class LinkProvider(Protocol):
    name: str

    async def create_link(
        self,
        *,
        amount_paise: int,
        description: str,
        reference_id: str,
        customer_name: str | None,
        expire_by: int | None,
        notes: dict[str, str],
    ) -> CreatedLink: ...

    async def cancel_link(self, link_id: str) -> None: ...


class SimulatedLinkProvider:
    """No network. The link opens core's dev-only simulator page."""

    name = "sim"

    def __init__(self, public_api_url: str) -> None:
        self._base = public_api_url.rstrip("/")

    async def create_link(
        self,
        *,
        amount_paise: int,
        description: str,
        reference_id: str,
        customer_name: str | None,
        expire_by: int | None,
        notes: dict[str, str],
    ) -> CreatedLink:
        link_id = f"plink_sim_{secrets.token_hex(8)}"
        return CreatedLink(link_id=link_id, short_url=f"{self._base}/v1/payments/sim/{link_id}")

    async def cancel_link(self, link_id: str) -> None:
        return None


class RazorpayLinkProvider:
    name = "razorpay"

    def __init__(
        self, key_id: str, key_secret: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.key_id = key_id
        self._secret = key_secret
        self._client = client

    async def _post(self, path: str, body: dict[str, object]) -> httpx.Response:
        auth = httpx.BasicAuth(self.key_id, self._secret)
        try:
            if self._client is not None:
                return await self._client.post(f"{RAZORPAY_API}{path}", json=body, auth=auth)
            async with httpx.AsyncClient(timeout=10) as client:
                return await client.post(f"{RAZORPAY_API}{path}", json=body, auth=auth)
        except httpx.HTTPError as exc:
            raise AppError(
                502, "payment_provider_unavailable", "Razorpay could not be reached"
            ) from exc

    async def create_link(
        self,
        *,
        amount_paise: int,
        description: str,
        reference_id: str,
        customer_name: str | None,
        expire_by: int | None,
        notes: dict[str, str],
    ) -> CreatedLink:
        body: dict[str, object] = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description[:2048],
            "reference_id": reference_id[:40],
            # Mitra sends the link on WhatsApp itself; Razorpay's own SMS/email stay off.
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": notes,
        }
        if customer_name:
            body["customer"] = {"name": customer_name[:100]}
        if expire_by:
            body["expire_by"] = expire_by
        resp = await self._post("/payment_links", body)
        if resp.status_code >= 400:
            raise AppError(502, "payment_provider_error", "Razorpay rejected the payment link")
        data = resp.json()
        return CreatedLink(link_id=str(data["id"]), short_url=str(data["short_url"]))

    async def cancel_link(self, link_id: str) -> None:
        resp = await self._post(f"/payment_links/{link_id}/cancel", {})
        if resp.status_code >= 400:
            raise AppError(502, "payment_provider_error", "Razorpay could not cancel the link")


_override: LinkProvider | None = None


def set_link_provider(provider: LinkProvider | None) -> None:
    """Tests: force a provider for every business (``None`` restores the default)."""
    global _override
    _override = provider


def link_provider(key_id: str, key_secret: str, settings: Settings | None = None) -> LinkProvider:
    """The provider for one business's Razorpay account (simulated unless configured)."""
    if _override is not None:
        return _override
    settings = settings or get_settings()
    if settings.collections_provider == "razorpay":
        return RazorpayLinkProvider(key_id, key_secret)
    return SimulatedLinkProvider(settings.public_api_url)
