"""Onboarding checklist, derived from data on every request (contract §6)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.models import Business, Employee, Fact, TestCall
from mitra_core.models.enums import FactStatus
from mitra_core.schemas.onboarding import ProgressOut, StepKey, StepOut
from mitra_core.security import Tenant, get_tenant_session, require_business
from mitra_core.simulation import COMPLETED_AFTER_SECONDS

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

MIN_CONFIRMED_FACTS = 3


@router.get("/progress", response_model=ProgressOut, summary="Which onboarding steps are done")
async def get_progress(
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> ProgressOut:
    bid = tenant.business_id
    completed_before = clock() - timedelta(seconds=COMPLETED_AFTER_SECONDS)
    row = (
        await session.execute(
            select(
                exists().where(Business.id == bid),
                exists().where(Employee.business_id == bid),
                select(func.count())
                .select_from(Fact)
                .where(Fact.business_id == bid, Fact.status == FactStatus.CONFIRMED)
                .scalar_subquery(),
                exists().where(Employee.business_id == bid, Employee.voice_id.is_not(None)),
                exists().where(
                    TestCall.business_id == bid, TestCall.created_at <= completed_before
                ),
            )
        )
    ).one()
    has_business, has_role, confirmed, has_voice, has_call = row
    done: dict[StepKey, bool] = {
        "business": bool(has_business),
        "role": bool(has_role),
        "teach": confirmed >= MIN_CONFIRMED_FACTS,
        "voice": bool(has_voice),
        "test_call": bool(has_call),
        "go_live": False,  # going live (number + wallet) arrives in a later step
    }
    return ProgressOut(
        steps=[StepOut(key=k, done=v) for k, v in done.items()],
        percent=round(100 * sum(done.values()) / len(done)),
        next=next((k for k, v in done.items() if not v), None),
    )
