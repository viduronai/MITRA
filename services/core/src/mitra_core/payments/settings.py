"""Collection settings per business: connect Razorpay, or a plain UPI ID (VPA).

Secrets are sealed on write (``phones.seal_secret``: per-business key, label-bound) and only
unsealed to talk to Razorpay or to verify a webhook; nothing here returns them. A plain UPI ID
has no payment confirmation, so requests in ``upi`` mode are marked paid by the owner.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.config import get_settings
from mitra_core.errors import AppError
from mitra_core.models import CollectionSettings
from mitra_core.payments.providers import LinkProvider, link_provider
from mitra_core.phones import PhoneSealError, seal_secret, unseal_secret

KEY_ID = re.compile(r"^rzp_(test|live)_[A-Za-z0-9]{6,40}$")
# name@handle: 2-256 chars before @ per NPCI; handles are letters only (okhdfcbank, ybl, ...).
VPA = re.compile(r"^[A-Za-z0-9.\-_]{2,80}@[A-Za-z][A-Za-z0-9]{1,30}$")
KEY_LABEL = "razorpay_key_secret"
WEBHOOK_LABEL = "razorpay_webhook_secret"


async def get_settings_row(session: AsyncSession, business_id: uuid.UUID) -> CollectionSettings:
    """The business's settings, created (mode ``none``) on first use."""
    await session.execute(
        insert(CollectionSettings)
        .values(business_id=business_id, webhook_token=secrets.token_urlsafe(24))
        .on_conflict_do_nothing(index_elements=["business_id"])
    )
    row = await session.scalar(
        select(CollectionSettings)
        .where(CollectionSettings.business_id == business_id)
        .execution_options(populate_existing=True)
    )
    assert row is not None  # noqa: S101  (just inserted or already there)
    return row


def webhook_url(row: CollectionSettings) -> str:
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/v1/payments/webhooks/razorpay/{row.webhook_token}"


def masked_key_id(key_id: str | None) -> str | None:
    if not key_id:
        return None
    prefix = key_id[: key_id.index("_", 4) + 1] if key_id.count("_") >= 2 else ""
    return f"{prefix}••••{key_id[-4:]}"


def connect_razorpay(
    row: CollectionSettings, *, key_id: str, key_secret: str | None, webhook_secret: str | None
) -> None:
    """Store the business's own keys. Omitted secrets keep the stored ones (same key id only)."""
    key_id = key_id.strip()
    if not KEY_ID.fullmatch(key_id):
        raise AppError(422, "invalid_key_id", "That doesn't look like a Razorpay key id")
    same_key = row.razorpay_key_id == key_id
    if not key_secret and not (same_key and row.razorpay_key_secret_sealed):
        raise AppError(422, "secret_required", "Enter the key secret")
    if not webhook_secret and not (same_key and row.razorpay_webhook_secret_sealed):
        raise AppError(422, "secret_required", "Enter the webhook secret")
    for value in (key_secret, webhook_secret):
        if value is not None and not 8 <= len(value.strip()) <= 128:
            raise AppError(422, "invalid_secret", "That secret doesn't look right")
    row.mode = "razorpay"
    row.razorpay_key_id = key_id
    if key_secret:
        row.razorpay_key_secret_sealed = seal_secret(
            row.business_id, key_secret.strip(), label=KEY_LABEL
        )
    if webhook_secret:
        row.razorpay_webhook_secret_sealed = seal_secret(
            row.business_id, webhook_secret.strip(), label=WEBHOOK_LABEL
        )


def use_upi_id(row: CollectionSettings, *, vpa: str, payee_name: str | None) -> None:
    vpa = vpa.strip()
    if not VPA.fullmatch(vpa):
        raise AppError(422, "invalid_vpa", "That doesn't look like a UPI ID (name@bank)")
    row.mode = "upi"
    row.upi_vpa = vpa
    row.payee_name = (payee_name or "").strip()[:100] or None


def disconnect(row: CollectionSettings) -> None:
    """Stop collecting; stored secrets are wiped, open requests keep their links."""
    row.mode = "none"
    row.razorpay_key_secret_sealed = None
    row.razorpay_webhook_secret_sealed = None


def rotate_webhook_token(row: CollectionSettings) -> None:
    row.webhook_token = secrets.token_urlsafe(24)


@dataclass(frozen=True, slots=True)
class Razorpay:
    provider: LinkProvider
    webhook_secret: str


def razorpay_for(row: CollectionSettings) -> Razorpay:
    """Unseal the business's keys into a provider. Raises 409 when Razorpay isn't connected."""
    if (
        row.mode != "razorpay"
        or not row.razorpay_key_id
        or not row.razorpay_key_secret_sealed
        or not row.razorpay_webhook_secret_sealed
    ):
        raise AppError(409, "collections_not_connected", "Connect Razorpay first")
    try:
        key_secret = unseal_secret(row.business_id, row.razorpay_key_secret_sealed, label=KEY_LABEL)
        hook_secret = unseal_secret(
            row.business_id, row.razorpay_webhook_secret_sealed, label=WEBHOOK_LABEL
        )
    except PhoneSealError as exc:
        raise AppError(409, "collections_not_connected", "Reconnect Razorpay") from exc
    return Razorpay(link_provider(row.razorpay_key_id, key_secret), hook_secret)


def webhook_secret_for(row: CollectionSettings) -> str | None:
    if not row.razorpay_webhook_secret_sealed:
        return None
    try:
        return unseal_secret(
            row.business_id, row.razorpay_webhook_secret_sealed, label=WEBHOOK_LABEL
        )
    except PhoneSealError:
        return None
