from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import idempotency
from mitra_core.catalog import VOICES_BY_ID
from mitra_core.errors import AppError, not_found
from mitra_core.models import Employee
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.employee import EmployeeCreate, EmployeeList, EmployeeOut, EmployeeUpdate
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role

router = APIRouter(prefix="/employees", tags=["employees"])

_CREATE_ENDPOINT = "POST /v1/employees"
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)

# Queries filter by business_id explicitly AND are constrained by RLS (defence in depth).


async def _get_employee(session: AsyncSession, tenant: Tenant, employee_id: uuid.UUID) -> Employee:
    employee = await session.scalar(
        select(Employee).where(
            Employee.id == employee_id, Employee.business_id == tenant.business_id
        )
    )
    if employee is None:
        raise not_found("Employee")
    return employee


@router.get("", response_model=EmployeeList, summary="List AI employees")
async def list_employees(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeList:
    employees = await session.scalars(
        select(Employee)
        .where(Employee.business_id == tenant.business_id)
        .order_by(Employee.created_at, Employee.id)
        .limit(limit)
        .offset(offset)
    )
    return EmployeeList(items=[EmployeeOut.model_validate(e) for e in employees])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=EmployeeOut,
    summary="Hire (create) an AI employee",
)
async def create_employee(
    body: EmployeeCreate,
    idempotency_key: idempotency.IdempotencyKey = None,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeOut | JSONResponse:
    payload = body.model_dump(mode="json")
    req_hash = idempotency.request_hash(payload)
    if idempotency_key:
        await idempotency.lock_key(
            session, f"business:{tenant.business_id}:{_CREATE_ENDPOINT}", idempotency_key
        )
        record = await idempotency.find(
            session, endpoint=_CREATE_ENDPOINT, key=idempotency_key, business_id=tenant.business_id
        )
        if record is not None:
            return idempotency.replay(record, req_hash)

    employee = Employee(business_id=tenant.business_id, **payload)
    session.add(employee)
    await session.flush()
    result = EmployeeOut.model_validate(employee)
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


@router.get("/{employee_id}", response_model=EmployeeOut, summary="Get an AI employee")
async def get_employee(
    employee_id: uuid.UUID,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> Employee:
    return await _get_employee(session, tenant, employee_id)


@router.patch(
    "/{employee_id}",
    response_model=EmployeeOut,
    summary="Update an AI employee (rename, pause/resume, voice, greeting, behaviour, ...)",
)
async def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Employee:
    employee = await _get_employee(session, tenant, employee_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    if changes.get("voice_id"):
        tier = VOICES_BY_ID[changes["voice_id"]].tier
        if changes.get("voice_tier", tier) != tier:
            raise AppError(
                422,
                "voice_tier_mismatch",
                "voice_tier must match the chosen voice's tier (or be omitted)",
                details={"voice_id": changes["voice_id"], "tier": tier},
            )
        changes["voice_tier"] = tier
    for field, value in changes.items():
        setattr(employee, field, value)
    await session.flush()
    await session.commit()
    return employee
