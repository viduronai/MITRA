"""Customer phone numbers, stored encrypted (08-COMPLIANCE-SECURITY section 6).

Every customer number is kept twice: ``phone_hash`` (HMAC, ``mitra_core.pii``) as the lookup
index, and ``phone_enc``, sealed with AES-256-GCM under a per-business key so one business's
key can never open another business's numbers. Sealed values are versioned text:

- ``v2:<b64url(nonce12 | ciphertext | tag16)>``: AES-256-GCM, key = HKDF-SHA256(master,
  info = business id), associated data = version + business id.
- ``v1:...``: the dialer's earlier stdlib seal (no business binding). Still readable, never
  written; values are re-sealed as v2 by migration 0006_phones.

The master key is ``MITRA_PHONE_ENC_KEY`` (else derived from the phone-hash key with a distinct
label). TODO(kms): fetch a KMS-wrapped data key instead; the version prefix allows rotation.

Reading a number back is :func:`reveal_phone`, which writes a ``phone_access_log`` row (who, why,
when; never the number). Numbers never go into logs, webhooks or API responses: use
:func:`mask_phone` / ``phone_last4`` there.
"""

from __future__ import annotations

import base64
import re
import secrets
import uuid
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.config import get_settings
from mitra_core.logging import get_logger

log = get_logger(__name__)

VERSION = "v2"
_NONCE = 12
_SALT = b"mitra-phone-seal"
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
_LABEL = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class PhoneSealError(ValueError):
    """The sealed value is corrupt, unknown, or belongs to another business/key."""


def _master() -> bytes:
    settings = get_settings()
    if settings.phone_enc_key is not None and settings.phone_enc_key.get_secret_value():
        return settings.phone_enc_key.get_secret_value().encode()
    return ("phone-enc:" + settings.phone_hash_key.get_secret_value()).encode()


@lru_cache(maxsize=1024)
def _cipher(master: bytes, business_id: uuid.UUID) -> AESGCM:
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=_SALT, info=b"business:" + business_id.bytes
    ).derive(master)
    return AESGCM(key)


def _aad(business_id: uuid.UUID) -> bytes:
    return f"mitra-phone:{VERSION}:".encode() + business_id.bytes


def seal_phone(business_id: uuid.UUID, phone_e164: str) -> str:
    """Encrypt an E.164 number for one business. Raises ``ValueError`` on a non-E.164 input."""
    if not _E164.fullmatch(phone_e164):
        raise ValueError("phone must be E.164")
    nonce = secrets.token_bytes(_NONCE)
    body = _cipher(_master(), business_id).encrypt(nonce, phone_e164.encode(), _aad(business_id))
    return f"{VERSION}:" + base64.urlsafe_b64encode(nonce + body).decode()


def unseal_phone(business_id: uuid.UUID, sealed: str) -> str:
    """Decrypt a value from :func:`seal_phone` (or a legacy dialer ``v1`` value)."""
    version, _, payload = sealed.partition(":")
    if version == "v1":
        from mitra_core.dialer.sealing import unseal_v1  # legacy, not business-bound

        return unseal_v1(sealed)
    if version != VERSION:
        raise PhoneSealError("unknown seal version")
    try:
        raw = base64.urlsafe_b64decode(payload.encode())
    except ValueError as e:
        raise PhoneSealError("corrupt sealed value") from e
    if len(raw) <= _NONCE + 16:
        raise PhoneSealError("corrupt sealed value")
    try:
        plain = _cipher(_master(), business_id).decrypt(
            raw[:_NONCE], raw[_NONCE:], _aad(business_id)
        )
    except InvalidTag as e:
        raise PhoneSealError("sealed value failed authentication") from e
    return plain.decode()


def seal_secret(business_id: uuid.UUID, plain: str, *, label: str) -> str:
    """Seal any short per-business secret (e.g. a payment gateway key). ``label`` (snake_case,
    e.g. "razorpay_key_secret") is bound as associated data: a value sealed under one label
    cannot be opened as another. Same key hierarchy and ``v2`` format as phone numbers."""
    if not _LABEL.fullmatch(label):
        raise ValueError("label must be a short snake_case name")
    nonce = secrets.token_bytes(_NONCE)
    aad = _aad(business_id) + b":" + label.encode()
    body = _cipher(_master(), business_id).encrypt(nonce, plain.encode(), aad)
    return f"{VERSION}:" + base64.urlsafe_b64encode(nonce + body).decode()


def unseal_secret(business_id: uuid.UUID, sealed: str, *, label: str) -> str:
    version, _, payload = sealed.partition(":")
    if version != VERSION:
        raise PhoneSealError("unknown seal version")
    try:
        raw = base64.urlsafe_b64decode(payload.encode())
        aad = _aad(business_id) + b":" + label.encode()
        return _cipher(_master(), business_id).decrypt(raw[:_NONCE], raw[_NONCE:], aad).decode()
    except (ValueError, InvalidTag) as e:
        raise PhoneSealError("sealed value failed authentication") from e


def mask_phone(phone_last4: str | None, *, country: str = "+91") -> str | None:
    """What lists and webhooks show: ``+91 ••••• •3210`` (only the last four digits)."""
    if not phone_last4:
        return None
    return f"{country} ••••• •{phone_last4[-4:]}"


# ---- contacts -----------------------------------------------------------------------------------


async def remember_phone(
    session: AsyncSession, business_id: uuid.UUID, phone_hash: str, phone_e164: str
) -> None:
    """Fill ``contact.phone_enc`` for this number if the contact exists and has none yet."""
    from mitra_core.models import Contact

    await session.execute(
        update(Contact)
        .where(
            Contact.business_id == business_id,
            Contact.phone_hash == phone_hash,
            Contact.phone_enc.is_(None),
        )
        .values(phone_enc=seal_phone(business_id, phone_e164))
    )


async def _sealed_from_dialer(
    session: AsyncSession, business_id: uuid.UUID, phone_hash: str
) -> str | None:
    """Contacts created before 0006 may only have a copy on the dialer's own rows."""
    from mitra_core.models.campaign import CampaignContact, OutboundJob

    for model in (OutboundJob, CampaignContact):
        sealed = await session.scalar(
            select(model.phone_enc)
            .where(model.business_id == business_id, model.phone_hash == phone_hash)
            .where(model.phone_enc != "")
            .order_by(model.created_at.desc())
            .limit(1)
        )
        if sealed:
            return sealed
    return None


async def has_phone(session: AsyncSession, business_id: uuid.UUID, contact_id: uuid.UUID) -> bool:
    """Whether a number is on file (no decryption, no access-log row): for dry runs."""
    from mitra_core.models import Contact

    row = (
        await session.execute(
            select(Contact.phone_enc, Contact.phone_hash).where(
                Contact.business_id == business_id, Contact.id == contact_id
            )
        )
    ).first()
    if row is None:
        return False
    return bool(row[0]) or await _sealed_from_dialer(session, business_id, row[1]) is not None


async def reveal_phone(
    session: AsyncSession,
    business_id: uuid.UUID,
    contact_id: uuid.UUID,
    *,
    purpose: str,
    actor: str,
) -> str | None:
    """The contact's E.164 number, or None if none is on file. The ONLY way to read one.

    Writes a ``phone_access_log`` row (business, contact, purpose, actor, time) in the caller's
    transaction; the caller commits. ``purpose`` is a short snake_case label ("callback",
    "owner_view", "team_follow_up"); ``actor`` names who asked ("user:<id>", "dialer", "team").
    Never log the result.
    """
    from mitra_core.models import Contact, PhoneAccessLog

    if not _LABEL.fullmatch(purpose):
        raise ValueError("purpose must be a short snake_case label")
    if not 0 < len(actor) <= 80:
        raise ValueError("actor must be 1-80 characters")
    contact = await session.scalar(
        select(Contact).where(Contact.business_id == business_id, Contact.id == contact_id)
    )
    if contact is None:
        return None
    sealed = contact.phone_enc
    if not sealed:
        sealed = await _sealed_from_dialer(session, business_id, contact.phone_hash)
    if not sealed:
        return None
    try:
        phone = unseal_phone(business_id, sealed)
    except (PhoneSealError, ValueError):
        log.warning("phones.unseal_failed", contact_id=str(contact_id))
        return None
    if not contact.phone_enc or not contact.phone_enc.startswith(f"{VERSION}:"):
        contact.phone_enc = seal_phone(business_id, phone)  # lazy upgrade to v2
    session.add(
        PhoneAccessLog(
            business_id=business_id,
            contact_id=contact_id,
            purpose=purpose,
            actor=actor,
            created_at=utcnow(),
        )
    )
    await session.flush()
    return phone


async def forget_phone(session: AsyncSession, business_id: uuid.UUID, phone_hash: str) -> int:
    """DPDP erasure of a number's sealed copies outside ``contact`` (the dialer's rows).

    Queued calls to it are cancelled; finished jobs and campaign rows keep their result but lose
    the number (``phone_enc`` = ''). Returns how many queued calls were cancelled.
    """
    from mitra_core.dialer.enums import ContactStatus, JobStatus
    from mitra_core.models.campaign import CampaignContact, OutboundJob

    now = utcnow()
    cancelled = await session.execute(
        update(OutboundJob)
        .where(
            OutboundJob.business_id == business_id,
            OutboundJob.phone_hash == phone_hash,
            OutboundJob.status == JobStatus.QUEUED,
        )
        .values(status=JobStatus.CANCELLED, reasons=["forgotten"], finished_at=now)
    )
    await session.execute(
        update(OutboundJob)
        .where(OutboundJob.business_id == business_id, OutboundJob.phone_hash == phone_hash)
        .values(phone_enc="")
    )
    await session.execute(
        update(CampaignContact)
        .where(
            CampaignContact.business_id == business_id,
            CampaignContact.phone_hash == phone_hash,
            CampaignContact.status.in_([ContactStatus.PENDING, ContactStatus.QUEUED]),
        )
        .values(status=ContactStatus.SKIPPED, reasons=["forgotten"])
    )
    await session.execute(
        update(CampaignContact)
        .where(CampaignContact.business_id == business_id, CampaignContact.phone_hash == phone_hash)
        .values(phone_enc="")
    )
    return int(cancelled.rowcount or 0)  # type: ignore[attr-defined]
