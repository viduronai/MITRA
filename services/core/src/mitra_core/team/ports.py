"""The team module's edges: the dialer queue, WhatsApp, approvals and a contact's number.

Each port is a plain module-level function so tests can monkeypatch it, and each degrades to
"not available" (``None`` / ``False``) instead of raising when the other module is missing or
refuses: a follow-up the dialer cannot take stays visible as a task, it is never lost.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.logging import get_logger
from mitra_core.models import Contact

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Queued:
    ref: str  # the dialer job id / message id


async def enqueue_call(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    employee_id: uuid.UUID,
    phone_e164: str,
    purpose: str,
    variables: dict[str, str],
    source: str,
    not_before: datetime | None = None,
    dedupe_key: str | None = None,
) -> Queued | None:
    """Queue a follow-up call through the campaigns dialer (compliance runs at dial time)."""
    from mitra_core.dialer.queue import EnqueueError
    from mitra_core.dialer.queue import enqueue_call as dialer_enqueue

    try:
        job = await dialer_enqueue(
            session,
            business_id,
            employee_id=employee_id,
            phone_e164=phone_e164,
            purpose=purpose,
            variables=variables,
            source=source,
            not_before=not_before,
            dedupe_key=dedupe_key,
        )
    except EnqueueError as exc:
        log.warning("team.enqueue_refused", reason=str(exc)[:120])
        return None
    return Queued(ref=str(job.id))


async def contact_phone(
    session: AsyncSession,
    contact: Contact,
    *,
    purpose: str = "team_follow_up",
    actor: str = "team",
) -> str | None:
    """The dialable E.164 for a contact, if one is on file; access-logged, never logged."""
    from mitra_core.phones import reveal_phone

    return await reveal_phone(
        session, contact.business_id, contact.id, purpose=purpose, actor=actor
    )


async def has_contact_phone(session: AsyncSession, contact: Contact) -> bool:
    """Whether a number is on file, without decrypting it (dry runs, audience previews)."""
    from mitra_core.phones import has_phone

    return await has_phone(session, contact.business_id, contact.id)


async def send_whatsapp(
    session: AsyncSession,
    business_id: uuid.UUID,
    to_e164: str,
    text: str,
    *,
    kind: str,
    task: str | None = None,
    ref_id: str | None = None,
    name: str | None = None,
) -> str | None:
    """Text a staff member, the owner or (team follow-ups) a customer via the WhatsApp module.

    Returns the stored message id, or None if it could not be sent.
    """
    from mitra_core.whatsapp import send_team_message

    try:
        # Free text inside WhatsApp's 24-hour window, else the approved template for the kind.
        # A savepoint: a failed send never poisons the caller's transaction.
        async with session.begin_nested():
            msg = await send_team_message(
                session,
                business_id,
                to_phone=to_e164,
                text=text,
                kind=kind,
                task=task,
                ref_id=ref_id,
                name=name,
            )
    except Exception as exc:
        log.warning("team.whatsapp_failed", kind=kind, error=type(exc).__name__)
        return None
    if msg is None or msg.status != "sent":
        return None
    return str(msg.id)


@dataclass(frozen=True, slots=True)
class OwnerNotice:
    recipients: int  # owners/managers the WhatsApp module would reach (0 = nobody set up)
    message_ids: list[str]


async def notify_owner(
    session: AsyncSession,
    business_id: uuid.UUID,
    kind: str,
    text: str,
    *,
    dedupe_key: str | None = None,
    ref: dict[str, Any] | None = None,
) -> OwnerNotice:
    """TEAM-05: alert every owner/manager per their WhatsApp alert settings (manager module).

    ``message_ids`` can be empty with recipients > 0: the owner switched this kind off, or the
    same alert (same ``dedupe_key``) already went out, e.g. manager's own "urgent" call alert.
    """
    from mitra_core.whatsapp import notify_owner as wa_notify_owner
    from mitra_core.whatsapp.service import owner_recipients

    recipients = len(await owner_recipients(session, business_id))
    try:
        async with session.begin_nested():
            sent = await wa_notify_owner(
                session, business_id, kind, text, ref=ref, dedupe_key=dedupe_key
            )
    except Exception as exc:
        log.warning("team.notify_owner_failed", kind=kind, error=type(exc).__name__)
        return OwnerNotice(recipients=recipients, message_ids=[])
    return OwnerNotice(recipients=recipients, message_ids=[str(m.id) for m in sent])


async def request_approval(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    subject: str,
    summary: str,
    payload: dict[str, Any],
) -> str | None:
    """Ask the owner first (APPR). Returns the approval id, or None if it could not be asked.

    The decision comes back through the ``routine_run`` handler in
    :mod:`mitra_core.team.approval_handlers`.
    """
    from mitra_core.approvals import request_approval as ask

    try:
        async with session.begin_nested():
            approval = await ask(
                session,
                business_id,
                kind=subject,
                summary=summary[:500],
                payload=payload,
                requested_by="routine",
                default_action="decline",
            )
    except Exception as exc:
        log.warning("team.approval_failed", error=type(exc).__name__)
        return None
    return str(approval.id)


async def withdraw_approval(session: AsyncSession, business_id: uuid.UUID, ref: str) -> None:
    """The owner decided in the Routines screen: withdraw the WhatsApp card for the same run."""
    from mitra_core.approvals import cancel

    try:
        async with session.begin_nested():
            await cancel(session, business_id, uuid.UUID(ref), reason="decided in the app")
    except Exception as exc:
        log.warning("team.approval_withdraw_failed", error=type(exc).__name__)
