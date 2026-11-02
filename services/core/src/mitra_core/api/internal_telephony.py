"""Internal telephony API (``/internal/v1/telephony``) for the voice service and routines.

Same service-token auth as ``internal.py``. Inbound resolution maps the dialled number to its
business through a SECURITY DEFINER lookup, then binds that tenant; every other endpoint takes
the ``business_id`` explicitly and binds it before touching a table, so RLS still confines each
request to one business.

- ``GET  /resolve?to=&from=``         dialled number -> business + answering employee
- ``POST /compliance/check``          ``compliance.check(contact, purpose, time, number)``
- ``POST /attempts``, ``PATCH /attempts/{id}``   dial attempts + outcomes (caps, answer rate)
- ``POST /opt-outs``, ``POST /consents``         CMP-06 suppression, CMP-03 consent capture
- ``PATCH /numbers/{id}``             carrier / verification updates (KYC approved, spam label)
- ``POST /health/run``                number-health monitor job (all businesses)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.internal import require_service
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError, not_found
from mitra_core.models import Business, ConsentRecord, OptOut, OutboundAttempt, PhoneNumber
from mitra_core.pii import hash_phone
from mitra_core.schemas.common import E164Phone
from mitra_core.schemas.telephony import (
    AttemptIn,
    AttemptOut,
    AttemptOutcomeIn,
    CallerIdOut,
    CarrierUpdateIn,
    ComplianceCheckIn,
    ComplianceCheckOut,
    ConsentIn,
    CreatedOut,
    HealthChange,
    HealthRunOut,
    OptOutIn,
    ReasonOut,
    ResolveOut,
)
from mitra_core.telephony import service
from mitra_core.telephony.compliance import evaluate
from mitra_core.telephony.dnd import DndProvider, get_dnd_provider
from mitra_core.telephony.enums import KycStatus
from mitra_core.tenancy import TenantContext, set_tenant

router = APIRouter(
    prefix="/internal/v1/telephony",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)


async def _bind(session: AsyncSession, business_id: uuid.UUID) -> Business:
    await set_tenant(session, TenantContext(business_id=business_id))
    business = await session.get(Business, business_id)
    if business is None:
        raise not_found("Business")
    return business


@router.get("/resolve", response_model=ResolveOut)
async def resolve_number(
    to: E164Phone = Query(description="The number the caller dialled"),
    from_: E164Phone | None = Query(default=None, alias="from"),
    session: AsyncSession = Depends(get_session),
) -> ResolveOut:
    business_id = await service.business_for_number(session, to)
    if business_id is None:
        raise not_found("Phone number")
    business = await _bind(session, business_id)
    number = await session.scalar(
        select(PhoneNumber).where(PhoneNumber.business_id == business_id, PhoneNumber.e164 == to)
    )
    if number is None:
        raise not_found("Phone number")
    employee = await service.answering_employee(session, business_id, number)
    if employee is None:
        raise AppError(409, "no_employee", "This business has no employee to answer calls")
    known = False
    if from_:
        known = await service.note_inbound_relationship(session, business_id, from_)
        await session.commit()
    return ResolveOut(
        business_id=business_id,
        business_name=business.name,
        employee_id=employee.id,
        phone_number_id=number.id,
        caller_known=known,
    )


@router.post("/compliance/check", response_model=ComplianceCheckOut)
async def compliance_check(
    body: ComplianceCheckIn,
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    dnd: DndProvider = Depends(get_dnd_provider),
    session: AsyncSession = Depends(get_session),
) -> ComplianceCheckOut:
    business = await _bind(session, body.business_id)
    now = body.at or clock()
    facts = await service.load_facts(
        session,
        business=business,
        phone_e164=body.contact_phone,
        purpose=body.purpose,
        now=now,
        settings=settings,
        dnd=dnd,
        number_id=body.number_id,
        called_number_id=body.called_number_id,
        dlt_template_id=body.dlt_template_id,
        timezone=body.timezone,
    )
    result = evaluate(facts)
    row = service.log_decision(
        session,
        business_id=business.id,
        phone_e164=body.contact_phone,
        purpose=body.purpose,
        result=result,
        now=now,
    )
    await session.commit()
    caller = result.caller
    return ComplianceCheckOut(
        decision=result.decision,
        allowed=result.allowed,
        reasons=[ReasonOut(code=r.code, message=r.message) for r in result.reasons],
        caller_id=(
            CallerIdOut(phone_number_id=caller.id, e164=caller.e164, type=caller.type)
            if caller and caller.e164
            else None
        ),
        defer_until=result.defer_until,
        decision_id=row.id,
    )


@router.post("/attempts", status_code=status.HTTP_201_CREATED, response_model=AttemptOut)
async def record_attempt(
    body: AttemptIn,
    clock: Clock = Depends(get_clock),
    session: AsyncSession = Depends(get_session),
) -> AttemptOut:
    await _bind(session, body.business_id)
    if body.phone_number_id is not None:
        owned = await session.scalar(
            select(PhoneNumber.id).where(
                PhoneNumber.id == body.phone_number_id,
                PhoneNumber.business_id == body.business_id,
            )
        )
        if owned is None:
            raise not_found("Phone number")
    attempt = OutboundAttempt(
        business_id=body.business_id,
        phone_hash=hash_phone(body.contact_phone),
        phone_number_id=body.phone_number_id,
        purpose=body.purpose,
        outcome=body.outcome,
        carrier_call_sid=body.carrier_call_sid,
        attempted_at=body.attempted_at or clock(),
    )
    session.add(attempt)
    await session.flush()
    out = AttemptOut(id=attempt.id, outcome=attempt.outcome, attempted_at=attempt.attempted_at)
    await session.commit()
    return out


@router.patch("/attempts/{attempt_id}", response_model=AttemptOut)
async def set_attempt_outcome(
    attempt_id: uuid.UUID, body: AttemptOutcomeIn, session: AsyncSession = Depends(get_session)
) -> AttemptOut:
    await _bind(session, body.business_id)
    attempt = await session.scalar(
        select(OutboundAttempt).where(
            OutboundAttempt.id == attempt_id, OutboundAttempt.business_id == body.business_id
        )
    )
    if attempt is None:
        raise not_found("Attempt")
    attempt.outcome = body.outcome
    out = AttemptOut(id=attempt.id, outcome=body.outcome, attempted_at=attempt.attempted_at)
    await session.commit()
    return out


@router.post("/opt-outs", status_code=status.HTTP_201_CREATED, response_model=CreatedOut)
async def add_opt_out(body: OptOutIn, session: AsyncSession = Depends(get_session)) -> CreatedOut:
    """Idempotent: opting out twice for the same purpose returns the existing row."""
    await _bind(session, body.business_id)
    phone_hash = hash_phone(body.contact_phone)
    purpose_match = (
        OptOut.purpose.is_(None) if body.purpose is None else OptOut.purpose == body.purpose
    )
    existing = await session.scalar(
        select(OptOut.id).where(
            OptOut.business_id == body.business_id, OptOut.phone_hash == phone_hash, purpose_match
        )
    )
    if existing is not None:
        return CreatedOut(id=existing)
    row = OptOut(
        business_id=body.business_id,
        phone_hash=phone_hash,
        purpose=body.purpose,
        source=body.source,
    )
    session.add(row)
    await session.flush()
    out = CreatedOut(id=row.id)
    await session.commit()
    return out


@router.post("/consents", status_code=status.HTTP_201_CREATED, response_model=CreatedOut)
async def add_consent(body: ConsentIn, session: AsyncSession = Depends(get_session)) -> CreatedOut:
    await _bind(session, body.business_id)
    row = ConsentRecord(
        business_id=body.business_id,
        phone_hash=hash_phone(body.contact_phone),
        scope=body.scope,
        source=body.source,
        note=body.note,
    )
    session.add(row)
    await session.flush()
    out = CreatedOut(id=row.id)
    await session.commit()
    return out


@router.patch("/numbers/{number_id}", response_model=CreatedOut)
async def update_number(
    number_id: uuid.UUID, body: CarrierUpdateIn, session: AsyncSession = Depends(get_session)
) -> CreatedOut:
    await _bind(session, body.business_id)
    number = await session.scalar(
        select(PhoneNumber).where(
            PhoneNumber.id == number_id, PhoneNumber.business_id == body.business_id
        )
    )
    if number is None:
        raise not_found("Phone number")
    changes = body.model_dump(exclude_unset=True, exclude={"business_id"})
    if changes.get("kyc_status") == KycStatus.APPROVED and not (changes.get("e164") or number.e164):
        raise AppError(422, "number_required", "An approved number needs its e164")
    for field, value in changes.items():
        setattr(number, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:  # the e164 already belongs to another number
        raise AppError(409, "number_taken", "That number is already registered") from exc
    return CreatedOut(id=number.id)


@router.post("/health/run", response_model=HealthRunOut)
async def run_health(
    clock: Clock = Depends(get_clock), session: AsyncSession = Depends(get_session)
) -> HealthRunOut:
    now = clock()
    checked, changes = 0, []
    for business_id in await service.numbered_businesses(session):
        changed = await service.run_health_for_business(session, business_id, now)
        checked += 1
        changes += [
            HealthChange(
                phone_number_id=n.id,
                business_id=business_id,
                previous=previous,
                health=n.health,
                answer_rate_7d=n.answer_rate_7d,
            )
            for n, previous in changed
        ]
        await session.commit()  # one transaction per tenant
    # TODO(alerts): WhatsApp the owner when a number moves to Watch or Paused (NUM-08).
    return HealthRunOut(checked=checked, changes=changes)
