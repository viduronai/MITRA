"""The routine scheduler: runs due routines and sends due follow-up WhatsApps.

``team_due_work(now)`` (SECURITY DEFINER, migration 0005_team) lists only ids of due work across
businesses; each item is then handled in its own transaction with that business bound as the
RLS tenant. ``FOR UPDATE SKIP LOCKED`` plus moving ``next_run_at`` forward in the same
transaction make concurrent ticks safe. A failure in one business never stops the others.

Run it as a loop next to the API (``uv run python -m mitra_core.team.scheduler``) or trigger
single ticks via ``POST /internal/v1/team/tick``.
TODO(temporal): replace with Temporal Schedules (TRD section 9).
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text

from mitra_core.clock import utcnow
from mitra_core.db import get_sessionmaker, tenant_session
from mitra_core.logging import get_logger
from mitra_core.models import Business, FollowUpTask, Routine
from mitra_core.team.dispatch import dispatch_task
from mitra_core.team.routines.runs import schedule_next, start_run
from mitra_core.tenancy import TenantContext

log = get_logger(__name__)
_DUE = text("SELECT kind, business_id, id FROM team_due_work(:now) LIMIT :limit")
TICK_LIMIT = 200


@dataclass
class TickResult:
    routines: int = 0
    tasks: int = 0
    failed: int = 0


async def _run_routine(business_id: uuid.UUID, routine_id: uuid.UUID, now: datetime) -> bool:
    async with tenant_session(TenantContext(business_id=business_id)) as session:
        routine = await session.scalar(
            select(Routine)
            .where(Routine.id == routine_id, Routine.business_id == business_id)
            .with_for_update(skip_locked=True)
        )
        if routine is None or not routine.enabled or routine.next_run_at is None:
            return False
        if routine.next_run_at > now:
            return False
        business = await session.get(Business, business_id)
        schedule_next(routine, business.timezone if business else "Asia/Kolkata", now)
        await start_run(session, routine, trigger="schedule", now=now)
        await session.commit()
        return True


async def _send_task(business_id: uuid.UUID, task_id: uuid.UUID, now: datetime) -> bool:
    async with tenant_session(TenantContext(business_id=business_id)) as session:
        task = await session.scalar(
            select(FollowUpTask)
            .where(FollowUpTask.id == task_id, FollowUpTask.business_id == business_id)
            .with_for_update(skip_locked=True)
        )
        if task is None or task.status != "pending":
            return False
        await dispatch_task(session, task, now=now)
        if task.status == "pending":  # nothing could act on it: do not spin on it forever
            task.status = "failed"
            task.outcome = {**task.outcome, "reason": "could_not_dispatch"}
        await session.commit()
        return True


async def tick(now: datetime | None = None) -> TickResult:
    now = now or utcnow()
    async with get_sessionmaker()() as session:
        due = (await session.execute(_DUE, {"now": now, "limit": TICK_LIMIT})).all()
    result = TickResult()
    for kind, business_id, item_id in due:
        try:
            if kind == "routine":
                result.routines += await _run_routine(business_id, item_id, now)
            else:
                result.tasks += await _send_task(business_id, item_id, now)
        except Exception as exc:
            result.failed += 1
            log.error(
                "team.tick_failed",
                kind=kind,
                business_id=str(business_id),
                exc_type=type(exc).__name__,
            )
    if due:
        log.info("team.tick", routines=result.routines, tasks=result.tasks, failed=result.failed)
    return result


async def run_forever(interval_s: float) -> None:
    while True:
        await tick()
        await asyncio.sleep(interval_s)


def main() -> None:  # pragma: no cover - process entry point
    parser = argparse.ArgumentParser(description="Mitra routine scheduler")
    parser.add_argument("--interval", type=float, default=30.0, help="seconds between ticks")
    parser.add_argument("--once", action="store_true", help="run a single tick and exit")
    args = parser.parse_args()
    asyncio.run(tick() if args.once else run_forever(args.interval))


if __name__ == "__main__":  # pragma: no cover
    main()
