"""The business's people (transfer ladder CALL-19, WhatsApp briefs TEAM-04) and hand-off cards."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.errors import not_found
from mitra_core.models import HandoffCard, StaffMember
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.team import HandoffCardOut, StaffIn, StaffOut, StaffPatch
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role

router = APIRouter(prefix="/team", tags=["team"])
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)


async def _get(session: AsyncSession, tenant: Tenant, staff_id: uuid.UUID) -> StaffMember:
    staff = await session.scalar(
        select(StaffMember).where(
            StaffMember.id == staff_id, StaffMember.business_id == tenant.business_id
        )
    )
    if staff is None:
        raise not_found("Staff member")
    return staff


@router.get("/staff", response_model=list[StaffOut], summary="Staff and the transfer order")
async def list_staff(
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[StaffMember]:
    rows = await session.scalars(
        select(StaffMember)
        .where(StaffMember.business_id == tenant.business_id)
        .order_by(StaffMember.ladder_position.nulls_last(), StaffMember.created_at)
    )
    return list(rows)


@router.post(
    "/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED, summary="Add staff"
)
async def add_staff(
    body: StaffIn,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> StaffMember:
    staff = StaffMember(business_id=tenant.business_id, **body.model_dump())
    session.add(staff)
    await session.commit()
    return staff


@router.patch("/staff/{staff_id}", response_model=StaffOut, summary="Change a staff member")
async def update_staff(
    staff_id: uuid.UUID,
    body: StaffPatch,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> StaffMember:
    staff = await _get(session, tenant, staff_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(staff, key, value)
    await session.commit()
    return staff


@router.delete("/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove staff")
async def delete_staff(
    staff_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    await session.delete(await _get(session, tenant, staff_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/handoff-cards",
    response_model=list[HandoffCardOut],
    summary="Messages taken when nobody could pick up a transfer",
)
async def list_cards(
    status_: str | None = Query("open", alias="status", pattern="^(open|done)$"),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[HandoffCard]:
    query = (
        select(HandoffCard)
        .where(HandoffCard.business_id == tenant.business_id)
        .order_by(HandoffCard.created_at.desc())
        .limit(100)
    )
    if status_:
        query = query.where(HandoffCard.status == status_)
    return list(await session.scalars(query))


@router.post(
    "/handoff-cards/{card_id}/done", response_model=HandoffCardOut, summary="Mark as called back"
)
async def resolve_card(
    card_id: uuid.UUID,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> HandoffCard:
    card = await session.scalar(
        select(HandoffCard).where(
            HandoffCard.id == card_id, HandoffCard.business_id == tenant.business_id
        )
    )
    if card is None:
        raise not_found("Hand-off card")
    if card.status != "done":
        card.status, card.resolved_at, card.resolved_by = "done", clock(), tenant.user.id
        await session.commit()
    return card
