"""Home (Today) at a glance (REP-01): stat tiles, "Needs you", recent calls."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from mitra_core.calls.queries import business_tz, call_rows_stmt, day_bounds, to_row
from mitra_core.calls.service import utcnow
from mitra_core.models import Call, Contact
from mitra_core.models.enums import CallResult, CallStatus
from mitra_core.schemas.call import HomeStats, HomeSummary, NeedsYouItem
from mitra_core.security import Tenant, get_tenant_session, require_business

router = APIRouter(prefix="/home", tags=["home"])

NEEDS_YOU_WINDOW = timedelta(days=7)
RESCUE_WINDOW = timedelta(days=7)
LIVE_STALE_AFTER = timedelta(hours=2)
MAX_NEEDS_YOU = 10


@router.get("/summary", response_model=HomeSummary, summary="Today's numbers for Home")
async def home_summary(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> HomeSummary:
    biz = tenant.business_id
    tz = await business_tz(session, biz)
    now = utcnow()
    start, end = day_bounds(now.astimezone(tz).date(), tz)
    today = and_(Call.business_id == biz, Call.started_at >= start, Call.started_at < end)

    calls_today = await session.scalar(select(func.count()).where(today)) or 0
    booked = (
        await session.scalar(select(func.count()).where(today, Call.result == CallResult.BOOKED))
        or 0
    )
    # "Missed calls rescued": a caller who missed us in the last week and was reached today.
    earlier = aliased(Call)
    rescued = (
        await session.scalar(
            select(func.count(func.distinct(Call.contact_id))).where(
                today,
                Call.contact_id.is_not(None),
                Call.result.is_not(None),
                Call.result != CallResult.MISSED,
                exists().where(
                    earlier.contact_id == Call.contact_id,
                    earlier.result == CallResult.MISSED,
                    earlier.started_at < Call.started_at,
                    earlier.started_at >= Call.started_at - RESCUE_WINDOW,
                ),
            )
        )
        or 0
    )
    live = (
        await session.scalar(
            select(func.count()).where(
                Call.business_id == biz,
                Call.status == CallStatus.LIVE,
                Call.started_at >= now - LIVE_STALE_AFTER,
            )
        )
        or 0
    )
    # TODO(needs-you): resolution state per alert (done / snoozed); for now: last 7 days.
    alert_rows = await session.execute(
        select(Call.id, Call.alerts, Call.phone_last4, Call.ended_at, Call.started_at, Contact.name)
        .outerjoin(Contact, Contact.id == Call.contact_id)
        .where(
            Call.business_id == biz,
            Call.started_at >= now - NEEDS_YOU_WINDOW,
            func.jsonb_array_length(Call.alerts) > 0,
        )
        .order_by(Call.started_at.desc())
        .limit(50)
    )
    needs_you = [
        NeedsYouItem(
            call_id=call_id,
            kind=str(alert.get("kind")),
            message=str(alert.get("message")),
            contact_name=name,
            phone_last4=last4,
            at=ended or started,
        )
        for call_id, alerts, last4, ended, started, name in alert_rows
        for alert in alerts
    ]
    recent = await session.execute(
        call_rows_stmt().where(Call.business_id == biz).order_by(Call.started_at.desc()).limit(5)
    )
    recent_calls = [to_row(c, e, n) for c, e, n in recent]
    has_calls = bool(recent_calls)
    return HomeSummary(
        date=now.astimezone(tz).date().isoformat(),
        timezone=str(tz),
        has_calls=has_calls,
        stats=HomeStats(
            calls_today=calls_today,
            booked_today=booked,
            rescued_today=rescued,
            needs_you=len(needs_you),
            live_now=live,
        ),
        needs_you=needs_you[:MAX_NEEDS_YOU],
        recent_calls=recent_calls,
    )
