"""Internal billing API for the voice/calls services (``/internal/v1``, service token).

* ``POST /internal/v1/usage``: rate one finished call (idempotent by ``call_id``).
* ``GET /internal/v1/billing/allowance``: may a call start, and for how many seconds.
* ``POST /internal/v1/billing/passthrough``: an at-cost extra (WhatsApp, SMS, verification).
* ``POST /internal/v1/billing/number-rental``: month close for dedicated numbers (waiver rule).

Tenancy as in ``internal.py``: the employee id is mapped to its business by the SECURITY DEFINER
``internal_employee_business``; endpoints that take a ``business_id`` trust the service caller.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import idempotency
from mitra_core.api.internal import require_service
from mitra_core.billing import rating, service
from mitra_core.billing.providers import PaymentProvider, get_payment_provider
from mitra_core.billing.rating import Balances, CallDirection
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import not_found
from mitra_core.models import Employee
from mitra_core.schemas.billing import (
    AllowanceOut,
    NumberRentalIn,
    NumberRentalOut,
    PassthroughIn,
    PassthroughOut,
    UsageIn,
    UsageOut,
)
from mitra_core.tenancy import TenantContext, set_tenant

_LOOKUP = text("SELECT internal_employee_business(:id)")

router = APIRouter(
    prefix="/internal/v1",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)


async def _bind_employee(session: AsyncSession, employee_id: uuid.UUID) -> uuid.UUID:
    business_id = (await session.execute(_LOOKUP, {"id": employee_id})).scalar_one_or_none()
    if business_id is None:
        raise not_found("Employee")
    await set_tenant(session, TenantContext(business_id=business_id))
    return business_id  # type: ignore[no-any-return]


async def _bind_business(session: AsyncSession, business_id: uuid.UUID) -> None:
    await set_tenant(session, TenantContext(business_id=business_id))


@router.post("/usage", response_model=UsageOut)
async def record_usage(
    body: UsageIn,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    provider: PaymentProvider = Depends(get_payment_provider),
    settings: Settings = Depends(get_settings),
) -> UsageOut:
    business_id = await _bind_employee(session, body.employee_id)
    result = await service.record_usage(
        session,
        business_id,
        service.UsageInput(
            call_id=body.call_id,
            employee_id=body.employee_id,
            direction=body.direction,
            outcome=body.outcome,
            connected_seconds=body.connected_seconds,
            started_at=body.started_at,
            request_hash=idempotency.request_hash(body.model_dump(mode="json")),
        ),
        now=clock(),
        provider=provider,
        settings=settings,
    )
    event, wallet = result.event, result.wallet
    out = UsageOut(
        usage_event_id=event.id,
        call_id=event.call_id,
        billable_seconds=event.billable_seconds,
        grace_seconds=event.grace_seconds,
        tier=event.tier,
        rate_paise_per_min=event.rate_paise_per_min,
        amount_paise=event.amount_paise,
        balance_paise=wallet.balance_paise,
        bonus_paise=wallet.bonus_paise,
        outbound_paused=result.status.outbound_paused,
        pause_reason=result.status.pause_reason,
        low_balance=result.low_balance,
        low_balance_alert=result.low_balance_alert,
        autopay_topup_id=result.autopay_topup.id if result.autopay_topup else None,
        replayed=result.replayed,
    )
    await session.commit()
    return out


@router.get("/billing/allowance", response_model=AllowanceOut)
async def get_allowance(
    employee_id: uuid.UUID = Query(...),
    direction: CallDirection = Query(...),
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> AllowanceOut:
    business_id = await _bind_employee(session, employee_id)
    now = clock()
    wallet = await service.lock_wallet(session, business_id, now)
    employee = await session.scalar(
        select(Employee).where(Employee.id == employee_id, Employee.business_id == business_id)
    )
    if employee is None:
        raise not_found("Employee")
    rate = await service.current_rate(session, employee.voice_tier, now)
    allowed = rating.allowance(
        direction,
        Balances(wallet.balance_paise, wallet.bonus_paise),
        rate_paise_per_min=rate,
        monthly_cap=wallet.monthly_cap_paise,
        month_usage=wallet.month_usage_paise,
        grace_used_today=wallet.grace_seconds_used,
    )
    await session.commit()  # keeps the lazily created / rolled-over wallet
    return AllowanceOut(
        allowed=allowed.allowed,
        reason=allowed.reason,
        max_seconds=allowed.max_seconds,
        tier=employee.voice_tier,
        rate_paise_per_min=rate,
    )


@router.post("/billing/passthrough", response_model=PassthroughOut)
async def post_passthrough(
    body: PassthroughIn,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> PassthroughOut:
    await _bind_business(session, body.business_id)
    now = clock()
    wallet = await service.lock_wallet(session, body.business_id, now)
    txn, created = await service.post_passthrough(
        session,
        wallet,
        category=body.category,
        amount_paise=body.amount_paise,
        ref=body.ref,
        description=body.description,
        now=now,
    )
    out = PassthroughOut(
        txn_id=txn.id,
        created=created,
        balance_paise=wallet.balance_paise,
        bonus_paise=wallet.bonus_paise,
    )
    await session.commit()
    return out


@router.post("/billing/number-rental", response_model=NumberRentalOut)
async def close_number_rental(
    body: NumberRentalIn,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> NumberRentalOut:
    """Charge (or waive) a month's number rental. Call after the month ends; idempotent."""
    await _bind_business(session, body.business_id)
    now = clock()
    wallet = await service.lock_wallet(session, body.business_id, now)
    year, month = (int(p) for p in body.month.split("-"))
    usage = await service.usage_in_month(session, body.business_id, date(year, month, 1))
    rental = rating.number_rental(usage, body.numbers)
    txn_id = None
    if rental.amount_paise:
        txn, _ = await service.post_passthrough(
            session,
            wallet,
            category="number_rental",
            amount_paise=rental.amount_paise,
            ref=f"number_rental:{body.month}",
            description=f"Dedicated number rental · {body.month} · {body.numbers} number(s)",
            now=now,
        )
        txn_id = txn.id
    await session.commit()
    return NumberRentalOut(
        month=body.month,
        usage_paise=usage,
        amount_paise=rental.amount_paise,
        waived=rental.waived,
        txn_id=txn_id,
    )
