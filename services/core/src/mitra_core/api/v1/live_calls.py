"""Live calls (CALL-13/18): watch the transcript, whisper a private instruction, take over.

Owner and manager only. Every look (once per person per call), whisper and takeover is a
``supervisor_action`` row: who, what, when. The voice service picks up whispers and takeovers
on its next poll; the AI follows a whisper for the rest of the call but it can never override
the AI disclosure or the safety rules (enforced in the voice brain, not trusted from here).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.errors import AppError, not_found
from mitra_core.models import Call, Contact, Employee, SupervisorAction
from mitra_core.models.enums import CallDirection, CallStatus, MemberRole
from mitra_core.schemas.team import LiveCallOut, LiveDetailOut, LiveTurnOut, WhisperIn
from mitra_core.security import Tenant, get_tenant_session, require_role
from mitra_core.team.humans import clean_text

router = APIRouter(prefix="/live-calls", tags=["live calls"])
_supervisor = require_role(MemberRole.OWNER, MemberRole.MANAGER)
# A call still "live" after this long lost its end report; don't show it as live forever.
STALE_AFTER = timedelta(hours=1)
MAX_WHISPERS_PER_CALL = 20


def _out(call: Call, employee: str | None, customer: str | None) -> LiveCallOut:
    return LiveCallOut(
        id=call.id,
        employee_id=call.employee_id,
        employee_name=employee,
        direction=call.direction.value,
        phone_last4=call.phone_last4,
        customer_name=customer,
        started_at=call.started_at,
        language=call.language,
    )


@router.get("", response_model=list[LiveCallOut], summary="Calls happening now")
async def live_calls(
    tenant: Tenant = Depends(_supervisor),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> list[LiveCallOut]:
    rows = await session.execute(
        select(Call, Employee.name, Contact.name)
        .outerjoin(Employee, Employee.id == Call.employee_id)
        .outerjoin(Contact, Contact.id == Call.contact_id)
        .where(Call.business_id == tenant.business_id, Call.status == CallStatus.LIVE)
        .where(Call.direction != CallDirection.WEB)
        .where(Call.started_at >= clock() - STALE_AFTER)
        .order_by(Call.started_at.desc())
        .limit(50)
    )
    return [_out(call, employee, customer) for call, employee, customer in rows]


async def _call(session: AsyncSession, tenant: Tenant, call_id: uuid.UUID) -> Call:
    call = await session.scalar(
        select(Call).where(Call.id == call_id, Call.business_id == tenant.business_id)
    )
    if call is None:
        raise not_found("Call")
    return call


@router.get("/{call_id}", response_model=LiveDetailOut, summary="Live transcript (poll)")
async def live_detail(
    call_id: uuid.UUID,
    after: int = Query(0, ge=0, le=10_000),
    tenant: Tenant = Depends(_supervisor),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> LiveDetailOut:
    call = await _call(session, tenant, call_id)
    employee = await session.get(Employee, call.employee_id) if call.employee_id else None
    contact = await session.get(Contact, call.contact_id) if call.contact_id else None
    listened = await session.scalar(
        select(SupervisorAction.id).where(
            SupervisorAction.call_id == call.id,
            SupervisorAction.user_id == tenant.user.id,
            SupervisorAction.kind == "listen",
        )
    )
    if listened is None:
        session.add(
            SupervisorAction(
                business_id=tenant.business_id,
                call_id=call.id,
                user_id=tenant.user.id,
                kind="listen",
                created_at=clock(),
            )
        )
        await session.commit()
    actions = await session.scalars(
        select(SupervisorAction)
        .where(SupervisorAction.call_id == call.id)
        .where(SupervisorAction.kind.in_(("whisper", "takeover")))
        .order_by(SupervisorAction.created_at)
    )
    turns = [
        LiveTurnOut(seq=i, role=str(t.get("role", "")), text=str(t.get("text", "")))
        for i, t in enumerate(call.transcript)
        if i >= after
    ]
    return LiveDetailOut(
        call=_out(call, employee.name if employee else None, contact.name if contact else None),
        live=call.status == CallStatus.LIVE,
        turns=turns,
        whispers=[
            {
                "kind": a.kind,
                "text": a.text,
                "at": a.created_at.isoformat(),
                "delivered": a.delivered_at is not None,
            }
            for a in actions
        ],
    )


async def _live_call(session: AsyncSession, tenant: Tenant, call_id: uuid.UUID) -> Call:
    call = await _call(session, tenant, call_id)
    if call.status != CallStatus.LIVE:
        raise AppError(409, "call_ended", "This call has already ended")
    return call


@router.post(
    "/{call_id}/whisper",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Private instruction the AI follows for the rest of the call",
)
async def whisper(
    call_id: uuid.UUID,
    body: WhisperIn,
    tenant: Tenant = Depends(_supervisor),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> dict[str, str]:
    call = await _live_call(session, tenant, call_id)
    sent = len(
        list(
            await session.scalars(
                select(SupervisorAction.id).where(
                    SupervisorAction.call_id == call.id, SupervisorAction.kind == "whisper"
                )
            )
        )
    )
    if sent >= MAX_WHISPERS_PER_CALL:
        raise AppError(429, "too_many_whispers", "Too many instructions for one call")
    text = clean_text(body.text, 300)
    if not text:
        raise AppError(422, "validation_error", "Instruction is empty")
    session.add(
        SupervisorAction(
            business_id=tenant.business_id,
            call_id=call.id,
            user_id=tenant.user.id,
            kind="whisper",
            text=text,
            created_at=clock(),
        )
    )
    await session.commit()
    return {"status": "queued"}


@router.post(
    "/{call_id}/takeover",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Transfer this call to my phone",
)
async def takeover(
    call_id: uuid.UUID,
    tenant: Tenant = Depends(_supervisor),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> dict[str, str]:
    call = await _live_call(session, tenant, call_id)
    pending = await session.scalar(
        select(SupervisorAction.id).where(
            SupervisorAction.call_id == call.id,
            SupervisorAction.kind == "takeover",
            SupervisorAction.delivered_at.is_(None),
        )
    )
    if pending is None:
        session.add(
            SupervisorAction(
                business_id=tenant.business_id,
                call_id=call.id,
                user_id=tenant.user.id,
                kind="takeover",
                created_at=clock(),
            )
        )
        await session.commit()
    return {"status": "connecting", "to_last4": tenant.user.phone_e164[-4:]}
