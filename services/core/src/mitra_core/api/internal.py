"""Internal service-to-service API (``/internal/v1``), e.g. for the voice service.

Auth: ``Authorization: Bearer <MITRA_SERVICE_TOKEN>``, compared in constant time. This is a
separate credential from user JWTs (a user token is never accepted here, nor this token on the
public API). Unset outside env=local => the internal API answers 503 (disabled).

Tenancy: the caller only knows an employee id. The SECURITY DEFINER function
``internal_employee_business`` (migration 0003) maps it to its business id and nothing else; the
request then binds that business as the RLS tenant and reads everything through the normal
policies, so a bug in a query below still cannot cross tenants.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.catalog import VOICES_BY_ID
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError, not_found
from mitra_core.models import Business, Employee, Fact
from mitra_core.models.enums import FactStatus
from mitra_core.schemas.pack import EmployeePackOut, PackBehaviour, PackFact
from mitra_core.simulation import opening_line
from mitra_core.tenancy import TenantContext, set_tenant

_bearer = HTTPBearer(auto_error=False, description="Service token")
_LOOKUP = text("SELECT internal_employee_business(:id)")
# The voice service validates greeting <= 300 chars.
MAX_GREETING = 300


async def require_service(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.effective_service_token
    if expected is None:
        raise AppError(503, "internal_api_disabled", "Internal API is not configured")
    supplied = credentials.credentials if credentials else ""
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise AppError(
            401, "unauthenticated", "Invalid service token", headers={"WWW-Authenticate": "Bearer"}
        )


router = APIRouter(
    prefix="/internal/v1",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)


@router.get("/employees/{employee_id}/pack", response_model=EmployeePackOut)
async def get_employee_pack(
    employee_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> EmployeePackOut:
    business_id = (await session.execute(_LOOKUP, {"id": employee_id})).scalar_one_or_none()
    if business_id is None:
        raise not_found("Employee")
    await set_tenant(session, TenantContext(business_id=business_id))

    employee = await session.scalar(
        select(Employee).where(Employee.id == employee_id, Employee.business_id == business_id)
    )
    business = await session.get(Business, business_id)
    if employee is None or business is None:
        raise not_found("Employee")
    facts = await session.scalars(
        select(Fact)
        .where(Fact.business_id == business_id, Fact.status == FactStatus.CONFIRMED)
        .order_by(Fact.category, Fact.created_at, Fact.id)
    )

    greeting = opening_line(business.name, employee.name, employee.greeting)
    if len(greeting) > MAX_GREETING:
        # Never drop the disclosure: fall back to the standard opening instead.
        greeting = opening_line(business.name, employee.name, None)
    voice = VOICES_BY_ID.get(employee.voice_id or "")
    body = {
        "business_id": business.id,
        "business_name": business.name,
        "industry": business.industry,
        "city": business.city,
        "business_languages": business.languages,
        "employee_id": employee.id,
        "employee_name": employee.name,
        "role_template": employee.role_template,
        "languages": employee.languages,
        "voice_id": employee.voice_id,
        "voice_tier": employee.voice_tier,
        "voice_gender": voice.gender if voice else "female",
        "greeting": greeting,
        "behaviour": PackBehaviour.model_validate(employee.behaviour),
        "working_hours": employee.working_hours,
        "facts": [PackFact.model_validate(f) for f in facts],
    }
    pack = EmployeePackOut.model_validate(body | {"knowledge_version": ""})
    digest = hashlib.sha256(
        json.dumps(pack.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    return pack.model_copy(update={"knowledge_version": digest[:16]})
