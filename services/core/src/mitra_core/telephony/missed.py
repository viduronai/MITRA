"""Missed-call number (CALL-20): "Give a missed call on 040-xxxx and we'll call you back".

A call to the business's missed-call number is rejected before answer by the voice service (free
for the caller), which reports it here. A missed call is a customer-initiated request, so it is
recorded as service consent (source ``missed_call``, 08 section 3 rule 1) and a ``callback`` is
queued in the dialer about a minute later from the same number; the dialer's compliance check
still runs right before dialling (opt-outs, hours, caps, wallet). Outside calling hours the call
waits for the next window and the caller gets a WhatsApp "We'll call you back at 9:00 am"
(``missed_call_callback`` template outside the 24-hour window, via ``send_customer_message``).

Abuse guards: a block list (``caller_block``), opted-out callers, one pending callback per caller
(deduped for ``dedupe_minutes``), at most ``per_caller_day`` callbacks per caller per day and
``per_business_hour`` missed calls handled per business per hour.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.service import upsert_contact
from mitra_core.dialer.enums import JobStatus
from mitra_core.dialer.queue import enqueue_call
from mitra_core.logging import get_logger
from mitra_core.models import (
    Business,
    CallerBlock,
    ConsentRecord,
    Employee,
    MissedCall,
    OptOut,
    OutboundJob,
    PhoneNumber,
)
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.telephony.compliance import DEFAULT_RULES, next_window_start
from mitra_core.telephony.enums import AttemptOutcome, CallPurpose, ConsentScope, ConsentSource

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MissedCallLimits:
    delay_seconds: int = 45  # "we'll call you back in 1 minute"
    dedupe_minutes: int = 30
    per_caller_day: int = 3
    per_business_hour: int = 60
    whatsapp_when_deferred: bool = True


DEFAULT_LIMITS = MissedCallLimits()


@dataclass(frozen=True, slots=True)
class MissedCallResult:
    row: MissedCall
    deferred: bool = False


def callback_dedupe_key(phone_hash: str) -> str:
    """Shared with the voice brain's callbacks (CALL-05) and missed-call rescue (CALL-02)."""
    return f"callback:{phone_hash[:32]}"


async def _count(session: AsyncSession, *where: ColumnElement[bool]) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(MissedCall).where(*where)) or 0
    )


async def _blocked(session: AsyncSession, business_id: uuid.UUID, phone_hash: str) -> bool:
    block = await session.scalar(
        select(CallerBlock.id).where(
            CallerBlock.business_id == business_id, CallerBlock.phone_hash == phone_hash
        )
    )
    if block is not None:
        return True
    opted = await session.scalar(
        select(OptOut.id)
        .where(OptOut.business_id == business_id, OptOut.phone_hash == phone_hash)
        .where(or_(OptOut.purpose.is_(None), OptOut.purpose == CallPurpose.CALLBACK))
        .limit(1)
    )
    return opted is not None


async def _record_consent(
    session: AsyncSession, business_id: uuid.UUID, phone_hash: str, now: datetime
) -> None:
    """One active ``missed_call`` consent per caller is enough evidence."""
    existing = await session.scalar(
        select(ConsentRecord.id)
        .where(
            ConsentRecord.business_id == business_id,
            ConsentRecord.phone_hash == phone_hash,
            ConsentRecord.source == ConsentSource.MISSED_CALL,
            ConsentRecord.revoked_at.is_(None),
        )
        .limit(1)
    )
    if existing is None:
        session.add(
            ConsentRecord(
                business_id=business_id,
                phone_hash=phone_hash,
                scope=ConsentScope.SERVICE,
                source=ConsentSource.MISSED_CALL,
                note="Gave a missed call to ask for a call back",
                captured_at=now,
            )
        )


def _when_words(at: datetime) -> str:
    """9:00 am / 9:30 pm (the caller's local time)."""
    hour = at.hour % 12 or 12
    return f"{hour}:{at.minute:02d} {'am' if at.hour < 12 else 'pm'}"


async def _tell_deferred(
    session: AsyncSession, business: Business, phone: str, local_at: datetime, now_local: datetime
) -> None:
    """ "We'll call you back at 9:00 am": free text inside WhatsApp's 24-hour window, else the
    approved ``missed_call_callback`` template (clock time only; hi/te append their own word)."""
    from mitra_core.whatsapp import send_customer_message  # manager's module; best effort

    when = _when_words(local_at)
    day = "" if local_at.date() == now_local.date() else " tomorrow"
    try:
        async with session.begin_nested():
            await send_customer_message(
                session,
                business.id,
                to_phone=phone,
                template="missed_call_callback",
                params={"time": when},
                text=f"Thanks for your missed call to {business.name}. "
                f"We'll call you back at {when}{day}.",
                ref={"kind": "missed_call"},
                dedupe_key=f"missed_call:{local_at.date().isoformat()}",
            )
    except Exception as exc:
        log.warning("missed_call.whatsapp_failed", error=type(exc).__name__)


async def handle_missed_call(
    session: AsyncSession,
    business: Business,
    number: PhoneNumber,
    employee: Employee,
    caller_e164: str,
    *,
    now: datetime,
    carrier_call_sid: str | None = None,
    limits: MissedCallLimits = DEFAULT_LIMITS,
) -> MissedCallResult:
    """Record one missed call and queue the callback (flushes; the caller commits)."""
    bid = business.id
    phone_hash = hash_phone(caller_e164)
    row = MissedCall(
        business_id=bid,
        phone_number_id=number.id,
        phone_hash=phone_hash,
        phone_last4=phone_last4(caller_e164),
        status="queued",
        carrier_call_sid=carrier_call_sid,
        received_at=now,
    )
    session.add(row)

    if await _blocked(session, bid, phone_hash):
        row.status = "blocked"
    elif (
        await _count(
            session,
            MissedCall.business_id == bid,
            MissedCall.received_at > now - timedelta(hours=1),
        )
        >= limits.per_business_hour
        or await _count(
            session,
            MissedCall.business_id == bid,
            MissedCall.phone_hash == phone_hash,
            MissedCall.status == "queued",
            MissedCall.received_at > now - timedelta(days=1),
        )
        >= limits.per_caller_day
    ):
        row.status = "rate_limited"
    if row.status != "queued":
        await session.flush()
        log.info("missed_call.ignored", business_id=str(bid), status=row.status)
        return MissedCallResult(row)

    contact = await upsert_contact(session, bid, caller_e164)  # keeps the number encrypted
    row.contact_id = contact.id
    recent = await session.scalar(
        select(MissedCall)
        .where(
            MissedCall.business_id == bid,
            MissedCall.phone_hash == phone_hash,
            MissedCall.status == "queued",
            MissedCall.received_at > now - timedelta(minutes=limits.dedupe_minutes),
            MissedCall.id != row.id,
        )
        .order_by(MissedCall.received_at.desc())
        .limit(1)
    )
    if recent is not None:
        row.status, row.job_id, row.call_back_at = "deduped", recent.job_id, recent.call_back_at
        await session.flush()
        return MissedCallResult(row)

    await _record_consent(session, bid, phone_hash, now)
    tz = ZoneInfo(business.timezone or "Asia/Kolkata")
    local_soon = (now + timedelta(seconds=limits.delay_seconds)).astimezone(tz)
    start = next_window_start(local_soon, DEFAULT_RULES.service_window)
    deferred = start > local_soon
    job = await enqueue_call(
        session,
        bid,
        employee_id=employee.id,
        phone_e164=caller_e164,
        purpose=CallPurpose.CALLBACK,
        variables={"callback_note": "Gave a missed call to ask for a call back"},
        source="missed_call",
        not_before=start,
        dedupe_key=callback_dedupe_key(phone_hash),
        called_number_id=number.id,
    )
    row.job_id, row.call_back_at = job.id, job.not_before
    await session.flush()
    if deferred and limits.whatsapp_when_deferred:
        await _tell_deferred(session, business, caller_e164, start, now.astimezone(tz))
    log.info("missed_call.queued", business_id=str(bid), deferred=deferred)
    return MissedCallResult(row, deferred=deferred)


@dataclass(frozen=True, slots=True)
class MissedCallStats:
    missed: int
    called_back: int
    answered: int


async def stats(session: AsyncSession, business_id: uuid.UUID, since: datetime) -> MissedCallStats:
    """Missed calls received, how many we dialled back, how many of those picked up."""
    missed = await _count(
        session, MissedCall.business_id == business_id, MissedCall.received_at >= since
    )
    jobs = (
        select(OutboundJob.id, OutboundJob.attempts, OutboundJob.last_outcome, OutboundJob.status)
        .where(OutboundJob.business_id == business_id)
        .where(
            OutboundJob.id.in_(
                select(MissedCall.job_id).where(
                    MissedCall.business_id == business_id,
                    MissedCall.received_at >= since,
                    MissedCall.status == "queued",
                )
            )
        )
    )
    called = answered = 0
    for _, attempts, outcome, status in await session.execute(jobs):
        if attempts > 0 or status in (JobStatus.DIALING, JobStatus.COMPLETED):
            called += 1
        if outcome == AttemptOutcome.ANSWERED:
            answered += 1
    return MissedCallStats(missed=missed, called_back=called, answered=answered)
