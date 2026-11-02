"""Entry points other modules call. Each one is safe: a team failure never fails its caller."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.logging import get_logger
from mitra_core.models import Call
from mitra_core.models.enums import CallResult
from mitra_core.team.handoff import after_call
from mitra_core.team.routines.events import fire_event

log = get_logger(__name__)
# Call results that are routine events by themselves (AUTO-02).
RESULT_EVENTS = {CallResult.MISSED: "call.missed", CallResult.BOOKED: "booking.made"}


async def after_call_processed(session: AsyncSession, call_id: uuid.UUID) -> None:
    """After post-call analysis committed: hand-off tasks, escalations, event routines."""
    try:
        await after_call(session, call_id)
        call = await session.get(Call, call_id)
        event = RESULT_EVENTS.get(call.result) if call and call.result else None
        if call is not None and event and call.contact_id is not None:
            await fire_event(
                session,
                call.business_id,
                event,
                contact_id=call.contact_id,
                source_call_id=call.id,
            )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        log.error("team.after_call_failed", call_id=str(call_id), exc_type=type(exc).__name__)
