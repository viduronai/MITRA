"""Integration points owned by the manager module: owner alerts and approvals (APPR-01).

Kept in one place so tests can swap them and the dialer reads the same way whichever module
answers. Alerts go through ``manager.alerts.notify_owner`` (WhatsApp, deduped per subject).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import approvals
from mitra_core.logging import get_logger
from mitra_core.manager import alerts

log = get_logger(__name__)

LIST_CALL = "list_call"  # approval kind: calling a list; amount = number of people


async def alert_owner(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    kind: str,
    title: str,
    body: str,
    link: str | None = None,
) -> None:
    """Tell the owner something needs attention (e.g. a campaign auto-paused).

    Best effort, in a savepoint: a failing alert must never roll back the dialer's own work.
    """
    try:
        async with session.begin_nested():
            await alerts.notify_owner(
                session, business_id, kind=kind, title=title, body=body, link=link
            )
    except Exception:
        log.exception("dialer.alert_failed", business_id=str(business_id), kind=kind)


async def needs_list_approval(session: AsyncSession, business_id: uuid.UUID, people: int) -> bool:
    return await approvals.needs_approval(session, business_id, LIST_CALL, amount=people)


async def request_approval(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    summary: str,
    payload: dict[str, Any],
    requested_by: uuid.UUID | None,
) -> uuid.UUID:
    approval = await approvals.request_approval(
        session,
        business_id,
        kind=LIST_CALL,
        summary=summary,
        payload=payload,
        requested_by=f"user:{requested_by}" if requested_by else "campaign",
    )
    return approval.id
