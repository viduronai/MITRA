from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import AppUser, Business, Membership
from mitra_core.schemas.business import MembershipOut
from mitra_core.schemas.user import MeResponse, UserOut
from mitra_core.security import current_user, get_tenant_session

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeResponse, summary="Current user and their memberships")
async def get_me(
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(get_tenant_session),
) -> MeResponse:
    # RLS lets a user read their own memberships (and those businesses) across tenants.
    rows = await session.execute(
        select(Membership.business_id, Business.name, Membership.role)
        .join(Business, Business.id == Membership.business_id)
        .where(Membership.user_id == user.id)
        .order_by(Business.name)
    )
    return MeResponse(
        user=UserOut.model_validate(user),
        memberships=[
            MembershipOut(business_id=bid, business_name=name, role=role)
            for bid, name, role in rows
        ],
    )
