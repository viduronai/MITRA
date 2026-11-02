"""Running a routine: dry run (AUTO-04), approval gate, tasks per person, history (AUTO-05).

A run that would contact more people than ``approval_over`` waits in ``awaiting_approval``
("Ask me first", APPR) and only executes on :func:`decide_run`. Each person becomes a
``follow_up_task`` (kind ``routine``) dispatched like a hand-off, so the dialer's compliance
check, retries and results apply the same way.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.logging import get_logger
from mitra_core.models import Business, Contact, Employee, FollowUpTask, Routine, RoutineRun
from mitra_core.team import ports
from mitra_core.team.dispatch import dispatch_task
from mitra_core.team.handoff import context_packet
from mitra_core.team.routines.audience import Person, contact_ids, people
from mitra_core.team.routines.spec import GOAL_TASK, EventTrigger, RoutineSpec, next_run, sentence

log = get_logger(__name__)


@dataclass
class Preview:
    contacted: list[Person] = field(default_factory=list)
    skipped: list[Person] = field(default_factory=list)

    @property
    def skipped_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.skipped:
            counts[p.skip or "other"] = counts.get(p.skip or "other", 0) + 1
        return counts


async def _tz(session: AsyncSession, business_id: uuid.UUID) -> str:
    business = await session.get(Business, business_id)
    return business.timezone if business else "Asia/Kolkata"


async def preview(
    session: AsyncSession,
    business_id: uuid.UUID,
    spec: RoutineSpec,
    *,
    now: datetime,
    event_contact: uuid.UUID | None = None,
) -> Preview:
    """Exactly who would be contacted right now, and who would be skipped and why."""
    if isinstance(spec.trigger, EventTrigger):
        ids = [event_contact] if event_contact else []
    else:
        tz = await _tz(session, business_id)
        ids = await contact_ids(session, business_id, spec.audience or "", now, tz)
    result = Preview()
    for person in await people(session, business_id, ids):
        (result.skipped if person.skip else result.contacted).append(person)
    return result


def _row(person: Person, status: str) -> dict[str, str | None]:
    return {
        "contact_id": str(person.contact_id),
        "name": person.name,
        "last4": person.last4,
        "status": status,
    }


async def start_run(
    session: AsyncSession,
    routine: Routine,
    *,
    trigger: str,
    now: datetime | None = None,
    event_contact: uuid.UUID | None = None,
    source_call_id: uuid.UUID | None = None,
) -> RoutineRun:
    """Resolve the audience now; execute, or wait for approval when it is large."""
    now = now or utcnow()
    spec = RoutineSpec.model_validate(routine.spec)
    found = await preview(session, routine.business_id, spec, now=now, event_contact=event_contact)
    run = RoutineRun(
        business_id=routine.business_id,
        routine_id=routine.id,
        trigger=trigger,
        status="running",
        audience_count=len(found.contacted) + len(found.skipped),
        skipped=found.skipped_counts,
        contacts=[_row(p, "waiting") for p in found.contacted]
        + [_row(p, p.skip or "skipped") for p in found.skipped],
        started_at=now,
    )
    session.add(run)
    await session.flush()
    routine.last_run_at = now
    if len(found.contacted) > spec.approval_over:
        employee = await session.get(Employee, spec.action.employee_id)
        text = sentence(spec, employee.name if employee else "Your employee")
        run.status = "awaiting_approval"
        run.approval_ref = await ports.request_approval(
            session,
            routine.business_id,
            subject="routine_run",
            summary=f"{routine.name}: {len(found.contacted)} people. {text}",
            payload={"routine_run_id": str(run.id), "count": len(found.contacted)},
        )
        return run
    await _execute(session, routine, run, spec, found.contacted, now, source_call_id)
    return run


async def _execute(
    session: AsyncSession,
    routine: Routine,
    run: RoutineRun,
    spec: RoutineSpec,
    persons: list[Person],
    now: datetime,
    source_call_id: uuid.UUID | None = None,
) -> None:
    delay = spec.trigger.delay_minutes if isinstance(spec.trigger, EventTrigger) else 0
    statuses: dict[str, str] = {}
    for person in persons:
        contact = await session.get(Contact, person.contact_id)
        task = FollowUpTask(
            business_id=routine.business_id,
            contact_id=person.contact_id,
            to_employee_id=spec.action.employee_id,
            routine_run_id=run.id,
            source_call_id=source_call_id,
            kind="routine",
            task=GOAL_TASK[spec.action.goal],
            channel=spec.action.verb,
            due_at=now + timedelta(minutes=delay),
            status="pending",
            context=await context_packet(session, contact, None)
            | {"routine": routine.name, "goal": spec.action.goal},
        )
        session.add(task)
        await session.flush()
        await dispatch_task(session, task, now=now)
        statuses[str(person.contact_id)] = task.status
    run.contacts = [
        {**row, "status": statuses.get(str(row["contact_id"]), row["status"])}
        for row in run.contacts
    ]
    run.contacted_count = sum(1 for s in statuses.values() if s in {"queued", "sent", "pending"})
    run.status = "done"
    run.finished_at = now


async def decide_run(
    session: AsyncSession, run: RoutineRun, *, approved: bool, now: datetime | None = None
) -> RoutineRun:
    """The owner's answer to a large run (from the app or the WhatsApp approval card)."""
    now = now or utcnow()
    if run.status != "awaiting_approval":
        return run
    if not approved:
        run.status = "declined"
        run.finished_at = now
        return run
    routine = await session.get(Routine, run.routine_id)
    if routine is None:
        run.status = "failed"
        return run
    spec = RoutineSpec.model_validate(routine.spec)
    ids = [uuid.UUID(str(r["contact_id"])) for r in run.contacts if r["status"] == "waiting"]
    persons = [p for p in await people(session, run.business_id, ids) if not p.skip]
    await _execute(session, routine, run, spec, persons, now)
    return run


async def refresh_results(session: AsyncSession, run: RoutineRun) -> list[dict[str, object]]:
    """History rows with the latest task outcome (queued -> the dialer's job status)."""
    tasks = {
        str(t.contact_id): t
        for t in await session.scalars(
            select(FollowUpTask).where(FollowUpTask.routine_run_id == run.id)
        )
    }
    job_status: dict[str, str] = {}
    job_ids = [t.outcome.get("job_id") for t in tasks.values() if t.outcome.get("job_id")]
    if job_ids:
        try:
            from mitra_core.models.campaign import OutboundJob

            jobs = await session.execute(
                select(OutboundJob.id, OutboundJob.status, OutboundJob.last_outcome).where(
                    OutboundJob.id.in_([uuid.UUID(str(j)) for j in job_ids])
                )
            )
            for job_id, job_state, outcome in jobs:
                value = outcome.value if outcome is not None else job_state.value
                job_status[str(job_id)] = str(value)
        except ImportError:  # pragma: no cover
            pass
    rows: list[dict[str, object]] = []
    for row in run.contacts:
        task = tasks.get(str(row["contact_id"]))
        status = str(row["status"])
        if task is not None:
            status = job_status.get(str(task.outcome.get("job_id")), task.status)
        rows.append({**row, "status": status})
    return rows


def schedule_next(routine: Routine, tz: str, now: datetime) -> None:
    spec = RoutineSpec.model_validate(routine.spec)
    routine.next_run_at = next_run(spec, now, tz) if routine.enabled else None
