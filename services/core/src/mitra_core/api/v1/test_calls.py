"""Test calls (contract §5). SIMULATED until the voice pipeline exists: nothing is dialled;
status advances with the call's age and every response carries ``simulated: true``."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import idempotency, simulation
from mitra_core.clock import Clock, get_clock
from mitra_core.errors import AppError, not_found
from mitra_core.knowledge.extract import guess_category
from mitra_core.models import Business, Employee, Fact, TestCall
from mitra_core.models.enums import FactStatus, MemberRole, TestCallStatus
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.schemas.test_call import (
    CorrectionIn,
    CorrectionOut,
    TestCallCreated,
    TestCallIn,
    TestCallOut,
    TranscriptLine,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role

router = APIRouter(prefix="/test-calls", tags=["test calls"])

_CREATE_ENDPOINT = "POST /v1/test-calls"
_CORRECTION_ENDPOINT = "POST /v1/test-calls/{id}/corrections"
_MAX_BEHAVIOUR_ITEMS = 20
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)


async def _get_employee(session: AsyncSession, tenant: Tenant, employee_id: uuid.UUID) -> Employee:
    employee = await session.scalar(
        select(Employee).where(
            Employee.id == employee_id, Employee.business_id == tenant.business_id
        )
    )
    if employee is None:
        raise not_found("Employee")
    return employee


async def _get_call(session: AsyncSession, tenant: Tenant, call_id: uuid.UUID) -> TestCall:
    call = await session.scalar(
        select(TestCall).where(TestCall.id == call_id, TestCall.business_id == tenant.business_id)
    )
    if call is None:
        raise not_found("Test call")
    return call


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TestCallCreated,
    summary="Start a (simulated) test call from an employee to the owner's phone",
)
async def create_test_call(
    body: TestCallIn,
    idempotency_key: idempotency.IdempotencyKey = None,
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> TestCallCreated | JSONResponse:
    payload = body.model_dump(mode="json")
    req_hash, replayed = await idempotency.lookup_for_business(
        session,
        business_id=tenant.business_id,
        endpoint=_CREATE_ENDPOINT,
        key=idempotency_key,
        payload=payload,
    )
    if replayed is not None:
        return replayed

    employee = await _get_employee(session, tenant, body.employee_id)
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    facts = await session.execute(
        select(Fact.category, Fact.key, Fact.value)
        .where(Fact.business_id == tenant.business_id, Fact.status == FactStatus.CONFIRMED)
        .order_by(Fact.updated_at.desc(), Fact.id)
    )
    script = simulation.build_transcript(
        business_name=business.name,
        industry=business.industry,
        employee_name=employee.name,
        greeting=employee.greeting,
        ask_for=list(employee.behaviour.get("ask_for", [])),
        facts=[(c, k, v) for c, k, v in facts],
    )
    phone = body.phone or tenant.user.phone_e164
    call = TestCall(
        business_id=tenant.business_id,
        employee_id=employee.id,
        created_by=tenant.user.id,
        phone_hash=hash_phone(phone),
        phone_last4=phone_last4(phone),
        transcript=script.transcript,
        summary=script.summary,
        corrections=[],
        created_at=clock(),
    )
    session.add(call)
    await session.flush()
    result = TestCallCreated(id=call.id, status=simulation.status_at(call.created_at, clock()))
    if idempotency_key:
        idempotency.save(
            session,
            business_id=tenant.business_id,
            user_id=tenant.user.id,
            endpoint=_CREATE_ENDPOINT,
            key=idempotency_key,
            req_hash=req_hash,
            status=status.HTTP_201_CREATED,
            body=result.model_dump(mode="json"),
        )
    await session.commit()
    return result


@router.get("/{call_id}", response_model=TestCallOut, summary="Poll a test call")
async def get_test_call(
    call_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> TestCallOut:
    call = await _get_call(session, tenant, call_id)
    state = simulation.status_at(call.created_at, clock())
    return TestCallOut(
        id=call.id,
        status=state,
        employee_id=call.employee_id,
        phone_last4=call.phone_last4,
        created_at=call.created_at,
        transcript=[
            TranscriptLine.model_validate(line)
            for line in simulation.visible_transcript(call.transcript, state)
        ],
        summary=call.summary if state == TestCallStatus.COMPLETED else None,
    )


@router.post(
    "/{call_id}/corrections",
    status_code=status.HTTP_201_CREATED,
    response_model=CorrectionOut,
    summary="Correct the employee after a test call (to knowledge or behaviour)",
)
async def create_correction(
    call_id: uuid.UUID,
    body: CorrectionIn,
    idempotency_key: idempotency.IdempotencyKey = None,
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> CorrectionOut | JSONResponse:
    payload = body.model_dump(mode="json") | {"call_id": str(call_id)}
    req_hash, replayed = await idempotency.lookup_for_business(
        session,
        business_id=tenant.business_id,
        endpoint=_CORRECTION_ENDPOINT,
        key=idempotency_key,
        payload=payload,
    )
    if replayed is not None:
        return replayed

    call = await _get_call(session, tenant, call_id)
    employee = await _get_employee(session, tenant, call.employee_id)
    if simulation.applies_to_knowledge(body.text):
        result = await _correct_knowledge(session, tenant, employee, body.text)
    else:
        result = _correct_behaviour(employee, body.text)
    call.corrections = [
        *call.corrections,
        result.model_dump(mode="json") | {"text": body.text, "at": clock().isoformat()},
    ]
    await session.flush()
    if idempotency_key:
        idempotency.save(
            session,
            business_id=tenant.business_id,
            user_id=tenant.user.id,
            endpoint=_CORRECTION_ENDPOINT,
            key=idempotency_key,
            req_hash=req_hash,
            status=status.HTTP_201_CREATED,
            body=result.model_dump(mode="json"),
        )
    await session.commit()
    return result


async def _correct_knowledge(
    session: AsyncSession, tenant: Tenant, employee: Employee, text: str
) -> CorrectionOut:
    key, value = simulation.parse_fact(text)
    fact = await session.scalar(
        select(Fact)
        .where(Fact.business_id == tenant.business_id, func.lower(Fact.key) == key.lower())
        .order_by(Fact.updated_at.desc(), Fact.id)
        .limit(1)
    )
    if fact is None:
        fact = Fact(
            business_id=tenant.business_id,
            category=guess_category(key, value),
            key=key,
            value=value,
            status=FactStatus.CONFIRMED,
        )
        session.add(fact)
        summary = f"{employee.name} now knows: {key}: {value}."
    else:
        fact.value, fact.status = value, FactStatus.CONFIRMED
        summary = f"Updated {key} to {value}; {employee.name} will say this from the next call."
    await session.flush()
    return CorrectionOut(
        id=uuid.uuid4(), applied_to="knowledge", change_summary=summary, fact_id=fact.id
    )


def _correct_behaviour(employee: Employee, text: str) -> CorrectionOut:
    list_name = simulation.behaviour_list_for(text)
    behaviour: dict[str, Any] = {k: list(v) for k, v in employee.behaviour.items()}
    items: list[str] = behaviour.setdefault(list_name, [])
    note = text[:200]
    if note not in items:
        if len(items) >= _MAX_BEHAVIOUR_ITEMS:
            raise AppError(
                409,
                "behaviour_full",
                f"{employee.name}'s {list_name.replace('_', ' ')} list is full "
                f"({_MAX_BEHAVIOUR_ITEMS} items). Remove one first.",
            )
        items.append(note)
    employee.behaviour = behaviour
    label = "never say" if list_name == "never_say" else "ask for"
    return CorrectionOut(
        id=uuid.uuid4(),
        applied_to="behaviour",
        change_summary=f'Added to what {employee.name} should {label}: "{note}".',
    )
