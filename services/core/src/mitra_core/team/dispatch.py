"""Turn a follow-up task into work: a queued call, a WhatsApp, or a staff brief.

Calls are queued at once with ``not_before = due_at`` (the dialer waits and runs compliance
right before dialling). WhatsApp tasks wait for their due time; the scheduler tick picks them
up (``scheduler.run_due``). Every outcome is written on the task, so nothing silently vanishes:
``queued`` / ``sent`` / ``no_phone`` / ``failed``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.models import Business, Contact, Employee, FollowUpTask, StaffMember
from mitra_core.team import ports
from mitra_core.team.humans import ladder

WHATSAPP_THEN_CALL_GAP = timedelta(minutes=30)
TASK_WORDS = {
    "book_visit": "book a visit",
    "remind_appointment": "remind about the appointment",
    "follow_up": "follow up",
    "collect_payment": "collect the payment",
    "feedback": "ask for feedback",
    "send_report": "send the report",
    "call_back": "call back as promised",
    "brief_staff": "brief the staff",
}


def _who(ctx: dict[str, Any]) -> str:
    if ctx.get("name"):
        return str(ctx["name"])
    return f"…{ctx['phone_last4']}" if ctx.get("phone_last4") else "A customer"


def staff_brief(task: FollowUpTask) -> str:
    """TEAM-04 / TEAM-05 text: needs, budget, concerns, promises, in one short message."""
    ctx = task.context or {}
    lines = []
    if task.kind == "escalation":
        urgent = ctx.get("urgency") in {"urgent", "emergency"}
        lines.append(
            f"{'URGENT: ' if urgent else ''}{_who(ctx)} needs a person: {ctx.get('reason')}"
        )
    else:
        lines.append(f"Brief: {_who(ctx)}")
    if ctx.get("summary"):
        lines.append(str(ctx["summary"])[:300])
    facts = [f"{m['key']}: {m['value']}" for m in ctx.get("memory", [])[:6]]
    if facts:
        lines.append("Knows: " + "; ".join(facts))
    if ctx.get("promises"):
        lines.append("Promised: " + "; ".join(ctx["promises"][:3]))
    if ctx.get("do_not"):
        lines.append("Avoid: " + "; ".join(ctx["do_not"][:3]))
    return "\n".join(lines)[:1000]


def customer_message(task: FollowUpTask, employee: Employee | None, business_name: str) -> str:
    ctx = task.context or {}
    sender = employee.name if employee else "our team"
    name = ctx.get("name") or "there"
    if task.task == "send_report":
        return f"Hi {name}, {sender} from {business_name} here. Your report is ready."
    return (
        f"Hi {name}, {sender} from {business_name} here, following up on your call. "
        "Reply here or we'll call you shortly."
    )


async def _call_variables(task: FollowUpTask) -> dict[str, str]:
    ctx = task.context or {}
    out = {"task": task.task, "goal": TASK_WORDS.get(task.task, task.task)}
    if ctx.get("name"):
        out["customer_name"] = str(ctx["name"])
    if ctx.get("summary"):
        out["previous_summary"] = str(ctx["summary"])
    if ctx.get("result"):
        out["previous_result"] = str(ctx["result"])
    return out


async def _staff_targets(session: AsyncSession, task: FollowUpTask) -> list[tuple[str, str]]:
    """(name, phone) of brief-takers; with no staff set up, the owner's own login number."""
    rows = await session.scalars(
        select(StaffMember)
        .where(StaffMember.business_id == task.business_id, StaffMember.active.is_(True))
        .where(StaffMember.receives_briefs.is_(True))
        .order_by(StaffMember.is_owner.desc(), StaffMember.created_at)
        .limit(3)
    )
    targets = [(s.name, s.phone_e164) for s in rows]
    if not targets:
        targets = [(s.name, s.phone_e164) for s in await ladder(session, task.business_id)][-1:]
    return targets


async def _escalate(session: AsyncSession, task: FollowUpTask) -> None:
    """TEAM-05 through the manager's owner alerts, so alert settings and dedupe apply.

    Urgent / emergency escalations use the manager's ``urgent`` kind with the same per-call
    dedupe key as its call alerts, so the owner gets one message, not two. Only when the
    business has no owner or manager to notify does it fall back to the transfer ladder.
    """
    urgent = (task.context or {}).get("urgency") in {"urgent", "emergency"}
    kind = "urgent" if urgent else "escalation"
    key = f"call:{task.source_call_id}" if task.source_call_id else f"task:{task.id}"
    text = staff_brief(task)
    notice = await ports.notify_owner(
        session, task.business_id, kind, text, dedupe_key=key, ref={"task_id": str(task.id)}
    )
    if notice.recipients:
        task.outcome = {
            "owners": notice.recipients,
            "message_ids": notice.message_ids,
            "text": text,
        }
        task.status = "sent"
        return
    sent = []
    for name, phone in [(s.name, s.phone_e164) for s in await ladder(session, task.business_id)][
        :3
    ]:
        ref = await ports.send_whatsapp(
            session, task.business_id, phone, text, kind="team_escalation"
        )
        sent.append({"name": name, "last4": phone[-4:], "message_id": ref})
    task.outcome = {"briefed": sent, "text": text, "fallback": "ladder"}
    task.status = "sent" if any(s["message_id"] for s in sent) else "failed"


async def _brief(session: AsyncSession, task: FollowUpTask) -> None:
    if task.kind == "escalation":
        await _escalate(session, task)
        return
    targets = await _staff_targets(session, task)
    text = staff_brief(task)
    sent = []
    for name, phone in targets:
        ref = await ports.send_whatsapp(
            session, task.business_id, phone, text, kind=f"team_{task.kind}"
        )
        sent.append({"name": name, "last4": phone[-4:], "message_id": ref})
    task.outcome = {"briefed": sent, "text": text}
    task.status = "sent" if any(s["message_id"] for s in sent) else "failed"
    if not targets:
        task.outcome["reason"] = "no_staff"


async def dispatch_task(
    session: AsyncSession, task: FollowUpTask, *, now: datetime | None = None
) -> None:
    """Act on one pending task (idempotent: only ``pending`` tasks are touched)."""
    now = now or utcnow()
    if task.status != "pending":
        return
    if task.task == "brief_staff" or task.to_employee_id is None:
        if task.due_at <= now:
            await _brief(session, task)
        return
    if task.channel == "whatsapp" and task.due_at > now:
        return  # the scheduler sends it when due
    contact = await session.get(Contact, task.contact_id) if task.contact_id else None
    phone = await ports.contact_phone(session, contact) if contact else None
    if phone is None:
        task.status = "no_phone"
        task.outcome = {"reason": "no dialable number on file for this customer"}
        return
    outcome: dict[str, Any] = {}
    if task.channel in {"whatsapp", "whatsapp_then_call"} and task.due_at <= now:
        employee = await session.get(Employee, task.to_employee_id)
        business = await session.get(Business, task.business_id)
        text = customer_message(task, employee, business.name if business else "us")
        outcome["whatsapp"] = await ports.send_whatsapp(
            session, task.business_id, phone, text, kind="team_follow_up"
        )
        if task.channel == "whatsapp":
            task.status = "sent" if outcome["whatsapp"] else "failed"
            task.outcome = outcome
            return
    elif task.channel == "whatsapp_then_call" and task.due_at > now:
        return
    not_before = task.due_at
    if task.channel == "whatsapp_then_call":
        not_before = max(now, task.due_at) + WHATSAPP_THEN_CALL_GAP
    queued = await ports.enqueue_call(
        session,
        task.business_id,
        employee_id=task.to_employee_id,
        phone_e164=phone,
        purpose="service",
        variables=await _call_variables(task),
        source="team",
        not_before=max(not_before, now),
        dedupe_key=f"task:{task.id}",
    )
    outcome["job_id"] = queued.ref if queued else None
    task.outcome = outcome
    task.status = "queued" if queued else "failed"
