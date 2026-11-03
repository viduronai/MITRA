"""Owner attestations for generic lead sources (lead consent policy rule 3).

Ticking "These people asked to be contacted about their enquiry" appends a row with the user,
time, words and version; unticking stamps ``revoked_at``. Rows are never edited otherwise, so
the history of who vouched for which source stays auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.leads import consent as policy
from mitra_core.leads.enums import LeadSourceKind
from mitra_core.models import AppUser, LeadConsentAttestation


async def active(
    session: AsyncSession, business_id: uuid.UUID, kind: LeadSourceKind
) -> LeadConsentAttestation | None:
    return await session.scalar(
        select(LeadConsentAttestation)
        .where(
            LeadConsentAttestation.business_id == business_id,
            LeadConsentAttestation.source == kind.value,
            LeadConsentAttestation.revoked_at.is_(None),
        )
        .order_by(LeadConsentAttestation.attested_at.desc())
        .limit(1)
    )


async def for_policy(
    session: AsyncSession, business_id: uuid.UUID, kind: LeadSourceKind
) -> policy.Attestation | None:
    row = await active(session, business_id, kind)
    return policy.Attestation(row.text_version, row.wording) if row else None


async def revoke(
    session: AsyncSession, business_id: uuid.UUID, kind: LeadSourceKind, now: datetime
) -> None:
    await session.execute(
        update(LeadConsentAttestation)
        .where(
            LeadConsentAttestation.business_id == business_id,
            LeadConsentAttestation.source == kind.value,
            LeadConsentAttestation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


async def attest(
    session: AsyncSession,
    business_id: uuid.UUID,
    kind: LeadSourceKind,
    user: AppUser,
    language: str | None,
    now: datetime,
) -> LeadConsentAttestation:
    """Replace any active attestation with a new one by ``user`` in their language."""
    await revoke(session, business_id, kind, now)
    row = LeadConsentAttestation(
        business_id=business_id,
        source=kind.value,
        user_id=user.id,
        user_name=user.name,
        text_version=policy.ATTESTATION_VERSION,
        wording=policy.ATTESTATION_TEXTS[policy.lang(language)],
        attested_at=now,
    )
    session.add(row)
    await session.flush()
    return row
