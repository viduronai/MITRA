"""What a customer's or staff member's WhatsApp button tap (or "PAID" reply) does.

Only taps that answer a message we actually sent to that same number with that same button
payload are acted on (``payload_was_sent``), so a forged payload does nothing.

* ``call_later`` (heads-up)  -> the imminent lead call is cancelled and a call is queued for the
  next calling window at least 2 hours away (dialer; compliance re-checked at dial time).
* ``call_me[:task:<id>]``    -> a call is queued now (the dialer waits for calling hours).
* ``not_now[:task:<id>]``    -> noted on the customer; that follow-up (or, without an id, every
  pending follow-up for them) is paused and its queued call cancelled.
* ``done:task|card:<id>``    -> the staff task / hand-off card is marked done.
* ``paid:<request id>`` or a "PAID" reply -> every registered paid-claim handler is told
  (payments flags the request for the owner). Nothing here ever marks a request paid.
* ``ill_come`` (appointment reminder) -> noted on the customer (their next appointment stays
  open) and thanked with the appointment time.
* ``change_time`` (booking confirmation / reminder) -> a call is queued now to find a new time
  (the dialer waits for calling hours); the appointment stays until it is actually moved.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.queries import business_tz
from mitra_core.logging import get_logger
from mitra_core.models import Contact, Employee, MemoryFact, WaMessage
from mitra_core.models.enums import EmployeeStatus, MemoryStatus
from mitra_core.pii import hash_phone
from mitra_core.telephony.compliance import DEFAULT_RULES, next_window_start
from mitra_core.whatsapp.templates import Lang

log = get_logger(__name__)

LATER_AT_LEAST = timedelta(hours=2)
_SPACE = re.compile(r"\s+")
_PAID_WORDS = frozenset(
    {
        "paid",
        "i paid",
        "i have paid",
        "payment done",
        "done paid",
        "पेड",
        "पे कर दिया",
        "pay kar diya",
        "pay kar diya hai",
        "pay kar diya h",
        "pay chesanu",
        "pay chesa",
        "pay చేశాను",
        "కట్టేశాను",
    }
)

Reply = Literal["call_later", "call_me", "not_now", "done", "paid", "ill_come", "change_time"]
REPLIES: dict[Reply, dict[Lang, str]] = {
    "call_later": {
        "en": "Sure. We'll call you at {time}.",
        "hi": "ज़रूर। हम आपको {time} पर call करेंगे।",
        "te": "సరే. మేము మీకు {time}కి call చేస్తాం.",
    },
    "call_me": {
        "en": "Sure, we'll call you shortly.",
        "hi": "ज़रूर, हम आपको जल्द call करेंगे।",
        "te": "సరే, మేము త్వరలో మీకు call చేస్తాం.",
    },
    "not_now": {
        "en": "Okay, we won't follow up for now.",
        "hi": "ठीक है, अभी हम follow-up नहीं करेंगे।",
        "te": "సరే, ప్రస్తుతానికి follow-up చేయము.",
    },
    "done": {
        "en": "Marked done. Thank you!",
        "hi": "Done मार्क किया। धन्यवाद!",
        "te": "Done అని గుర్తించాం. ధన్యవాదాలు!",
    },
    "paid": {
        "en": "Thank you! {business} will confirm your payment shortly.",
        "hi": "धन्यवाद! {business} जल्द आपका payment confirm करेगा।",
        "te": "ధన్యవాదాలు! {business} త్వరలో మీ payment confirm చేస్తుంది.",
    },
    "ill_come": {
        "en": "Thank you! See you on {when}.",
        "hi": "धन्यवाद! {when} को मिलते हैं।",
        "te": "ధన్యవాదాలు! {when}న కలుద్దాం.",
    },
    "change_time": {
        "en": "Sure, we'll call you shortly to find a new time.",
        "hi": "ज़रूर, नया समय तय करने के लिए हम आपको जल्द call करेंगे।",
        "te": "సరే, కొత్త సమయం నిర్ణయించడానికి మేము త్వరలో మీకు call చేస్తాం.",
    },
}


@dataclass(frozen=True, slots=True)
class PaidClaim:
    """The customer says they paid. A claim only: the owner (or the gateway) confirms."""

    business_id: uuid.UUID
    contact_phone: str
    phone_hash: str
    request_id: uuid.UUID | None  # from the "Already paid" button; None for a "PAID" reply
    via: Literal["button", "text"]
    message_id: str | None


PaidClaimHandler = Callable[[AsyncSession, PaidClaim], Awaitable[None]]
_paid_handlers: list[PaidClaimHandler] = []


def register_paid_claim_handler(fn: PaidClaimHandler) -> None:
    """Payments: flag the request for the owner. Must NEVER mark a request paid by itself."""
    if fn not in _paid_handlers:
        _paid_handlers.append(fn)


def is_paid_text(text: str) -> bool:
    norm = _SPACE.sub(" ", text.lower()).strip(" .!")
    return norm in _PAID_WORDS


async def payload_was_sent(
    session: AsyncSession,
    business_id: uuid.UUID,
    phone_hash: str,
    context_id: str | None,
    payload: str,
) -> WaMessage | None:
    """Our message (to this number) the tap answers, if it really carried ``payload``."""
    if not context_id:
        return None
    msg = await session.scalar(
        select(WaMessage).where(
            WaMessage.business_id == business_id,
            WaMessage.direction == "out",
            WaMessage.provider_message_id == context_id,
            WaMessage.phone_hash == phone_hash,
        )
    )
    if msg is None or not any(b.get("id") == payload for b in msg.buttons):
        return None
    return msg


async def _employee_for(
    session: AsyncSession, business_id: uuid.UUID, wanted: object
) -> uuid.UUID | None:
    if wanted:
        try:
            emp = await session.get(Employee, uuid.UUID(str(wanted)))
        except ValueError:
            emp = None
        if emp is not None and emp.business_id == business_id:
            return emp.id
    staff = list(
        await session.scalars(
            select(Employee)
            .where(Employee.business_id == business_id)
            .order_by(Employee.created_at)
        )
    )
    working = [e for e in staff if e.status == EmployeeStatus.WORKING]
    if working:
        return working[0].id
    return staff[0].id if staff else None


async def _queue_call(
    session: AsyncSession,
    business_id: uuid.UUID,
    phone: str,
    employee_id: uuid.UUID | None,
    *,
    not_before: datetime | None,
    note: str,
    dedupe: str,
) -> bool:
    from mitra_core.dialer.queue import EnqueueError, enqueue_call

    if employee_id is None:
        return False
    try:
        await enqueue_call(
            session,
            business_id,
            employee_id=employee_id,
            phone_e164=phone,
            purpose="service",
            variables={"callback_note": note},
            source="whatsapp",
            not_before=not_before,
            dedupe_key=dedupe,
        )
    except EnqueueError as exc:
        log.warning("whatsapp.button_enqueue_refused", reason=str(exc)[:120])
        return False
    return True


async def _cancel_queued(
    session: AsyncSession, business_id: uuid.UUID, phone_hash: str, source: str
) -> None:
    from mitra_core.dialer.queue import cancel_jobs
    from mitra_core.models.campaign import OutboundJob

    keys = await session.scalars(
        select(OutboundJob.dedupe_key).where(
            OutboundJob.business_id == business_id,
            OutboundJob.phone_hash == phone_hash,
            OutboundJob.source == source,
            OutboundJob.status == "queued",
            OutboundJob.dedupe_key.is_not(None),
        )
    )
    for key in set(keys):
        if key:
            await cancel_jobs(session, business_id, dedupe_key=key, reason="customer_asked_later")


async def _note(
    session: AsyncSession, business_id: uuid.UUID, contact: Contact, key: str, value: str
) -> None:
    """Upsert one confirmed memory fact on the customer."""
    fact = await session.scalar(
        select(MemoryFact).where(MemoryFact.contact_id == contact.id, MemoryFact.key == key)
    )
    if fact is None:
        session.add(
            MemoryFact(
                business_id=business_id,
                contact_id=contact.id,
                key=key,
                value=value,
                status=MemoryStatus.CONFIRMED,
                confidence=1.0,
            )
        )
    else:
        fact.value, fact.status, fact.confidence = value, MemoryStatus.CONFIRMED, 1.0
    await session.flush()


async def _contact(
    session: AsyncSession, business_id: uuid.UUID, phone_hash: str
) -> Contact | None:
    return await session.scalar(
        select(Contact).where(Contact.business_id == business_id, Contact.phone_hash == phone_hash)
    )


async def _pause_follow_ups(
    session: AsyncSession,
    business_id: uuid.UUID,
    phone_hash: str,
    task_id: str | None,
    now: datetime,
) -> None:
    from mitra_core.dialer.queue import cancel_jobs
    from mitra_core.models.team import FollowUpTask

    contact = await _contact(session, business_id, phone_hash)
    if contact is None:
        return
    note = f"Said “not now” to a WhatsApp follow-up on {now:%d %b %Y}"
    await _note(session, business_id, contact, "whatsapp_follow_up", note)
    stmt = select(FollowUpTask).where(
        FollowUpTask.business_id == business_id,
        FollowUpTask.contact_id == contact.id,
        FollowUpTask.status.in_(("pending", "queued")),
    )
    if task_id:
        stmt = stmt.where(FollowUpTask.id == uuid.UUID(task_id))
    for task in await session.scalars(stmt):
        if task.status == "queued":
            await cancel_jobs(session, business_id, dedupe_key=f"task:{task.id}", reason="not_now")
        task.status = "cancelled"
        task.outcome = {**(task.outcome or {}), "reason": "customer said not now on WhatsApp"}
    await session.flush()


async def _mark_done(
    session: AsyncSession, business_id: uuid.UUID, target: str, ident: str, now: datetime
) -> bool:
    from mitra_core.models.team import FollowUpTask, HandoffCard

    if target == "card":
        stmt = (
            update(HandoffCard)
            .where(HandoffCard.business_id == business_id, HandoffCard.id == uuid.UUID(ident))
            .values(status="done", resolved_at=now)
        )
    else:
        stmt = (
            update(FollowUpTask)
            .where(FollowUpTask.business_id == business_id, FollowUpTask.id == uuid.UUID(ident))
            .values(status="done")
        )
    result = await session.execute(stmt)
    return bool(getattr(result, "rowcount", 0))


def _task_id(payload: str) -> str | None:
    parts = payload.split(":")
    if len(parts) == 3 and parts[1] == "task":
        try:
            return str(uuid.UUID(parts[2]))
        except ValueError:
            return None
    return None


async def act(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    phone: str,
    payload: str | None,
    text: str,
    context_id: str | None,
    message_id: str | None,
    now: datetime,
) -> tuple[Reply, dict[str, str]] | None:
    """Run the action for one inbound tap/reply. Returns the reply key + its values, if any."""
    phone_hash = hash_phone(phone)
    if payload is None:
        if is_paid_text(text):
            claim = PaidClaim(business_id, phone, phone_hash, None, "text", message_id)
            for handler in _paid_handlers:
                await handler(session, claim)
            return "paid", {}
        return None
    sent = await payload_was_sent(session, business_id, phone_hash, context_id, payload)
    if sent is None:
        log.warning("whatsapp.button_unverified")
        return None
    head = payload.split(":", 1)[0]
    if head == "call_later":
        tz = await business_tz(session, business_id)
        at = next_window_start((now + LATER_AT_LEAST).astimezone(tz), DEFAULT_RULES.service_window)
        await _cancel_queued(session, business_id, phone_hash, "lead")
        employee = await _employee_for(session, business_id, sent.ref.get("employee_id"))
        if await _queue_call(
            session, business_id, phone, employee, not_before=at,
            note="Asked on WhatsApp to be called later", dedupe=f"wa_later:{phone_hash[:32]}",
        ):  # fmt: skip
            hour = at.hour % 12 or 12
            return "call_later", {
                "time": f"{hour}:{at.minute:02d} {'am' if at.hour < 12 else 'pm'}"
            }
        return None
    if head == "call_me":
        employee = await _employee_for(session, business_id, None)
        if await _queue_call(
            session, business_id, phone, employee, not_before=None,
            note="Tapped “Call me” on WhatsApp", dedupe=f"wa_call_me:{phone_hash[:32]}",
        ):  # fmt: skip
            return "call_me", {}
        return None
    if head == "not_now":
        await _pause_follow_ups(session, business_id, phone_hash, _task_id(payload), now)
        return "not_now", {}
    if head == "done":
        parts = payload.split(":")
        if len(parts) == 3 and parts[1] in {"task", "card"}:
            try:
                done = await _mark_done(session, business_id, parts[1], parts[2], now)
            except ValueError:
                done = False
            return ("done", {}) if done else None
        return None
    if head == "paid":
        try:
            request_id = uuid.UUID(payload.split(":", 1)[1])
        except (IndexError, ValueError):
            request_id = None
        claim = PaidClaim(business_id, phone, phone_hash, request_id, "button", message_id)
        for handler in _paid_handlers:
            await handler(session, claim)
        return "paid", {}
    if head == "ill_come":
        from mitra_core.manager.customer_sends import next_appointment_words  # avoids a cycle

        when = await next_appointment_words(session, business_id, phone, now)
        contact = await _contact(session, business_id, phone_hash)
        if when is None or contact is None:
            return None
        note = f"Confirmed on WhatsApp ({now:%d %b %Y}) they will come on {when}"
        await _note(session, business_id, contact, "appointment_confirmed", note)
        return "ill_come", {"when": when}
    if head == "change_time":
        from mitra_core.manager.customer_sends import next_appointment_words  # avoids a cycle

        when = await next_appointment_words(session, business_id, phone, now)
        note = "Wants to change their appointment" + (f" ({when})" if when else "")
        employee = await _employee_for(session, business_id, sent.ref.get("employee_id"))
        if await _queue_call(
            session, business_id, phone, employee, not_before=None,
            note=note, dedupe=f"wa_change_time:{phone_hash[:32]}",
        ):  # fmt: skip
            return "change_time", {}
        return None
    return None  # others: stored only
