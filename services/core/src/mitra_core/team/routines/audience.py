"""Who a routine would contact (AUTO-04 dry run uses exactly the same code as a real run).

Audiences are read from what the business already has: appointment and callback promises
(``commitment``), call results (``call``). Then each person is checked: not opted out, and we
have a number we may dial. Consent, DND, calling hours and frequency caps are checked again by
the dialer right before each call, so a dry run can only be more generous, never less safe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import Call, Commitment, Contact, OptOut
from mitra_core.models.enums import CallResult, CommitmentStatus
from mitra_core.team import ports

MAX_AUDIENCE = 500


@dataclass(frozen=True, slots=True)
class Person:
    contact_id: uuid.UUID
    name: str | None
    last4: str
    skip: str | None = None  # "opted_out" | "no_number" | None (will be contacted)
    phone: str | None = None  # E.164 for the run itself; never returned by the API


def _day_bounds(now: datetime, tz: str, offset_days: int) -> tuple[datetime, datetime]:
    zone = ZoneInfo(tz)
    day = now.astimezone(zone).date() + timedelta(days=offset_days)
    start = datetime.combine(day, time(0, 0), zone)
    return start, start + timedelta(days=1)


async def _appointments(
    session: AsyncSession, business_id: uuid.UUID, start: datetime, end: datetime
) -> list[uuid.UUID]:
    rows = await session.scalars(
        select(Commitment.contact_id)
        .where(Commitment.business_id == business_id, Commitment.kind == "appointment")
        .where(Commitment.status == CommitmentStatus.OPEN, Commitment.contact_id.is_not(None))
        .where(Commitment.due_at >= start, Commitment.due_at < end)
        .order_by(Commitment.due_at)
    )
    return [r for r in rows if r is not None]


async def contact_ids(
    session: AsyncSession, business_id: uuid.UUID, audience: str, now: datetime, tz: str
) -> list[uuid.UUID]:
    if audience == "tomorrows_appointments":
        ids = await _appointments(session, business_id, *_day_bounds(now, tz, 1))
    elif audience == "todays_appointments":
        _, end = _day_bounds(now, tz, 0)
        ids = await _appointments(session, business_id, now, end)
    elif audience == "no_shows_yesterday":
        ids = await _appointments(session, business_id, *_day_bounds(now, tz, -1))
    elif audience == "callbacks_due":
        _, end = _day_bounds(now, tz, 0)
        rows = await session.scalars(
            select(Commitment.contact_id)
            .where(Commitment.business_id == business_id, Commitment.kind == "callback")
            .where(Commitment.status == CommitmentStatus.OPEN)
            .where(or_(Commitment.due_at.is_(None), Commitment.due_at < end))
        )
        ids = [r for r in rows if r is not None]
    elif audience == "missed_callers_today":
        start, end = _day_bounds(now, tz, 0)
        rows = await session.scalars(
            select(Call.contact_id)
            .where(Call.business_id == business_id, Call.result == CallResult.MISSED)
            .where(Call.started_at >= start, Call.started_at < end)
        )
        ids = [r for r in rows if r is not None]
    elif audience == "interested_not_booked":
        booked = (
            select(Call.id)
            .where(Call.contact_id == Contact.id, Call.result == CallResult.BOOKED)
            .exists()
        )
        rows = await session.scalars(
            select(Call.contact_id)
            .join(Contact, Contact.id == Call.contact_id)
            .where(Call.business_id == business_id, Call.result == CallResult.INTERESTED)
            .where(Call.started_at >= now - timedelta(days=14))
            .where(~booked)
        )
        ids = [r for r in rows if r is not None]
    elif audience == "inactive_customers":
        last = func.max(Call.started_at)
        rows = await session.scalars(
            select(Call.contact_id)
            .where(Call.business_id == business_id, Call.contact_id.is_not(None))
            .group_by(Call.contact_id)
            .having(and_(last < now - timedelta(days=30), last >= now - timedelta(days=90)))
        )
        ids = [r for r in rows if r is not None]
    else:
        ids = []
    return list(dict.fromkeys(ids))[:MAX_AUDIENCE]


async def people(
    session: AsyncSession,
    business_id: uuid.UUID,
    ids: list[uuid.UUID],
    *,
    needs_phone: bool = True,
) -> list[Person]:
    """Resolve and check each contact (opt-out, dialable number)."""
    if not ids:
        return []
    contacts = {
        c.id: c
        for c in await session.scalars(
            select(Contact).where(Contact.business_id == business_id, Contact.id.in_(ids))
        )
    }
    hashes = [c.phone_hash for c in contacts.values()]
    opted = set(
        await session.scalars(
            select(OptOut.phone_hash)
            .where(OptOut.business_id == business_id, OptOut.phone_hash.in_(hashes))
            .where(or_(OptOut.purpose.is_(None), OptOut.purpose == "service"))
        )
    )
    out: list[Person] = []
    for contact_id in ids:
        contact = contacts.get(contact_id)
        if contact is None:
            continue
        skip, phone = None, None
        if contact.phone_hash in opted:
            skip = "opted_out"
        elif needs_phone:
            phone = await ports.contact_phone(session, contact)
            skip = None if phone else "no_number"
        out.append(Person(contact.id, contact.name, contact.phone_last4, skip=skip, phone=phone))
    return out
