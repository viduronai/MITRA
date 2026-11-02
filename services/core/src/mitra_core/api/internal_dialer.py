"""Internal dialer API (``/internal/v1/dialer``), same service-token auth as ``internal.py``.

- ``POST /tick``        run one dialer pass over every business with due work (cron / routine;
                        ``python -m mitra_core.dialer.run`` does the same in a loop)
- ``POST /callbacks``   the voice brain's ``schedule_callback`` tool (CALL-05): queue a call back
                        to the customer at the time they asked for
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.internal import require_service
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session, get_sessionmaker
from mitra_core.dialer.queue import EnqueueError, enqueue_call
from mitra_core.dialer.settings import DialerSettings, get_dialer_settings
from mitra_core.dialer.voice import VoiceDialer, make_voice_dialer
from mitra_core.dialer.worker import WorkerDeps, tick
from mitra_core.errors import AppError, not_found
from mitra_core.models import Employee, PhoneNumber
from mitra_core.pii import hash_phone
from mitra_core.schemas.campaign import CallbackIn, CallbackOut, TickOut
from mitra_core.telephony.dnd import DndProvider, get_dnd_provider
from mitra_core.telephony.enums import CallPurpose
from mitra_core.tenancy import TenantContext, set_tenant

router = APIRouter(
    prefix="/internal/v1/dialer",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)

MAX_CALLBACK_AHEAD = timedelta(days=30)
_voice: VoiceDialer | None = None


def get_voice_dialer(settings: DialerSettings = Depends(get_dialer_settings)) -> VoiceDialer:
    """FastAPI dependency (tests override it). One dialer per process."""
    global _voice
    if _voice is None:
        _voice = make_voice_dialer(settings)
    return _voice


@router.post("/tick", response_model=TickOut)
async def run_tick(
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    dialer: DialerSettings = Depends(get_dialer_settings),
    dnd: DndProvider = Depends(get_dnd_provider),
    voice: VoiceDialer = Depends(get_voice_dialer),
) -> TickOut:
    deps = WorkerDeps(settings=settings, dialer=dialer, dnd=dnd, voice=voice)
    report = await tick(get_sessionmaker(), deps, clock())
    return TickOut(
        businesses=report.businesses,
        dialed=report.dialed,
        deferred=report.deferred,
        blocked=report.blocked,
        finished=report.finished,
        paused_campaigns=report.paused_campaigns,
    )


@router.post("/callbacks", status_code=status.HTTP_201_CREATED, response_model=CallbackOut)
async def schedule_callback(
    body: CallbackIn,
    clock: Clock = Depends(get_clock),
    session: AsyncSession = Depends(get_session),
) -> CallbackOut:
    await set_tenant(session, TenantContext(business_id=body.business_id))
    employee = await session.scalar(
        select(Employee.id).where(
            Employee.id == body.employee_id, Employee.business_id == body.business_id
        )
    )
    if employee is None:
        raise not_found("Employee")
    if body.called_number_id is not None:
        owned = await session.scalar(
            select(PhoneNumber.id).where(
                PhoneNumber.id == body.called_number_id,
                PhoneNumber.business_id == body.business_id,
            )
        )
        if owned is None:
            raise not_found("Phone number")
    now = clock()
    if body.at.tzinfo is None:
        raise AppError(422, "invalid_time", "Give the callback time with a timezone")
    at = max(body.at, now)
    if at - now > MAX_CALLBACK_AHEAD:
        raise AppError(422, "too_far", "Callbacks can be scheduled up to 30 days ahead")
    variables = {"callback_note": body.note or ""} if body.note else {}
    if body.contact_name:
        variables["lead_name"] = body.contact_name
    try:
        job = await enqueue_call(
            session,
            body.business_id,
            employee_id=body.employee_id,
            phone_e164=body.contact_phone,
            purpose=CallPurpose.CALLBACK,
            variables=variables,
            source="callback",
            not_before=at,
            # One pending callback per person: asking again moves nothing, the first one stands.
            dedupe_key=f"callback:{hash_phone(body.contact_phone)[:32]}",
            called_number_id=body.called_number_id,
        )
    except EnqueueError as e:
        raise AppError(422, "invalid_callback", str(e)) from e
    out = CallbackOut(job_id=job.id, not_before=job.not_before, status=job.status.value)
    await session.commit()
    return out
