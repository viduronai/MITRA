"""Owner decisions on routine runs that asked first (APPR), from WhatsApp or the approvals inbox.

Imported by ``api.v1.routines`` so the handler is registered when the app starts.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.approvals import register_handler
from mitra_core.models import RoutineRun
from mitra_core.team.routines.runs import decide_run

KIND = "routine_run"


async def on_routine_run_decided(session: AsyncSession, approval: Any) -> None:
    run_id = (approval.payload or {}).get("routine_run_id")
    if not run_id:
        return
    run = await session.scalar(
        select(RoutineRun).where(
            RoutineRun.id == uuid.UUID(str(run_id)),
            RoutineRun.business_id == approval.business_id,
        )
    )
    if run is not None:
        await decide_run(session, run, approved=approval.status == "approved")


register_handler(KIND, on_routine_run_decided)
