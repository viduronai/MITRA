"""Internal call ingest from the voice service (``/internal/v1/calls``), service-token auth.

* ``POST /internal/v1/calls`` — call connected. Idempotent on the voice-generated ``id``
  (201 first time, 200 on a retry). Returns the caller's memory card for returning callers.
* ``POST /internal/v1/calls/{id}/end`` — transcript, actions, latency, usage. Idempotent: a
  repeated end report answers 200 with ``replayed: true`` and changes nothing. Phone calls
  (not browser test calls) are rated into the wallet in the same transaction; post-call
  processing then runs in the background.

Tenancy as in ``internal.py``: the employee id is mapped to its business by the SECURITY
DEFINER lookup, the tenant is bound, and every read/write goes through RLS.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import idempotency
from mitra_core.api.internal import require_service
from mitra_core.billing import service as billing
from mitra_core.billing.providers import PaymentProvider, get_payment_provider
from mitra_core.billing.rating import CallDirection as BilledDirection
from mitra_core.billing.rating import CallOutcome
from mitra_core.calls.service import caller_card, end_call, run_post_call, start_call
from mitra_core.calls.summarizer import Summarizer, get_summarizer
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError, not_found
from mitra_core.models import Call, Employee
from mitra_core.models.enums import CallDirection
from mitra_core.schemas.billing import UsageIn
from mitra_core.schemas.call import CallEndIn, CallEndOut, CallStartIn, CallStartOut
from mitra_core.tenancy import TenantContext, set_tenant

router = APIRouter(
    prefix="/internal/v1/calls",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)

_LOOKUP = text("SELECT internal_employee_business(:id)")


def summarizer_dep(settings: Settings = Depends(get_settings)) -> Summarizer:
    return get_summarizer(settings)


async def _bind_employee_tenant(session: AsyncSession, employee_id: uuid.UUID) -> uuid.UUID:
    business_id = (await session.execute(_LOOKUP, {"id": employee_id})).scalar_one_or_none()
    if business_id is None:
        raise not_found("Employee")
    await set_tenant(session, TenantContext(business_id=business_id))
    employee = await session.scalar(
        select(Employee.id).where(Employee.id == employee_id, Employee.business_id == business_id)
    )
    if employee is None:
        raise not_found("Employee")
    return business_id  # type: ignore[no-any-return]


@router.post("", response_model=CallStartOut, status_code=status.HTTP_201_CREATED)
async def report_call_start(
    body: CallStartIn, response: Response, session: AsyncSession = Depends(get_session)
) -> CallStartOut:
    business_id = await _bind_employee_tenant(session, body.employee_id)
    try:
        call, contact, created = await start_call(session, business_id, body)
        card = await caller_card(session, contact, exclude_call=call.id) if contact else None
        await session.commit()
    except IntegrityError:
        # The id exists under another tenant (invisible through RLS): never reuse it.
        await session.rollback()
        raise AppError(409, "conflict", "Call id already in use") from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return CallStartOut(id=call.id, status=call.status, caller=card)


@router.post("/{call_id}/end", response_model=CallEndOut)
async def report_call_end(
    call_id: uuid.UUID,
    body: CallEndIn,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    summarizer: Summarizer = Depends(summarizer_dep),
    clock: Clock = Depends(get_clock),
    provider: PaymentProvider = Depends(get_payment_provider),
    settings: Settings = Depends(get_settings),
) -> CallEndOut:
    business_id = await _bind_employee_tenant(session, body.employee_id)
    call = await session.scalar(
        select(Call).where(Call.id == call_id, Call.business_id == business_id)
    )
    if call is None:
        raise not_found("Call")
    if body.ended_at < call.started_at:
        raise AppError(422, "validation_error", "ended_at is before the call started")
    changed = await end_call(session, call, body)
    if changed and call.direction != CallDirection.WEB:
        await _bill(session, call, body, business_id, clock, provider, settings)
    await session.commit()
    if changed:
        # TODO(temporal): durable workflow instead of an in-process task.
        background.add_task(run_post_call, call.id, business_id, summarizer)
    return CallEndOut(id=call.id, status=call.status, replayed=not changed)


async def _bill(
    session: AsyncSession,
    call: Call,
    body: CallEndIn,
    business_id: uuid.UUID,
    clock: Clock,
    provider: PaymentProvider,
    settings: Settings,
) -> None:
    """Rate a finished phone call. A call reaches the voice service only once it connected.

    Hashed like ``POST /internal/v1/usage`` so a later explicit report of the same call replays.
    """
    usage = UsageIn(
        call_id=str(call.id),
        employee_id=body.employee_id,
        direction=BilledDirection(call.direction.value),
        outcome=CallOutcome.CONNECTED,
        connected_seconds=(body.ended_at - call.started_at).total_seconds(),
        started_at=call.started_at,
    )
    await billing.record_usage(
        session,
        business_id,
        billing.UsageInput(
            call_id=usage.call_id,
            employee_id=usage.employee_id,
            direction=usage.direction,
            outcome=usage.outcome,
            connected_seconds=usage.connected_seconds,
            started_at=usage.started_at,
            request_hash=idempotency.request_hash(usage.model_dump(mode="json")),
        ),
        now=clock(),
        provider=provider,
        settings=settings,
    )
