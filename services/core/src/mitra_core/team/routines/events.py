"""Event routines (AUTO-02 beyond new leads): "When [a call is missed], [Priya] calls them".

Other modules call :func:`fire_event` with the RLS tenant bound, inside their own transaction
(it flushes, never commits). Each enabled routine listening for the event starts a one-person
run for the event's contact.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.models import FollowUpTask, Routine, RoutineRun
from mitra_core.team.routines.runs import start_run
from mitra_core.team.routines.spec import EVENTS


async def fire_event(
    session: AsyncSession,
    business_id: uuid.UUID,
    name: str,
    *,
    contact_id: uuid.UUID,
    now: datetime | None = None,
    source_call_id: uuid.UUID | None = None,
) -> list[RoutineRun]:
    """``source_call_id``: the call that caused the event; re-processing it fires nothing new."""
    if name not in EVENTS:
        raise ValueError(f"unknown routine event {name!r}")
    if source_call_id is not None:
        seen = await session.scalar(
            select(FollowUpTask.id).where(
                FollowUpTask.source_call_id == source_call_id, FollowUpTask.kind == "routine"
            )
        )
        if seen is not None:
            return []
    routines = await session.scalars(
        select(Routine)
        .where(Routine.business_id == business_id, Routine.enabled.is_(True))
        .where(Routine.spec["trigger"]["type"].astext == "event")
        .where(Routine.spec["trigger"]["event"].astext == name)
    )
    return [
        await start_run(
            session,
            r,
            trigger="event",
            now=now or utcnow(),
            event_contact=contact_id,
            source_call_id=source_call_id,
        )
        for r in routines
    ]
