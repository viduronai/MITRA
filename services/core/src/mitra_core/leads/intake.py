"""Per-business intake URL and secret (INT-12): ``POST /lead-intake/{slug}`` with
``X-Mitra-Secret``. Secrets are 256-bit random tokens stored as SHA-256 hashes; after a rotation
the previous secret keeps working for :data:`ROTATION_GRACE` so the owner can update Zapier, the
Sheet script and so on without losing leads.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import Business, LeadIntake
from mitra_core.webhooks.signing import generate_secret, hint

SECRET_HEADER = "X-Mitra-Secret"  # noqa: S105  (a header name)
SECRET_PREFIX = "mli_"  # noqa: S105
ROTATION_GRACE = timedelta(hours=24)
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_slug(business_name: str) -> str:
    """``"Sunrise Clinic"`` -> ``"sunrise-clinic-7f3k2q"`` (unguessable suffix)."""
    base = _NON_SLUG.sub("-", business_name.lower()).strip("-")[:24].strip("-") or "business"
    suffix = "".join(secrets.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(6))
    return f"{base}-{suffix}"


async def get_intake(session: AsyncSession, business_id: uuid.UUID) -> LeadIntake | None:
    return await session.scalar(select(LeadIntake).where(LeadIntake.business_id == business_id))


async def ensure_intake(session: AsyncSession, business: Business) -> tuple[LeadIntake, str | None]:
    """The business's intake, created on first use. Returns the new secret only on creation."""
    intake = await get_intake(session, business.id)
    if intake is not None:
        return intake, None
    secret = generate_secret(SECRET_PREFIX)
    intake = LeadIntake(
        business_id=business.id,
        slug=new_slug(business.name),
        secret_hash=hash_secret(secret),
        secret_hint=hint(secret),
    )
    session.add(intake)
    await session.flush()
    return intake, secret


def rotate(intake: LeadIntake, now: datetime) -> str:
    secret = generate_secret(SECRET_PREFIX)
    intake.previous_secret_hash = intake.secret_hash
    # Database time, because ``lead_intake_business`` compares it with the database's now().
    intake.previous_valid_until = func.now() + ROTATION_GRACE
    intake.secret_hash = hash_secret(secret)
    intake.secret_hint = hint(secret)
    intake.rotated_at = now
    return secret
