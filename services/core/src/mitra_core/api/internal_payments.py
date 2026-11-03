"""Internal payments API for the voice service (``/internal/v1/payments``), service-token auth.

* ``POST /links``  an AI employee sends the caller a payment link (``send_payment_link`` tool).
  The voice service only passes amounts grounded in the business's knowledge or the call's
  brief; core still applies the owner's "Ask me first" rules (discounts, big amounts).
  Idempotent by ``client_ref`` (e.g. ``call:<call id>:1``).
* ``POST /tick``   run the payment reminder step once (scheduler).

Tenancy as in ``internal_calls``: the employee id maps to its business through the SECURITY
DEFINER lookup, then everything goes through RLS.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.internal import require_service
from mitra_core.api.internal_calls import _bind_employee_tenant
from mitra_core.clock import Clock, get_clock
from mitra_core.db import get_session
from mitra_core.models import Call
from mitra_core.payments import (
    approval_handlers,  # noqa: F401  (registers the handler)
    scheduler,
    service,
)
from mitra_core.schemas.payments import (
    InternalPaymentLinkIn,
    InternalPaymentLinkOut,
    PaymentTickOut,
)

router = APIRouter(
    prefix="/internal/v1/payments",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)


@router.post("/links", response_model=InternalPaymentLinkOut, status_code=status.HTTP_201_CREATED)
async def create_link(
    body: InternalPaymentLinkIn,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> InternalPaymentLinkOut:
    business_id = await _bind_employee_tenant(session, body.employee_id)
    call_id = None
    if body.call_id is not None:
        call_id = await session.scalar(
            select(Call.id).where(Call.id == body.call_id, Call.business_id == business_id)
        )
    req = await service.create_request(
        session,
        business_id,
        service.NewRequest(
            amount_paise=body.amount_paise,
            purpose=body.purpose,
            source="employee",
            phone_e164=body.contact_phone,
            employee_id=body.employee_id,
            call_id=call_id,
            client_ref=body.client_ref,
            discount_percent=body.discount_percent,
        ),
        now=clock(),
    )
    out = InternalPaymentLinkOut(
        payment_request_id=req.id,
        status=req.status,  # type: ignore[arg-type]
        needs_approval=req.status == "awaiting_approval",
    )
    await session.commit()
    return out


@router.post("/tick", response_model=PaymentTickOut)
async def tick(clock: Clock = Depends(get_clock)) -> PaymentTickOut:
    return PaymentTickOut(**asdict(await scheduler.tick(clock())))
