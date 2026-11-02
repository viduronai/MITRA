"""Calls list, detail, rating and CSV export (REP-02, CALL-11/12, REP-05, REP-06)."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.labels import VISIBLE_ACTIONS, action_label
from mitra_core.calls.queries import (
    CallFilters,
    apply_filters,
    business_tz,
    call_rows_stmt,
    list_calls,
    to_row,
)
from mitra_core.calls.service import utcnow
from mitra_core.errors import not_found
from mitra_core.models import Call, CallAction
from mitra_core.models.enums import CallDirection, CallResult, Locale, MemberRole
from mitra_core.schemas.call import (
    ActionOut,
    AlertOut,
    CallDetail,
    CallList,
    RatingIn,
    RatingOut,
    TranscriptLine,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role

router = APIRouter(prefix="/calls", tags=["calls"])

_can_export = require_role(MemberRole.OWNER, MemberRole.MANAGER)
EXPORT_LIMIT = 5_000
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _filters(
    result: list[CallResult] = Query(default=[]),
    employee_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    language: Locale | None = None,
    direction: CallDirection | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(None, min_length=1, max_length=100),
) -> CallFilters:
    return CallFilters(
        results=result,
        employee_id=employee_id,
        contact_id=contact_id,
        language=language,
        direction=direction,
        date_from=date_from,
        date_to=date_to,
        q=q.strip() if q and q.strip() else None,
    )


@router.get("", response_model=CallList, summary="List calls (filters, transcript search)")
async def get_calls(
    filters: CallFilters = Depends(_filters),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> CallList:
    rows, total = await list_calls(session, tenant.business_id, filters, limit=limit, offset=offset)
    return CallList(items=rows, total=total)


def _cell(value: object) -> str:
    """CSV cell, neutralising spreadsheet formulas (CSV injection)."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


@router.get(
    "/export.csv",
    response_class=Response,
    summary="Export calls as CSV (same filters as the list)",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_calls(
    filters: CallFilters = Depends(_filters),
    tenant: Tenant = Depends(_can_export),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    tz = await business_tz(session, tenant.business_id)
    stmt = apply_filters(call_rows_stmt(), tenant.business_id, filters, tz)
    rows = await session.execute(stmt.order_by(Call.started_at.desc()).limit(EXPORT_LIMIT))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "started_at",
            "employee",
            "customer",
            "phone_last4",
            "direction",
            "language",
            "duration_seconds",
            "result",
            "summary",
            "fields",
            "rating",
        ]
    )
    for call, employee_name, contact_name in rows:
        fields = "; ".join(f"{k}={v}" for k, v in call.fields.items())
        writer.writerow(
            [
                _cell(v)
                for v in (
                    call.started_at.astimezone(tz).isoformat(timespec="seconds"),
                    employee_name,
                    contact_name,
                    call.phone_last4,
                    call.direction.value,
                    call.language.value if call.language else "",
                    call.duration_seconds,
                    call.result.value if call.result else "",
                    call.summary,
                    fields,
                    call.rating.value if call.rating else "",
                )
            ]
        )
    filename = f"mitra-calls-{utcnow().astimezone(tz).date().isoformat()}.csv"
    return Response(
        content="﻿" + buf.getvalue(),  # BOM so Excel reads UTF-8 (Telugu / Hindi)
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _get_call(session: AsyncSession, tenant: Tenant, call_id: uuid.UUID) -> Call:
    call = await session.scalar(
        select(Call).where(Call.id == call_id, Call.business_id == tenant.business_id)
    )
    if call is None:
        raise not_found("Call")
    return call


@router.get("/{call_id}", response_model=CallDetail, summary="One call with transcript")
async def get_call(
    call_id: uuid.UUID,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> CallDetail:
    row = (
        await session.execute(
            call_rows_stmt().where(Call.id == call_id, Call.business_id == tenant.business_id)
        )
    ).first()
    if row is None:
        raise not_found("Call")
    call, employee_name, contact_name = row
    actions = await session.scalars(
        select(CallAction).where(CallAction.call_id == call.id).order_by(CallAction.seq)
    )
    return CallDetail(
        **to_row(call, employee_name, contact_name).model_dump(),
        ended_at=call.ended_at,
        next_step=call.next_step,
        sentiment=call.sentiment,
        fields=call.fields,
        transcript=[
            TranscriptLine(
                speaker="caller" if t.get("role") == "user" else "employee",
                text=str(t.get("text", "")),
                interrupted=bool(t.get("interrupted", False)),
                at_ms=t.get("at_ms"),
            )
            for t in call.transcript
        ],
        actions=[
            ActionOut(
                name=a.name,
                args=a.args,
                result=a.result,
                ok=a.ok,
                label=action_label(a.name, a.args, a.result),
            )
            for a in actions
            if a.name in VISIBLE_ACTIONS
        ],
        alerts=[AlertOut.model_validate(a) for a in call.alerts],
        unknown_questions=call.unknown_questions,
        recording_uri=call.recording_uri,
        rating_reason=call.rating_reason,
        latency_stats=call.latency_stats,
    )


@router.post("/{call_id}/rating", response_model=RatingOut, summary="Rate a call 👍 / 👎")
async def rate_call(
    call_id: uuid.UUID,
    body: RatingIn,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> RatingOut:
    # Setting a rating is naturally idempotent (last write wins), so no Idempotency-Key.
    call = await _get_call(session, tenant, call_id)
    call.rating = body.rating
    call.rating_reason = body.reason
    call.rated_by = tenant.user.id
    call.rated_at = utcnow()
    await session.flush()
    await session.commit()
    return RatingOut(
        id=call.id, rating=body.rating, rating_reason=body.reason, rated_at=call.rated_at
    )
