"""The dialer worker: due jobs -> compliance.check -> place the call -> outcome -> retry ladder.

One :func:`tick` serves every business with work (found through a SECURITY DEFINER function,
migration 0005_campaigns); each business runs in its own session bound to its RLS tenant.
Per business:

1. reconcile calls in flight (outcome from the attempt row, or a timeout -> no answer);
2. dial due jobs while a channel is free (CALL-09, default 5), one job per transaction, picked
   with ``FOR UPDATE SKIP LOCKED`` so parallel workers never dial the same job;
3. never two live calls to the same person; campaign days / holidays / end date respected;
4. ``compliance.check`` decides: BLOCK (reasons kept), DEFER (``not_before = defer_until``) or
   ALLOW. Business-level blocks (wallet, no usable number) pause the campaign instead of
   burning its contacts. The attempt row is committed BEFORE dialling.
5. carrier rejections count as strikes; repeated strikes or a spam flag auto-pause the campaign
   and alert the owner (CALL-16).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mitra_core.config import Settings
from mitra_core.dialer.enums import CampaignStatus, ContactStatus, JobStatus
from mitra_core.dialer.outcomes import (
    answered_call,
    block_job,
    finish_dial,
    next_calling_time,
    pause_campaign,
)
from mitra_core.dialer.queue import is_collection
from mitra_core.dialer.sealing import unseal
from mitra_core.dialer.settings import DialerSettings
from mitra_core.dialer.voice import DialRejectedError, PlaceRequest, VoiceDialer
from mitra_core.logging import get_logger
from mitra_core.models import Business, OutboundAttempt, PhoneNumber
from mitra_core.models.campaign import Campaign, CampaignContact, DialerConfig, OutboundJob
from mitra_core.models.enums import CallStatus
from mitra_core.telephony import service as telephony
from mitra_core.telephony.compliance import evaluate
from mitra_core.telephony.dnd import DndProvider
from mitra_core.telephony.enums import AttemptOutcome, Decision
from mitra_core.tenancy import TenantContext, set_tenant

log = get_logger(__name__)

_DUE = text("SELECT internal_dialer_businesses(:now)")
SAME_PERSON_WAIT = timedelta(minutes=5)
BUSINESS_WAIT = timedelta(minutes=15)
# Blocks that are about the business, not the person: pause the campaign, keep the contact.
BUSINESS_BLOCKS = {
    "wallet_zero_balance": "wallet",
    "wallet_spend_cap": "wallet",
    "number_paused": "number",
    "no_caller_id": "number",
    "promotional_disabled": "number",
}


@dataclass
class TickReport:
    businesses: int = 0
    dialed: int = 0
    deferred: int = 0
    blocked: int = 0
    finished: int = 0
    paused_campaigns: list[uuid.UUID] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class WorkerDeps:
    settings: Settings
    dialer: DialerSettings
    dnd: DndProvider
    voice: VoiceDialer


async def tick(
    sessionmaker: async_sessionmaker[AsyncSession], deps: WorkerDeps, now: datetime
) -> TickReport:
    report = TickReport()
    async with sessionmaker() as session:
        business_ids = list((await session.execute(_DUE, {"now": now})).scalars())
    for business_id in business_ids:
        async with sessionmaker() as session:
            await set_tenant(session, TenantContext(business_id=business_id))
            try:
                await run_business(session, business_id, deps, now, report)
            except Exception:
                await session.rollback()
                log.exception("dialer.business_failed", business_id=str(business_id))
        report.businesses += 1
    return report


async def run_business(
    session: AsyncSession,
    business_id: uuid.UUID,
    deps: WorkerDeps,
    now: datetime,
    report: TickReport,
) -> None:
    business = await session.get(Business, business_id)
    if business is None:
        return
    await reconcile(session, business_id, deps, now, report)
    await session.commit()

    config = await session.get(DialerConfig, business_id)
    channels = config.channels if config else deps.dialer.default_channels
    for _ in range(channels + 50):  # bounded: deferrals do not use a channel
        live = await session.scalar(
            select(func.count()).where(
                OutboundJob.business_id == business_id, OutboundJob.status == JobStatus.DIALING
            )
        )
        if (live or 0) >= channels:
            break
        job = await _next_job(session, business_id, now)
        if job is None:
            break
        await _process(session, business, job, deps, now, report)
        await session.commit()


async def _next_job(
    session: AsyncSession, business_id: uuid.UUID, now: datetime
) -> OutboundJob | None:
    running = select(Campaign.id).where(
        Campaign.business_id == business_id, Campaign.status == CampaignStatus.RUNNING
    )
    job: OutboundJob | None = await session.scalar(
        select(OutboundJob)
        .where(
            OutboundJob.business_id == business_id,
            OutboundJob.status == JobStatus.QUEUED,
            OutboundJob.not_before <= now,
            or_(OutboundJob.campaign_id.is_(None), OutboundJob.campaign_id.in_(running)),
        )
        .order_by(OutboundJob.not_before, OutboundJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return job


async def _process(
    session: AsyncSession,
    business: Business,
    job: OutboundJob,
    deps: WorkerDeps,
    now: datetime,
    report: TickReport,
) -> None:
    campaign = await session.get(Campaign, job.campaign_id) if job.campaign_id else None
    busy = await session.scalar(
        select(OutboundJob.id).where(
            OutboundJob.business_id == business.id,
            OutboundJob.phone_hash == job.phone_hash,
            OutboundJob.status == JobStatus.DIALING,
        )
    )
    if busy is not None:  # never two live calls to the same person
        job.not_before = now + SAME_PERSON_WAIT
        report.deferred += 1
        return
    if campaign is not None:
        start = next_calling_time(campaign, now)
        if start is None:
            await pause_campaign(session, campaign, "ended")
            report.paused_campaigns.append(campaign.id)
            return
        if start > now:
            job.not_before = start
            report.deferred += 1
            return

    try:
        phone = unseal(job.phone_enc, business.id)
    except ValueError:  # erased ("forget this customer") or sealed with another key
        await block_job(session, job, ["no_number"], now)
        report.blocked += 1
        return
    facts = await telephony.load_facts(
        session,
        business=business,
        phone_e164=phone,
        purpose=job.purpose,
        now=now,
        settings=deps.settings,
        dnd=deps.dnd,
        called_number_id=job.called_number_id,
        collection=is_collection(job.variables or {}),
    )
    result = evaluate(facts)
    telephony.log_decision(
        session,
        business_id=business.id,
        phone_e164=phone,
        purpose=job.purpose,
        result=result,
        now=now,
    )
    codes = [r.code for r in result.reasons]
    if result.decision == Decision.BLOCK:
        pause = next((BUSINESS_BLOCKS[c] for c in codes if c in BUSINESS_BLOCKS), None)
        if pause is not None and campaign is not None:
            job.not_before, job.reasons = now + BUSINESS_WAIT, codes
            await pause_campaign(session, campaign, pause)
            report.paused_campaigns.append(campaign.id)
            return
        await block_job(session, job, codes, now)
        report.blocked += 1
        return
    if result.decision == Decision.DEFER:
        job.not_before = result.defer_until or now + BUSINESS_WAIT
        job.reasons = codes
        report.deferred += 1
        return

    caller = result.caller
    if caller is None or caller.e164 is None:  # pragma: no cover - ALLOW always has a caller
        raise RuntimeError("compliance allowed a call without a caller id")
    number = await session.get(PhoneNumber, caller.id)
    if number is not None and number.spam_flag and campaign is not None:
        await pause_campaign(session, campaign, "spam_flagged")
        report.paused_campaigns.append(campaign.id)
        return

    attempt = OutboundAttempt(
        id=uuid.uuid4(),
        business_id=business.id,
        phone_hash=job.phone_hash,
        phone_number_id=caller.id,
        purpose=job.purpose,
        attempted_at=now,
    )
    session.add(attempt)
    await session.flush()  # no ORM relationship: insert the attempt before the job points at it
    job.status, job.dialed_at, job.attempt_id = JobStatus.DIALING, now, attempt.id
    job.attempts += 1
    job.reasons = []
    contact = (
        await session.get(CampaignContact, job.campaign_contact_id)
        if job.campaign_contact_id
        else None
    )
    if contact is not None:
        contact.status, contact.last_called_at = ContactStatus.QUEUED, now
        contact.attempts = job.attempts  # counts as called from the moment we dial
    await session.commit()  # the attempt counts against caps even if the carrier fails

    try:
        placed = await deps.voice.place(
            PlaceRequest(
                job_id=job.id,
                business_id=business.id,
                employee_id=job.employee_id,
                phone_e164=phone,
                purpose=job.purpose.value,
                caller_id=caller.e164,
                phone_number_id=caller.id,
                attempt_id=attempt.id,
                variables=dict(job.variables),
            )
        )
    except DialRejectedError as e:
        log.warning("dialer.rejected", job_id=str(job.id), spam=e.spam)
        attempt.outcome = AttemptOutcome.FAILED
        await finish_dial(session, job, AttemptOutcome.FAILED, now)
        report.finished += 1
        if campaign is not None:
            campaign.carrier_strikes += 1
            if e.spam or campaign.carrier_strikes >= deps.dialer.strike_limit:
                await pause_campaign(
                    session, campaign, "spam_flagged" if e.spam else "carrier_rejected"
                )
                report.paused_campaigns.append(campaign.id)
        return

    report.dialed += 1
    job.carrier_call_sid = attempt.carrier_call_sid = placed.call_sid[:64] or None
    if campaign is not None:
        campaign.carrier_strikes = 0
    if placed.outcome is not None:  # simulator: known at once
        attempt.outcome = placed.outcome
        await finish_dial(session, job, placed.outcome, now, result=placed.result)
        report.finished += 1


async def reconcile(
    session: AsyncSession,
    business_id: uuid.UUID,
    deps: WorkerDeps,
    now: datetime,
    report: TickReport,
) -> None:
    """Finish calls in flight once their outcome (and, if answered, the call record) is in."""
    timeout = timedelta(minutes=deps.dialer.dial_timeout_min)
    jobs = await session.scalars(
        select(OutboundJob)
        .where(OutboundJob.business_id == business_id, OutboundJob.status == JobStatus.DIALING)
        .with_for_update(skip_locked=True)
    )
    for job in list(jobs):
        attempt = await session.get(OutboundAttempt, job.attempt_id) if job.attempt_id else None
        outcome = attempt.outcome if attempt is not None else None
        age = now - (job.dialed_at or now)
        if outcome is None:
            if age < timeout:
                continue
            outcome = AttemptOutcome.NO_ANSWER
            if attempt is not None:
                attempt.outcome = outcome
        call = None
        if outcome == AttemptOutcome.ANSWERED:
            call = await answered_call(session, job)
            processed = call is not None and call.status == CallStatus.PROCESSED
            if not processed and age < timeout:
                continue  # still talking, or the summary is not ready yet
        await finish_dial(session, job, outcome, now, call=call)
        report.finished += 1
