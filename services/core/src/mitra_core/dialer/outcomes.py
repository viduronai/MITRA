"""What happens after a dial: retry ladder (CALL-04), result buckets, campaign bookkeeping.

Shared by the worker (outcomes it learns) and the campaign API (pause / complete).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.dialer import consent as list_consent
from mitra_core.dialer import hooks
from mitra_core.dialer.enums import CampaignStatus, ContactStatus, JobStatus, ResultBucket
from mitra_core.models import Call, Contact
from mitra_core.models.campaign import Campaign, CampaignContact, OutboundJob
from mitra_core.models.enums import CallDirection, CallResult
from mitra_core.telephony.enums import AttemptOutcome
from mitra_core.webhooks import service as webhooks

IST = ZoneInfo("Asia/Kolkata")

_BUCKETS: dict[CallResult, ResultBucket] = {
    CallResult.BOOKED: ResultBucket.INTERESTED,
    CallResult.INTERESTED: ResultBucket.INTERESTED,
    CallResult.TRANSFERRED: ResultBucket.INTERESTED,
    CallResult.CALL_BACK: ResultBucket.CALL_BACK,
    CallResult.NOT_INTERESTED: ResultBucket.NOT_INTERESTED,
    CallResult.MISSED: ResultBucket.NO_ANSWER,
}

PAUSE_TEXT = {
    "carrier_rejected": "The phone company kept rejecting calls",
    "spam_flagged": "Your calling number was marked as spam",
    "wallet": "Your Mitra balance is used up or the spending limit is reached",
    "number": "No healthy calling number is available",
    "ended": "The last calling day has passed",
}


def bucket_for(result: CallResult | None) -> ResultBucket:
    """An answered call without a clear result still needs a human follow-up."""
    return _BUCKETS.get(result, ResultBucket.CALL_BACK) if result else ResultBucket.CALL_BACK


def next_calling_time(campaign: Campaign, now: datetime) -> datetime | None:
    """``now`` if today is a calling day, else the start of the next one; None past ``ends_on``.

    Calling hours inside the day are left to ``compliance.check`` (it defers to the window).
    """
    local = now.astimezone(IST)
    holidays: set[date] = set(campaign.holidays or [])
    days = set(campaign.calling_days or range(7))
    for offset in range(60):
        day = local.date() + timedelta(days=offset)
        if campaign.ends_on is not None and day > campaign.ends_on:
            return None
        if day.weekday() in days and day not in holidays:
            return now if offset == 0 else datetime.combine(day, time(0), tzinfo=IST)
    return None


async def answered_call(session: AsyncSession, job: OutboundJob) -> Call | None:
    """The call record of an answered dial: same person, outbound, started after we dialled."""
    if job.dialed_at is None:
        return None
    found: Call | None = await session.scalar(
        select(Call)
        .join(Contact, Contact.id == Call.contact_id)
        .where(
            Call.business_id == job.business_id,
            Call.direction == CallDirection.OUTBOUND,
            Contact.phone_hash == job.phone_hash,
            Call.started_at >= job.dialed_at - timedelta(minutes=1),
        )
        .order_by(Call.started_at)
        .limit(1)
    )
    return found


async def finish_dial(
    session: AsyncSession,
    job: OutboundJob,
    outcome: AttemptOutcome,
    now: datetime,
    *,
    result: CallResult | None = None,
    call: Call | None = None,
) -> None:
    """Apply one dial's outcome: done (answered), retry later (ladder), or give up."""
    job.last_outcome = outcome
    bucket: ResultBucket | None = None
    if outcome == AttemptOutcome.ANSWERED:
        job.status = JobStatus.COMPLETED
        bucket = bucket_for(call.result if call is not None else result)
    elif job.attempts <= len(job.retry_ladder):
        job.status = JobStatus.QUEUED
        job.not_before = now + timedelta(minutes=job.retry_ladder[job.attempts - 1])
    else:
        job.status = JobStatus.FAILED
        bucket = ResultBucket.NO_ANSWER
    if job.status != JobStatus.QUEUED:
        job.finished_at = now
    contact = await _contact(session, job)
    if contact is not None:
        contact.attempts = job.attempts
        contact.last_outcome = outcome
        if bucket is not None:
            contact.status, contact.bucket = ContactStatus.DONE, bucket
            if call is not None:
                contact.call_id, contact.summary = call.id, call.summary
    if job.campaign_id is not None and job.status != JobStatus.QUEUED:
        await maybe_complete(session, job.campaign_id, now)


async def block_job(
    session: AsyncSession, job: OutboundJob, reasons: list[str], now: datetime
) -> None:
    job.status, job.reasons, job.finished_at = JobStatus.BLOCKED, reasons, now
    contact = await _contact(session, job)
    if contact is not None:
        contact.status, contact.bucket, contact.reasons = (
            ContactStatus.DONE,
            ResultBucket.BLOCKED,
            reasons,
        )
    if job.campaign_id is not None:
        await maybe_complete(session, job.campaign_id, now)


async def _contact(session: AsyncSession, job: OutboundJob) -> CampaignContact | None:
    if job.campaign_contact_id is None:
        return None
    return await session.get(CampaignContact, job.campaign_contact_id)


async def maybe_complete(session: AsyncSession, campaign_id: uuid.UUID, now: datetime) -> None:
    await session.flush()
    open_count = await session.scalar(
        select(func.count()).where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status.in_((ContactStatus.PENDING, ContactStatus.QUEUED)),
        )
    )
    campaign = await session.get(Campaign, campaign_id)
    if campaign is not None and not open_count and campaign.status == CampaignStatus.RUNNING:
        campaign.status, campaign.completed_at = CampaignStatus.COMPLETED, now
        await list_consent.expire(session, campaign, now)
        await _emit_finished(session, campaign, now)


async def _emit_finished(session: AsyncSession, campaign: Campaign, now: datetime) -> None:
    """``campaign.finished`` webhook (outbox row in this transaction; delivered by its cron)."""
    rows = (
        await session.execute(
            select(CampaignContact.status, CampaignContact.bucket, func.count())
            .where(CampaignContact.campaign_id == campaign.id)
            .group_by(CampaignContact.status, CampaignContact.bucket)
        )
    ).all()
    results = {b.value: 0 for b in ResultBucket}
    total = called = 0
    for status, bucket, n in rows:
        total += n
        if status == ContactStatus.DONE and bucket != ResultBucket.BLOCKED:
            called += n
        if bucket is not None:
            results[bucket.value] += n
    connected = called - results[ResultBucket.NO_ANSWER.value]
    await webhooks.emit_event(
        session,
        campaign.business_id,
        "campaign.finished",
        {
            "campaign_id": str(campaign.id),
            "name": campaign.name,
            "total": total,
            "called": called,
            "connected": connected,
            "results": results,
            "finished_at": now.isoformat(),
        },
        now=now,
    )


async def pause_campaign(session: AsyncSession, campaign: Campaign, reason: str) -> None:
    """Auto-pause (CALL-16) and tell the owner. Queued jobs wait; resume picks them up."""
    if campaign.status != CampaignStatus.RUNNING:
        return
    campaign.status, campaign.pause_reason = CampaignStatus.PAUSED, reason
    await hooks.alert_owner(
        session,
        campaign.business_id,
        kind="campaign_paused",
        title=f"Campaign paused: {campaign.name}",
        body=PAUSE_TEXT.get(reason, reason),
        link=f"/campaigns/{campaign.id}",
    )
