"""The two outward hooks of a new lead: queue the instant call (CALL-03) and the optional
WhatsApp heads-up (NUM-07). Both are FastAPI dependencies so tests can replace them.

The dialer (``mitra_core.dialer.queue``) runs the compliance gate again right before it dials;
the check at intake only tells the owner what will happen ("will call at 9:00 AM").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.dialer import queue
from mitra_core.telephony.enums import CallPurpose
from mitra_core.whatsapp import send_heads_up

LEAD_CALL_SOURCE = "lead"


class LeadDialer(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        *,
        employee_id: uuid.UUID,
        phone_e164: str,
        variables: dict[str, str],
        not_before: datetime | None,
        dedupe_key: str,
    ) -> uuid.UUID: ...


class HeadsUp(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        *,
        phone_e164: str,
        name: str | None,
        employee_id: uuid.UUID,
        call_at: datetime,
    ) -> None: ...


async def dialer_enqueue(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    employee_id: uuid.UUID,
    phone_e164: str,
    variables: dict[str, str],
    not_before: datetime | None,
    dedupe_key: str,
) -> uuid.UUID:
    job = await queue.enqueue_call(
        session,
        business_id,
        employee_id=employee_id,
        phone_e164=phone_e164,
        purpose=CallPurpose.SERVICE,
        variables=variables,
        source=LEAD_CALL_SOURCE,
        not_before=not_before,
        dedupe_key=dedupe_key,
    )
    return job.id


async def whatsapp_heads_up(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    phone_e164: str,
    name: str | None,
    employee_id: uuid.UUID,
    call_at: datetime,
) -> None:
    """NUM-07 through the manager's WhatsApp sender (simulator by default)."""
    eta = max(60, round((call_at - utcnow()).total_seconds()))
    await send_heads_up(
        session,
        business_id,
        phone_e164=phone_e164,
        name=name,
        employee_id=employee_id,
        eta_seconds=eta,
        source="lead",
    )


def get_lead_dialer() -> LeadDialer:
    return dialer_enqueue


def get_heads_up() -> HeadsUp:
    return whatsapp_heads_up
