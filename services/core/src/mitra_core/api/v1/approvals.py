"""Approvals inbox (APPR-01..06): list, detail with log, edit-before-approve, decide, rules."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import manager as _manager  # noqa: F401  (registers Manager approval handlers)
from mitra_core.approvals import RuleSpec, decide, edit_approval, expire_due, get_rules
from mitra_core.approvals.rules import upsert_rule
from mitra_core.clock import Clock, get_clock
from mitra_core.errors import AppError, not_found
from mitra_core.models import Approval, ApprovalEvent
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.manager import (
    ApprovalDecision,
    ApprovalDetail,
    ApprovalEdit,
    ApprovalEventOut,
    ApprovalList,
    ApprovalOut,
    RuleOut,
    RulesIn,
    RulesOut,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role

router = APIRouter(prefix="/approvals", tags=["approvals"])

DECIDERS = (MemberRole.OWNER, MemberRole.MANAGER)


@router.get("", response_model=ApprovalList, summary="Approvals inbox (pending first)")
async def list_approvals(
    status: Literal["pending", "decided", "all"] = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> ApprovalList:
    biz = tenant.business_id
    # Lazily apply overdue defaults so the inbox never shows a card that already timed out.
    if await expire_due(session, biz, clock()):
        await session.commit()
    stmt = select(Approval).where(Approval.business_id == biz)
    if status == "pending":
        stmt = stmt.where(Approval.status == "pending")
    elif status == "decided":
        stmt = stmt.where(Approval.status != "pending")
    rows = await session.scalars(stmt.order_by(Approval.created_at.desc()).limit(limit))
    pending = await session.scalar(
        select(func.count()).where(Approval.business_id == biz, Approval.status == "pending")
    )
    return ApprovalList(items=[ApprovalOut.model_validate(a) for a in rows], pending=pending or 0)


@router.get("/rules", response_model=RulesOut, summary='"Ask me first when…" rules (APPR-01)')
async def list_rules(
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> RulesOut:
    rules = await get_rules(session, tenant.business_id)
    return RulesOut(items=[RuleOut.model_validate(r, from_attributes=True) for r in rules.values()])


@router.put("/rules", response_model=RulesOut, summary="Change approval rules")
async def put_rules(
    body: RulesIn,
    tenant: Tenant = Depends(require_role(MemberRole.OWNER)),
    session: AsyncSession = Depends(get_tenant_session),
) -> RulesOut:
    for item in body.items:
        await upsert_rule(
            session,
            tenant.business_id,
            RuleSpec(
                item.kind, item.enabled, item.threshold, item.timeout_minutes, item.default_action
            ),
        )
    await session.commit()
    rules = await get_rules(session, tenant.business_id)
    return RulesOut(items=[RuleOut.model_validate(r, from_attributes=True) for r in rules.values()])


@router.get("/{approval_id}", response_model=ApprovalDetail, summary="One approval with its log")
async def get_approval(
    approval_id: uuid.UUID,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> ApprovalDetail:
    approval = await session.scalar(
        select(Approval).where(
            Approval.id == approval_id, Approval.business_id == tenant.business_id
        )
    )
    if approval is None:
        raise not_found("Approval")
    events = await session.scalars(
        select(ApprovalEvent)
        .where(ApprovalEvent.approval_id == approval.id)
        .order_by(ApprovalEvent.created_at, ApprovalEvent.id)
    )
    return ApprovalDetail(
        approval=ApprovalOut.model_validate(approval),
        events=[ApprovalEventOut.model_validate(e) for e in events],
    )


@router.patch("/{approval_id}", response_model=ApprovalOut, summary="Edit before approving")
async def edit(
    approval_id: uuid.UUID,
    body: ApprovalEdit,
    tenant: Tenant = Depends(require_role(*DECIDERS)),
    session: AsyncSession = Depends(get_tenant_session),
) -> ApprovalOut:
    approval = await edit_approval(
        session,
        tenant.business_id,
        approval_id,
        payload=body.payload,
        summary=body.summary,
        expected_version=body.version,
        actor_user_id=tenant.user.id,
    )
    await session.commit()
    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/decide", response_model=ApprovalOut, summary="Approve or decline")
async def decide_approval(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    tenant: Tenant = Depends(require_role(*DECIDERS)),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> ApprovalOut:
    try:
        approval = await decide(
            session,
            tenant.business_id,
            approval_id,
            action=body.action,
            version=body.version,
            actor_user_id=tenant.user.id,
            via="app",
            note=body.note,
            now=clock(),
        )
    except AppError as exc:
        if exc.status_code == 409:
            await session.commit()  # keep the rejected attempt (and any timeout) in the log
        raise
    await session.commit()
    return ApprovalOut.model_validate(approval)
