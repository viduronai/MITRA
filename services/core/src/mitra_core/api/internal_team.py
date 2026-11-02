"""Internal team API for the voice service (``/internal/v1/team``), service-token auth.

* ``GET  /ladder?employee_id=``            who to ring for a warm transfer, and the callback
  promise to make if nobody answers (CALL-06/19)
* ``POST /handoff-cards``                  message taken after the ladder failed (+ WhatsApp)
* ``POST /live/{call_id}/turns``           one live transcript turn; answers with any pending
  supervisor instructions (CALL-13/18)
* ``GET  /live/{call_id}/instructions``    the same instructions, polled between turns
* ``POST /tick``                           run due routines / follow-ups once (scheduler)

Tenancy as in ``internal_calls``: the employee id maps to its business through the SECURITY
DEFINER lookup, then everything goes through RLS.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.internal import require_service
from mitra_core.api.internal_calls import _bind_employee_tenant
from mitra_core.clock import Clock, get_clock
from mitra_core.db import get_session
from mitra_core.models import Business, Call
from mitra_core.schemas.team import (
    CardCreatedOut,
    CardIn,
    InstructionsOut,
    LadderOut,
    LadderStepOut,
    LiveTurnIn,
)
from mitra_core.team import scheduler
from mitra_core.team.humans import (
    append_turn,
    callback_promise,
    create_card,
    ladder,
    take_instructions,
)

router = APIRouter(
    prefix="/internal/v1/team",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)


@router.get("/ladder", response_model=LadderOut)
async def get_ladder(
    employee_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> LadderOut:
    business_id = await _bind_employee_tenant(session, employee_id)
    business = await session.get(Business, business_id)
    steps = await ladder(session, business_id)
    by, local, day = callback_promise(clock(), business.timezone if business else "Asia/Kolkata")
    return LadderOut(
        steps=[LadderStepOut(**asdict(s)) for s in steps],
        callback_by=by,
        callback_local=local,
        callback_day="today" if day == "today" else "tomorrow",
    )


@router.post("/handoff-cards", response_model=CardCreatedOut, status_code=status.HTTP_201_CREATED)
async def handoff_card(
    body: CardIn,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> CardCreatedOut:
    business_id = await _bind_employee_tenant(session, body.employee_id)
    card = await create_card(
        session,
        business_id,
        employee_id=body.employee_id,
        call_id=body.call_id,
        caller_phone=body.caller_phone,
        reason=body.reason,
        message=body.message,
        attempts=body.attempts,
        now=clock(),
    )
    await session.commit()
    return CardCreatedOut(id=card.id, callback_by=card.callback_by)


async def _instructions(
    session: AsyncSession, business_id: uuid.UUID, call_id: uuid.UUID, clock: Clock
) -> InstructionsOut:
    items = await take_instructions(session, business_id, call_id, clock())
    await session.commit()
    return InstructionsOut(instructions=items)


@router.post("/live/{call_id}/turns", response_model=InstructionsOut)
async def live_turn(
    call_id: uuid.UUID,
    body: LiveTurnIn,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> InstructionsOut:
    business_id = await _bind_employee_tenant(session, body.employee_id)
    call = await session.scalar(
        select(Call).where(Call.id == call_id, Call.business_id == business_id).with_for_update()
    )
    if call is not None and body.text.strip():
        await append_turn(session, call, body.role, body.text)
    return await _instructions(session, business_id, call_id, clock)


@router.get("/live/{call_id}/instructions", response_model=InstructionsOut)
async def live_instructions(
    call_id: uuid.UUID,
    employee_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> InstructionsOut:
    business_id = await _bind_employee_tenant(session, employee_id)
    return await _instructions(session, business_id, call_id, clock)


@router.post("/tick")
async def tick(clock: Clock = Depends(get_clock)) -> dict[str, int]:
    result = await scheduler.tick(clock())
    return asdict(result)
