"""Read-side queries shared by the Calls, Customers and Home endpoints."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import Business, Call, Contact, Employee
from mitra_core.models.enums import CallDirection, CallResult, Locale
from mitra_core.schemas.call import CallRow

DEFAULT_TZ = "Asia/Kolkata"


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def business_tz(session: AsyncSession, business_id: uuid.UUID) -> ZoneInfo:
    tz = await session.scalar(select(Business.timezone).where(Business.id == business_id))
    try:
        return ZoneInfo(tz or DEFAULT_TZ)
    except (KeyError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


@dataclass(frozen=True, slots=True)
class CallFilters:
    results: list[CallResult]
    employee_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    language: Locale | None = None
    direction: CallDirection | None = None
    date_from: date | None = None
    date_to: date | None = None
    q: str | None = None


RowsSelect = Select[Call, str, str | None]


def call_rows_stmt() -> RowsSelect:
    return (
        select(Call, Employee.name, Contact.name)
        .outerjoin(Employee, Employee.id == Call.employee_id)
        .outerjoin(Contact, Contact.id == Call.contact_id)
    )


def apply_filters(
    stmt: RowsSelect, business_id: uuid.UUID, f: CallFilters, tz: ZoneInfo
) -> RowsSelect:
    stmt = stmt.where(Call.business_id == business_id)
    if f.results:
        stmt = stmt.where(Call.result.in_(f.results))
    if f.employee_id:
        stmt = stmt.where(Call.employee_id == f.employee_id)
    if f.contact_id:
        stmt = stmt.where(Call.contact_id == f.contact_id)
    if f.language:
        stmt = stmt.where(Call.language == f.language)
    if f.direction:
        stmt = stmt.where(Call.direction == f.direction)
    if f.date_from:
        stmt = stmt.where(Call.started_at >= day_bounds(f.date_from, tz)[0])
    if f.date_to:
        stmt = stmt.where(Call.started_at < day_bounds(f.date_to, tz)[1])
    if f.q:
        pattern = f"%{escape_like(f.q.lower())}%"
        stmt = stmt.where(
            or_(
                Call.transcript_text.like(pattern, escape="\\"),
                func.lower(func.coalesce(Call.summary, "")).like(pattern, escape="\\"),
                func.lower(func.coalesce(Contact.name, "")).like(pattern, escape="\\"),
            )
        )
    return stmt


def to_row(call: Call, employee_name: str | None, contact_name: str | None) -> CallRow:
    return CallRow(
        id=call.id,
        employee_id=call.employee_id,
        employee_name=employee_name,
        contact_id=call.contact_id,
        contact_name=contact_name,
        phone_last4=call.phone_last4,
        direction=call.direction,
        status=call.status,
        language=call.language,
        started_at=call.started_at,
        duration_seconds=call.duration_seconds,
        result=call.result,
        summary=call.summary,
        rating=call.rating,
    )


async def list_calls(
    session: AsyncSession,
    business_id: uuid.UUID,
    filters: CallFilters,
    *,
    limit: int,
    offset: int,
) -> tuple[list[CallRow], int]:
    tz = await business_tz(session, business_id)
    stmt = apply_filters(call_rows_stmt(), business_id, filters, tz)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.execute(
        stmt.order_by(Call.started_at.desc(), Call.id).limit(limit).offset(offset)
    )
    return [to_row(c, e, n) for c, e, n in rows], total
