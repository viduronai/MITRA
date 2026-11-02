"""Hand-offs between interactions (WORKFLOWS section 5, TEAM-02/04/05, ACT-07).

When a call has been analysed, the deterministic rule engine picks every enabled rule for the
call's employee and result, and each match becomes a :class:`FollowUpTask` for the next
employee (or a WhatsApp brief for human staff) carrying the context packet built from shared
customer memory. One live call = one employee; employees never talk to each other in a call.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.logging import get_logger
from mitra_core.models import (
    Call,
    CallAction,
    Commitment,
    Contact,
    Employee,
    FollowUpTask,
    HandoffRule,
    MemoryFact,
    StaffMember,
)
from mitra_core.models.enums import CommitmentStatus, MemoryStatus
from mitra_core.team.dispatch import dispatch_task
from mitra_core.team.templates import BEFORE_APPOINTMENT_MIN

log = get_logger(__name__)
MAX_PACKET_FACTS = 15


def rule_matches(rule: HandoffRule, result: str | None, fields: dict[str, Any]) -> bool:
    """Pure check of one rule against a call's result and collected fields."""
    if not rule.enabled or result is None or rule.when_result != result:
        return False
    cond = rule.condition or {}
    name = cond.get("field")
    if not name:
        return True
    value = str(fields.get(name) or "").strip().lower()
    op = cond.get("op", "present")
    expected = str(cond.get("value") or "").strip().lower()
    if op == "present":
        return bool(value)
    if op == "equals":
        return value == expected
    if op == "contains":
        return bool(expected) and expected in value
    return False


async def context_packet(
    session: AsyncSession, contact: Contact | None, call: Call | None
) -> dict[str, Any]:
    """What the next employee needs: who, what happened, what we promised, what not to do."""
    packet: dict[str, Any] = {}
    if call is not None:
        packet |= {
            "call_id": str(call.id),
            "summary": call.summary or "",
            "result": call.result.value if call.result else None,
            "fields": {k: str(v)[:200] for k, v in (call.fields or {}).items()},
            "open_questions": list(call.unknown_questions or [])[:5],
        }
    if contact is None:
        return packet
    facts = await session.scalars(
        select(MemoryFact)
        .where(MemoryFact.contact_id == contact.id)
        .order_by(MemoryFact.updated_at.desc())
        .limit(MAX_PACKET_FACTS)
    )
    promises = await session.scalars(
        select(Commitment.description)
        .where(Commitment.contact_id == contact.id, Commitment.status == CommitmentStatus.OPEN)
        .order_by(Commitment.due_at.nulls_last())
        .limit(5)
    )
    facts_list = list(facts)
    memory = [
        {"key": f.key, "value": f.value, "confirmed": f.status == MemoryStatus.CONFIRMED}
        for f in facts_list
    ]
    return packet | {
        "contact_id": str(contact.id),
        "name": contact.name,
        "phone_last4": contact.phone_last4,
        "language": contact.language.value if contact.language else None,
        "memory": memory,
        "promises": list(promises),
        "do_not": [f.value for f in facts_list if f.key.startswith("do_not")],
    }


async def _appointment_at(session: AsyncSession, call: Call) -> datetime | None:
    return await session.scalar(
        select(Commitment.due_at)
        .where(Commitment.call_id == call.id, Commitment.kind == "appointment")
        .where(Commitment.due_at.is_not(None))
        .order_by(Commitment.due_at)
        .limit(1)
    )


async def _callback_at(session: AsyncSession, call: Call) -> datetime | None:
    return await session.scalar(
        select(Commitment.due_at)
        .where(Commitment.call_id == call.id, Commitment.kind == "callback")
        .order_by(Commitment.due_at.nulls_last())
        .limit(1)
    )


async def due_for(session: AsyncSession, rule: HandoffRule, call: Call, now: datetime) -> datetime:
    """Delay after the call, or (reminders / briefs) a fixed time before the appointment."""
    if rule.task in BEFORE_APPOINTMENT_MIN:
        at = await _appointment_at(session, call)
        if at is not None:
            return max(now, at - timedelta(minutes=BEFORE_APPOINTMENT_MIN[rule.task]))
    if rule.task == "call_back":
        at = await _callback_at(session, call)
        if at is not None:
            return max(now, at)
    return now + timedelta(minutes=rule.delay_minutes)


async def apply_handoffs(
    session: AsyncSession, call: Call, *, now: datetime | None = None
) -> list[FollowUpTask]:
    """Create (and dispatch) one task per matching rule. Re-runs replace pending tasks."""
    now = now or utcnow()
    if call.employee_id is None or call.result is None:
        return []
    existing = await session.scalars(
        select(FollowUpTask).where(
            FollowUpTask.source_call_id == call.id, FollowUpTask.kind == "handoff"
        )
    )
    done_rules = set()
    for task in existing:
        if task.status == "pending":
            await session.delete(task)
        else:
            done_rules.add(task.rule_id)
    rules = await session.scalars(
        select(HandoffRule)
        .where(HandoffRule.business_id == call.business_id)
        .where(HandoffRule.from_employee_id == call.employee_id)
        .order_by(HandoffRule.created_at)
    )
    contact = await session.get(Contact, call.contact_id) if call.contact_id else None
    packet: dict[str, Any] | None = None
    created: list[FollowUpTask] = []
    for rule in rules:
        if rule.id in done_rules or not rule_matches(rule, call.result.value, call.fields or {}):
            continue
        packet = packet if packet is not None else await context_packet(session, contact, call)
        task = FollowUpTask(
            business_id=call.business_id,
            contact_id=call.contact_id,
            from_employee_id=call.employee_id,
            to_employee_id=rule.to_employee_id,
            source_call_id=call.id,
            rule_id=rule.id,
            kind="handoff",
            task=rule.task,
            channel=rule.channel,
            due_at=await due_for(session, rule, call, now),
            status="pending",
            context=packet | {"rule_version": rule.version},
        )
        session.add(task)
        created.append(task)
    await session.flush()
    for task in created:
        await dispatch_task(session, task, now=now)
    return created


async def escalate_from_call(
    session: AsyncSession, call: Call, *, now: datetime | None = None
) -> list[FollowUpTask]:
    """TEAM-05: an employee's ``alert_staff`` becomes a WhatsApp to the owner/staff, with why."""
    now = now or utcnow()
    actions = await session.scalars(
        select(CallAction).where(CallAction.call_id == call.id, CallAction.name == "alert_staff")
    )
    already = await session.scalar(
        select(FollowUpTask.id).where(
            FollowUpTask.source_call_id == call.id, FollowUpTask.kind == "escalation"
        )
    )
    if already is not None:
        return []
    contact = await session.get(Contact, call.contact_id) if call.contact_id else None
    tasks = []
    for action in actions:
        reason = str(action.args.get("reason") or "needs a person")[:200]
        task = FollowUpTask(
            business_id=call.business_id,
            contact_id=call.contact_id,
            from_employee_id=call.employee_id,
            source_call_id=call.id,
            kind="escalation",
            task="brief_staff",
            channel="whatsapp",
            due_at=now,
            status="pending",
            context=await context_packet(session, contact, call)
            | {"reason": reason, "urgency": str(action.args.get("urgency") or "normal")},
        )
        session.add(task)
        tasks.append(task)
    await session.flush()
    for task in tasks:
        await dispatch_task(session, task, now=now)
    return tasks


async def owner_and_staff(session: AsyncSession, business_id: uuid.UUID) -> list[StaffMember]:
    """Who hears about escalations: the owner first, then staff on the ladder."""
    rows = await session.scalars(
        select(StaffMember)
        .where(StaffMember.business_id == business_id, StaffMember.active.is_(True))
        .order_by(StaffMember.is_owner.desc(), StaffMember.ladder_position.nulls_last())
    )
    return list(rows)


async def after_call(session: AsyncSession, call_id: uuid.UUID) -> None:
    """Post-call hook (``calls.service.process_call``): hand-offs then escalations."""
    call = await session.get(Call, call_id)
    if call is None:
        return
    employee = await session.get(Employee, call.employee_id) if call.employee_id else None
    if employee is None:
        return
    created = await apply_handoffs(session, call)
    escalated = await escalate_from_call(session, call)
    if created or escalated:
        log.info(
            "team.after_call",
            call_id=str(call.id),
            handoffs=len(created),
            escalations=len(escalated),
        )
