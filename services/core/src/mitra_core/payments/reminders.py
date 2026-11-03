"""Reminder routines for unpaid links, and stopping them the moment a link is paid (ACT-11).

``fire`` starts the business's event routines for a payment (``payment.overdue`` -> the ready-made
"Payment reminder" call, ``payment.failed`` -> "EMI / fee reminder") and records the runs on the
request. ``stop`` cancels every follow-up those runs created: pending tasks, queued dialer jobs
(``dialer.queue.cancel_jobs``) and runs still waiting for the owner. A call already ringing is
left to finish. Compliance (hours, frequency caps, "don't call me") is re-checked by the dialer
right before every dial, so a reminder can never exceed the defaults.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.logging import get_logger
from mitra_core.models import FollowUpTask, PaymentRequest, RoutineRun
from mitra_core.payments.messages import rupees

log = get_logger(__name__)

OPEN = ("sent", "failed")
REMIND_AT_LOCAL = time(10, 0)  # the overdue reminder goes out the morning after the due date
EXPIRY_NOTICE = timedelta(days=2)  # one WhatsApp this long before an unpaid link expires
EXPIRY_SENT = "expiry_whatsapp_at"


def overdue_at(due: date | None, tz: str) -> datetime | None:
    if due is None:
        return None
    local = datetime.combine(due + timedelta(days=1), REMIND_AT_LOCAL, ZoneInfo(tz))
    return local.astimezone(ZoneInfo("UTC"))


def expiry_notice_at(req: PaymentRequest) -> datetime | None:
    """Two days before expiry, unless the link was sent later than that (short expiries)."""
    if req.expires_at is None or EXPIRY_SENT in req.reminders:
        return None
    at = req.expires_at - EXPIRY_NOTICE
    return at if req.sent_at is None or at > req.sent_at else None


def next_step_at(req: PaymentRequest, *, reminders_enabled: bool, tz: str) -> datetime | None:
    """When the reminder tick must next look at this request: a reminder, or the expiry."""
    if req.status not in OPEN:
        return None
    steps: list[datetime | None] = [req.expires_at]
    if reminders_enabled:
        if req.reminder_stage == 0:
            steps.append(overdue_at(req.due_date, tz))
        steps.append(expiry_notice_at(req))
    due = [s for s in steps if s is not None and (req.expires_at is None or s <= req.expires_at)]
    return min(due) if due else None


def call_context(req: PaymentRequest) -> dict[str, Any]:
    """What the reminder call's brief and WhatsApp may say (only the request's own facts)."""
    out: dict[str, Any] = {
        "payment_amount": rupees(req.amount_paise),
        "payment_purpose": req.purpose,
        "payment_request_id": str(req.id),
    }
    if req.due_date:
        out["payment_due"] = f"{req.due_date:%d %b %Y}"
    if req.short_url:
        out["payment_link"] = req.short_url
    return out


async def fire(session: AsyncSession, req: PaymentRequest, event: str, *, now: datetime) -> int:
    """Start the routines listening for ``event`` for this customer; returns runs started."""
    from mitra_core.team.routines.events import fire_event

    if req.contact_id is None:
        return 0
    runs = await fire_event(
        session,
        req.business_id,
        event,
        contact_id=req.contact_id,
        now=now,
        context=call_context(req),
    )
    if runs:
        known = list(req.reminders.get("runs", []))
        req.reminders = {**req.reminders, "runs": known + [str(r.id) for r in runs]}
    return len(runs)


async def stop(session: AsyncSession, req: PaymentRequest, *, reason: str) -> int:
    """Cancel what this request's reminder runs still have queued. Returns items cancelled."""
    from mitra_core.dialer.queue import cancel_jobs
    from mitra_core.team import ports

    req.remind_at = None
    run_ids = [uuid.UUID(str(r)) for r in req.reminders.get("runs", []) if r]
    if not run_ids:
        return 0
    cancelled = 0
    tasks = await session.scalars(
        select(FollowUpTask)
        .where(FollowUpTask.business_id == req.business_id)
        .where(FollowUpTask.routine_run_id.in_(run_ids))
        .where(FollowUpTask.status.in_(("pending", "queued")))
        .with_for_update()
    )
    for task in tasks:
        if task.status == "queued":
            await cancel_jobs(session, req.business_id, dedupe_key=f"task:{task.id}", reason=reason)
        task.status = "cancelled"
        task.outcome = {**(task.outcome or {}), "reason": f"payment_{reason}"}
        cancelled += 1
    waiting = await session.scalars(
        select(RoutineRun)
        .where(RoutineRun.business_id == req.business_id)
        .where(RoutineRun.id.in_(run_ids), RoutineRun.status == "awaiting_approval")
    )
    for run in waiting:
        run.status = "declined"
        if run.approval_ref:
            await ports.withdraw_approval(session, req.business_id, run.approval_ref)
        cancelled += 1
    req.reminders = {**req.reminders, "stopped": reason}
    log.info("payments.reminders_stopped", business_id=str(req.business_id), count=cancelled)
    return cancelled
