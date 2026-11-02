"""Customers: list, profile + memory + timeline, memory edits, DPDP erasure (MEM-01..05)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.labels import VISIBLE_ACTIONS, action_label
from mitra_core.calls.queries import escape_like
from mitra_core.errors import not_found
from mitra_core.logging import get_logger
from mitra_core.models import Call, CallAction, Commitment, Contact, MemoryFact
from mitra_core.models.enums import CallResult, CommitmentStatus, MemberRole, MemoryStatus
from mitra_core.schemas.customer import (
    CommitmentOut,
    CustomerDetail,
    CustomerList,
    CustomerRow,
    ForgetOut,
    MemoryFactOut,
    MemoryFactUpdate,
    Tag,
    TimelineEvent,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role

router = APIRouter(prefix="/customers", tags=["customers"])
log = get_logger(__name__)

_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)
_RESULT_TAGS: dict[CallResult, Tag] = {
    CallResult.INTERESTED: "hot_lead",
    CallResult.BOOKED: "booked",
    CallResult.CALL_BACK: "call_back",
}
_RESULT_TITLES = {
    CallResult.BOOKED: "Call · Booked",
    CallResult.INTERESTED: "Call · Interested",
    CallResult.CALL_BACK: "Call · Call back",
    CallResult.TRANSFERRED: "Call · Transferred",
    CallResult.NOT_INTERESTED: "Call · Not interested",
    CallResult.INFO_ONLY: "Call · Answered",
    CallResult.MISSED: "Missed call",
}


async def _rows(session: AsyncSession, contacts: list[Contact]) -> list[CustomerRow]:
    """Attach call aggregates, last result, next step and tags to a page of contacts."""
    ids = [c.id for c in contacts]
    if not ids:
        return []
    stats: dict[uuid.UUID, tuple[int, Any]] = {
        cid: (n, last)
        for cid, n, last in await session.execute(
            select(Call.contact_id, func.count(), func.max(Call.started_at))
            .where(Call.contact_id.in_(ids))
            .group_by(Call.contact_id)
        )
        if cid is not None
    }
    latest = (
        select(Call.contact_id, Call.result)
        .where(Call.contact_id.in_(ids), Call.result.is_not(None))
        .ext(distinct_on(Call.contact_id))
        .order_by(Call.contact_id, Call.started_at.desc())
    )
    last_result = dict((await session.execute(latest)).all())
    nxt = (
        select(Commitment.contact_id, Commitment.description)
        .where(Commitment.contact_id.in_(ids), Commitment.status == CommitmentStatus.OPEN)
        .ext(distinct_on(Commitment.contact_id))
        .order_by(Commitment.contact_id, Commitment.due_at.asc().nulls_last())
    )
    next_step = dict((await session.execute(nxt)).all())
    opted = set(
        await session.scalars(
            select(Call.contact_id)
            .join(CallAction, CallAction.call_id == Call.id)
            .where(Call.contact_id.in_(ids), CallAction.name == "opt_out", CallAction.ok)
        )
    )
    vip = set(
        await session.scalars(
            select(MemoryFact.contact_id).where(
                MemoryFact.contact_id.in_(ids), MemoryFact.key == "vip"
            )
        )
    )
    out = []
    for c in contacts:
        n, last = stats.get(c.id, (0, None))
        result = last_result.get(c.id)
        tags: list[Tag] = []
        if result in _RESULT_TAGS:
            tags.append(_RESULT_TAGS[result])
        if c.id in vip:
            tags.append("vip")
        if c.id in opted:
            tags.append("opted_out")
        out.append(
            CustomerRow(
                id=c.id,
                name=c.name,
                phone_last4=c.phone_last4,
                language=c.language,
                tags=tags,
                calls=n,
                last_contact_at=last,
                last_result=result,
                next_step=next_step.get(c.id),
            )
        )
    return out


@router.get("", response_model=CustomerList, summary="List customers")
async def list_customers(
    q: str | None = Query(None, min_length=1, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> CustomerList:
    last_call = (
        select(func.max(Call.started_at))
        .where(Call.contact_id == Contact.id)
        .correlate(Contact)
        .scalar_subquery()
    )
    stmt = select(Contact).where(Contact.business_id == tenant.business_id)
    if q and q.strip():
        pattern = f"%{escape_like(q.strip().lower())}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(Contact.name, "")).like(pattern, escape="\\"),
                Contact.phone_last4.like(pattern, escape="\\"),
            )
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    contacts = list(
        await session.scalars(
            stmt.order_by(last_call.desc().nulls_last(), Contact.created_at.desc(), Contact.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return CustomerList(items=await _rows(session, contacts), total=total)


async def _get_contact(session: AsyncSession, tenant: Tenant, contact_id: uuid.UUID) -> Contact:
    contact = await session.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.business_id == tenant.business_id)
    )
    if contact is None:
        raise not_found("Customer")
    return contact


@router.get("/{contact_id}", response_model=CustomerDetail, summary="Profile, memory, timeline")
async def get_customer(
    contact_id: uuid.UUID,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> CustomerDetail:
    contact = await _get_contact(session, tenant, contact_id)
    (row,) = await _rows(session, [contact])
    memory = await session.scalars(
        select(MemoryFact)
        .where(MemoryFact.contact_id == contact.id)
        .order_by(MemoryFact.status, MemoryFact.updated_at.desc())
    )
    commitments = list(
        await session.scalars(
            select(Commitment)
            .where(Commitment.contact_id == contact.id)
            .order_by(Commitment.created_at.desc())
        )
    )
    calls = list(
        await session.scalars(
            select(Call)
            .where(Call.contact_id == contact.id)
            .order_by(Call.started_at.desc())
            .limit(100)
        )
    )
    actions = await session.scalars(
        select(CallAction)
        .where(CallAction.call_id.in_([c.id for c in calls]))
        .where(CallAction.name.in_(VISIBLE_ACTIONS - {"record_field"}))
    )
    events = [
        TimelineEvent(
            kind="call",
            at=c.started_at,
            title=_RESULT_TITLES.get(c.result, "Call") if c.result else "Call",
            detail=c.summary,
            call_id=c.id,
            result=c.result,
        )
        for c in calls
    ]
    events += [
        TimelineEvent(
            kind="action",
            at=a.created_at,
            title=action_label(a.name, a.args, a.result),
            call_id=a.call_id,
        )
        for a in actions
    ]
    events += [
        TimelineEvent(
            kind="commitment",
            at=m.created_at,
            title=m.description,
            detail=m.status.value,
            call_id=m.call_id,
        )
        for m in commitments
    ]
    events.sort(key=lambda e: (e.at, {"call": 0, "action": 1, "commitment": 2}[e.kind]))
    events.reverse()
    return CustomerDetail(
        **row.model_dump(),
        created_at=contact.created_at,
        memory=[MemoryFactOut.model_validate(m) for m in memory],
        commitments=[CommitmentOut.model_validate(m) for m in commitments],
        timeline=events,
    )


async def _get_fact(
    session: AsyncSession, tenant: Tenant, contact_id: uuid.UUID, fact_id: uuid.UUID
) -> MemoryFact:
    fact = await session.scalar(
        select(MemoryFact).where(
            MemoryFact.id == fact_id,
            MemoryFact.contact_id == contact_id,
            MemoryFact.business_id == tenant.business_id,
        )
    )
    if fact is None:
        raise not_found("Memory")
    return fact


@router.patch(
    "/{contact_id}/memory/{fact_id}", response_model=MemoryFactOut, summary="Correct a memory"
)
async def update_memory(
    contact_id: uuid.UUID,
    fact_id: uuid.UUID,
    body: MemoryFactUpdate,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> MemoryFact:
    fact = await _get_fact(session, tenant, contact_id, fact_id)
    if body.value is not None:
        fact.value = body.value
        fact.status = MemoryStatus.CONFIRMED  # the owner vouches for an edited value
    if body.status is not None:
        fact.status = body.status
    if fact.status == MemoryStatus.CONFIRMED:
        fact.confidence, fact.expires_at = 1.0, None
    await session.flush()
    await session.commit()
    return fact


@router.delete(
    "/{contact_id}/memory/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a memory",
)
async def delete_memory(
    contact_id: uuid.UUID,
    fact_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    fact = await _get_fact(session, tenant, contact_id, fact_id)
    await session.delete(fact)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{contact_id}/forget",
    response_model=ForgetOut,
    summary="Forget this customer (DPDP erasure: calls, transcripts, memory, promises)",
)
async def forget_customer(
    contact_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> ForgetOut:
    # Naturally idempotent: a repeat answers 404 and nothing is left to erase.
    contact = await _get_contact(session, tenant, contact_id)
    calls = await session.scalar(select(func.count()).where(Call.contact_id == contact.id)) or 0
    memory = (
        await session.scalar(select(func.count()).where(MemoryFact.contact_id == contact.id)) or 0
    )
    # ON DELETE CASCADE removes calls (with transcripts and actions), summaries, memory and
    # commitments. TODO(dpdp): delete recording objects in S3 once recordings are uploaded, keep
    # an opt-out suppression hash if the customer opted out, and write an audit_log entry.
    await session.delete(contact)
    await session.commit()
    log.info("customer.forgotten", business_id=str(tenant.business_id), calls=calls)
    return ForgetOut(id=contact_id, calls_deleted=calls, memory_deleted=memory)
