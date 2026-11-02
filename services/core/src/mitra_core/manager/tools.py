"""Read-only Manager tools over ONE business's data (MGR-02).

Every query filters on ``business_id`` explicitly AND runs under RLS (the session is bound to
the business), so a tool can never see another tenant. Tools return plain data; the answer
text is composed from these values only (``answers.py``), never from model guesses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.queries import business_tz, day_bounds, escape_like
from mitra_core.models import (
    Approval,
    Call,
    Commitment,
    Contact,
    Employee,
    InteractionSummary,
)
from mitra_core.models.enums import CallResult, CommitmentStatus

Period = Literal["today", "yesterday", "week"]
MAX_ROWS = 5


@dataclass(frozen=True, slots=True)
class Window:
    start: datetime
    end: datetime
    label: Period


@dataclass(slots=True)
class CallStats:
    period: Period
    total: int = 0
    by_result: dict[str, int] = field(default_factory=dict)
    unknown_questions: int = 0


@dataclass(frozen=True, slots=True)
class CallBrief:
    call_id: uuid.UUID
    who: str
    result: str | None
    summary: str | None
    at: datetime


@dataclass(frozen=True, slots=True)
class AttentionItem:
    kind: str
    message: str
    call_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None


async def window(
    session: AsyncSession, business_id: uuid.UUID, period: Period, now: datetime
) -> Window:
    tz = await business_tz(session, business_id)
    today = now.astimezone(tz).date()
    if period == "today":
        start, end = day_bounds(today, tz)
    elif period == "yesterday":
        start, end = day_bounds(today - timedelta(days=1), tz)
    else:
        start, _ = day_bounds(today - timedelta(days=6), tz)
        _, end = day_bounds(today, tz)
    return Window(start, end, period)


def _who(name: str | None, last4: str | None) -> str:
    return name or (f"…{last4}" if last4 else "A caller")


async def call_stats(
    session: AsyncSession, business_id: uuid.UUID, period: Period, now: datetime
) -> CallStats:
    w = await window(session, business_id, period, now)
    rows = await session.execute(
        select(Call.result, func.count())
        .where(Call.business_id == business_id, Call.started_at >= w.start, Call.started_at < w.end)
        .group_by(Call.result)
    )
    stats = CallStats(period=period)
    for result, count in rows:
        stats.total += count
        if result is not None:
            stats.by_result[result.value] = count
    stats.unknown_questions = (
        await session.scalar(
            select(
                func.coalesce(func.sum(func.jsonb_array_length(Call.unknown_questions)), 0)
            ).where(
                Call.business_id == business_id,
                Call.started_at >= w.start,
                Call.started_at < w.end,
            )
        )
        or 0
    )
    return stats


async def search_calls(
    session: AsyncSession, business_id: uuid.UUID, query: str, now: datetime, days: int = 30
) -> list[CallBrief]:
    """Calls in the last ``days`` whose transcript or summary mentions ``query``."""
    needle = f"%{escape_like(query.lower().strip()[:80])}%"
    rows = await session.execute(
        select(Call, Contact.name)
        .outerjoin(Contact, Contact.id == Call.contact_id)
        .where(
            Call.business_id == business_id,
            Call.started_at >= now - timedelta(days=days),
            or_(
                Call.transcript_text.like(needle, escape="\\"),
                func.lower(Call.summary).like(needle, escape="\\"),
            ),
        )
        .order_by(Call.started_at.desc())
        .limit(MAX_ROWS)
    )
    return [
        CallBrief(
            c.id,
            _who(n, c.phone_last4),
            c.result.value if c.result else None,
            c.summary,
            c.started_at,
        )
        for c, n in rows
    ]


async def calls_with_result(
    session: AsyncSession,
    business_id: uuid.UUID,
    results: list[CallResult],
    period: Period,
    now: datetime,
    limit: int = 200,
) -> list[tuple[Call, Contact | None]]:
    w = await window(session, business_id, period, now)
    rows = await session.execute(
        select(Call, Contact)
        .outerjoin(Contact, Contact.id == Call.contact_id)
        .where(
            Call.business_id == business_id,
            Call.started_at >= w.start,
            Call.started_at < w.end,
            Call.result.in_(results),
        )
        .order_by(Call.started_at.desc())
        .limit(limit)
    )
    return [(c, ct) for c, ct in rows]


async def find_contacts(
    session: AsyncSession, business_id: uuid.UUID, name: str
) -> list[tuple[Contact, str | None]]:
    """Customers whose name contains ``name``, with their latest call summary."""
    needle = f"%{escape_like(name.lower().strip()[:60])}%"
    contacts = list(
        await session.scalars(
            select(Contact)
            .where(
                Contact.business_id == business_id,
                func.lower(Contact.name).like(needle, escape="\\"),
            )
            .order_by(Contact.updated_at.desc())
            .limit(MAX_ROWS)
        )
    )
    out: list[tuple[Contact, str | None]] = []
    for contact in contacts:
        summary = await session.scalar(
            select(InteractionSummary.summary)
            .where(
                InteractionSummary.business_id == business_id,
                InteractionSummary.contact_id == contact.id,
            )
            .order_by(InteractionSummary.created_at.desc())
            .limit(1)
        )
        out.append((contact, summary))
    return out


async def bookings_on(
    session: AsyncSession, business_id: uuid.UUID, day: date
) -> list[tuple[Commitment, str]]:
    """Open appointments due on ``day`` (business local date)."""
    tz = await business_tz(session, business_id)
    start, end = day_bounds(day, tz)
    rows = await session.execute(
        select(Commitment, Contact.name, Contact.phone_last4)
        .outerjoin(Contact, Contact.id == Commitment.contact_id)
        .where(
            Commitment.business_id == business_id,
            Commitment.kind == "appointment",
            Commitment.status == CommitmentStatus.OPEN,
            Commitment.due_at >= start,
            Commitment.due_at < end,
        )
        .order_by(Commitment.due_at)
    )
    return [(c, _who(n, l4)) for c, n, l4 in rows]


async def local_date(
    session: AsyncSession, business_id: uuid.UUID, now: datetime, offset: int = 0
) -> date:
    tz = await business_tz(session, business_id)
    return now.astimezone(tz).date() + timedelta(days=offset)


async def needs_attention(
    session: AsyncSession, business_id: uuid.UUID, now: datetime, days: int = 2
) -> list[AttentionItem]:
    """Pending approvals first, then call alerts from the last ``days`` days."""
    items: list[AttentionItem] = [
        AttentionItem("approval", a.summary, approval_id=a.id)
        for a in await session.scalars(
            select(Approval)
            .where(Approval.business_id == business_id, Approval.status == "pending")
            .order_by(Approval.created_at.desc())
            .limit(MAX_ROWS)
        )
    ]
    rows = await session.execute(
        select(Call.id, Call.alerts)
        .where(
            Call.business_id == business_id,
            Call.started_at >= now - timedelta(days=days),
            func.jsonb_array_length(Call.alerts) > 0,
        )
        .order_by(Call.started_at.desc())
        .limit(20)
    )
    for call_id, alerts in rows:
        for alert in alerts:
            items.append(AttentionItem(str(alert.get("kind")), str(alert.get("message")), call_id))
    return items


async def unknown_questions(
    session: AsyncSession, business_id: uuid.UUID, period: Period, now: datetime
) -> list[str]:
    w = await window(session, business_id, period, now)
    rows = await session.scalars(
        select(Call.unknown_questions).where(
            Call.business_id == business_id,
            Call.started_at >= w.start,
            Call.started_at < w.end,
            func.jsonb_array_length(Call.unknown_questions) > 0,
        )
    )
    seen: dict[str, int] = {}
    for questions in rows:
        for q in questions:
            key = str(q).strip()
            if key:
                seen[key] = seen.get(key, 0) + 1
    return [q for q, _ in sorted(seen.items(), key=lambda kv: -kv[1])][:MAX_ROWS]


async def employees(session: AsyncSession, business_id: uuid.UUID) -> list[Employee]:
    return list(
        await session.scalars(
            select(Employee)
            .where(Employee.business_id == business_id)
            .order_by(Employee.created_at)
        )
    )


async def find_employee(
    session: AsyncSession, business_id: uuid.UUID, name: str
) -> Employee | None:
    wanted = name.strip().lower()
    for emp in await employees(session, business_id):
        if emp.name.lower() == wanted or emp.name.lower().startswith(wanted):
            return emp
    return None


async def wallet_paise(session: AsyncSession, business_id: uuid.UUID) -> int | None:
    """Spendable balance in paise, or None when the business has no wallet yet (read-only)."""
    from mitra_core.models.billing import Wallet

    wallet = await session.get(Wallet, business_id)
    if wallet is None:
        return None
    return wallet.balance_paise + wallet.bonus_paise
