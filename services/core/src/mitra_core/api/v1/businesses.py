from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import idempotency
from mitra_core.errors import not_found
from mitra_core.models import AppUser, Business, Membership
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.business import (
    BusinessCreate,
    BusinessCreated,
    BusinessOut,
    BusinessUpdate,
    MembershipOut,
)
from mitra_core.security import (
    Tenant,
    current_user,
    get_tenant_session,
    require_business,
    require_role,
)
from mitra_core.tenancy import TenantContext, set_tenant

router = APIRouter(prefix="/businesses", tags=["businesses"])

_CREATE_ENDPOINT = "POST /v1/businesses"


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=BusinessCreated,
    summary="Create a business; the caller becomes its owner",
)
async def create_business(
    request: Request,
    body: BusinessCreate,
    idempotency_key: idempotency.IdempotencyKey = None,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(get_tenant_session),
) -> BusinessCreated | JSONResponse:
    """The ONE bootstrap path into a new tenant.

    RLS only allows writes where ``business_id = app.business_id``, and a brand-new business has
    no id yet. So we reserve an id from Postgres, switch this transaction's tenant context to
    it, and insert the business and the owner membership in the same transaction. The caller's
    token is not scoped to the new business; the client must obtain a new token for it.
    """
    payload = body.model_dump(mode="json")
    req_hash = idempotency.request_hash(payload)
    if idempotency_key:
        await idempotency.lock_key(session, f"user:{user.id}:{_CREATE_ENDPOINT}", idempotency_key)
        record = await idempotency.find(
            session, endpoint=_CREATE_ENDPOINT, key=idempotency_key, user_id=user.id
        )
        if record is not None:
            return idempotency.replay(record, req_hash)

    business_id: uuid.UUID = (await session.execute(select(func.gen_random_uuid()))).scalar_one()
    await set_tenant(session, TenantContext(user_id=user.id, business_id=business_id))
    request.state.business_id = str(business_id)

    business = Business(id=business_id, **payload)
    session.add(business)
    await session.flush()
    session.add(Membership(business_id=business_id, user_id=user.id, role=MemberRole.OWNER))
    await session.flush()

    result = BusinessCreated(
        business=BusinessOut.model_validate(business),
        membership=MembershipOut(
            business_id=business_id, business_name=business.name, role=MemberRole.OWNER
        ),
    )
    if idempotency_key:
        idempotency.save(
            session,
            business_id=business_id,
            user_id=user.id,
            endpoint=_CREATE_ENDPOINT,
            key=idempotency_key,
            req_hash=req_hash,
            status=status.HTTP_201_CREATED,
            body=result.model_dump(mode="json"),
        )
    await session.commit()
    return result


@router.get("/current", response_model=BusinessOut, summary="The business the token is scoped to")
async def get_current_business(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> Business:
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    return business


@router.patch("/current", response_model=BusinessOut, summary="Update the current business")
async def update_current_business(
    body: BusinessUpdate,
    tenant: Tenant = Depends(require_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_tenant_session),
) -> Business:
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    for field, value in body.model_dump(mode="json", exclude_unset=True).items():
        setattr(business, field, value)
    await session.flush()
    await session.commit()
    return business
