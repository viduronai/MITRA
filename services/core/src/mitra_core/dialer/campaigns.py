"""Campaign lifecycle (CALL-15): create from a list, start (approval for big lists), pause,
resume, edit, extend, cancel; progress, buckets and ETA. Runs under the caller's RLS tenant.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.approvals import register_handler
from mitra_core.clock import utcnow
from mitra_core.dialer import hooks
from mitra_core.dialer.csvimport import ParsedList
from mitra_core.dialer.enums import CampaignStatus, ContactStatus, JobStatus, ResultBucket
from mitra_core.dialer.outcomes import maybe_complete
from mitra_core.dialer.queue import cancel_jobs, enqueue_call
from mitra_core.dialer.sealing import seal, unseal
from mitra_core.models import Approval, OutboundAttempt
from mitra_core.models.campaign import Campaign, CampaignContact, DialerConfig, OutboundJob
from mitra_core.pii import hash_phone, phone_last4

REMOVED_AT_APPROVAL = "removed_at_approval"
ACTIVE = (CampaignStatus.RUNNING, CampaignStatus.PAUSED, CampaignStatus.PENDING_APPROVAL)


class CampaignError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def recently_called(
    session: AsyncSession, business_id: uuid.UUID, hashes: list[str], days: int, now: datetime
) -> set[str]:
    if days <= 0 or not hashes:
        return set()
    rows = await session.scalars(
        select(OutboundAttempt.phone_hash).where(
            OutboundAttempt.business_id == business_id,
            OutboundAttempt.phone_hash.in_(hashes),
            OutboundAttempt.attempted_at > now - timedelta(days=days),
        )
    )
    return set(rows)


async def add_contacts(
    session: AsyncSession, campaign: Campaign, parsed: ParsedList, now: datetime
) -> tuple[int, int]:
    """Add the parsed people; returns (added, skipped). Already on this list = not added."""
    existing = set(
        await session.scalars(
            select(CampaignContact.phone_hash).where(CampaignContact.campaign_id == campaign.id)
        )
    )
    start = (
        await session.scalar(
            select(func.coalesce(func.max(CampaignContact.row_number), 0)).where(
                CampaignContact.campaign_id == campaign.id
            )
        )
        or 0
    )
    hashed = [(hash_phone(r.phone), r) for r in parsed.rows]
    recent = await recently_called(
        session, campaign.business_id, [h for h, _ in hashed], campaign.skip_recent_days, now
    )
    added = skipped = 0
    for phone_hash, row in hashed:
        if phone_hash in existing:
            continue
        existing.add(phone_hash)
        skip = phone_hash in recent
        contact = CampaignContact(
            id=uuid.uuid4(),
            business_id=campaign.business_id,
            campaign_id=campaign.id,
            row_number=start + row.row_number,
            phone_hash=phone_hash,
            phone_last4=phone_last4(row.phone),
            phone_enc=seal(row.phone),
            name=row.name,
            variables=row.variables,
            status=ContactStatus.SKIPPED if skip else ContactStatus.PENDING,
            reasons=["called_recently"] if skip else [],
        )
        session.add(contact)
        skipped += skip
        added += not skip
    await session.flush()
    if campaign.status == CampaignStatus.RUNNING:
        await _queue_pending(session, campaign, now)
    return added, skipped


async def _queue_pending(session: AsyncSession, campaign: Campaign, now: datetime) -> int:
    if campaign.employee_id is None:
        raise CampaignError("employee_required", "Choose which employee makes these calls")
    contacts = list(
        await session.scalars(
            select(CampaignContact)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == ContactStatus.PENDING,
            )
            .order_by(CampaignContact.row_number)
        )
    )
    for i, c in enumerate(contacts):
        await enqueue_call(
            session,
            campaign.business_id,
            employee_id=campaign.employee_id,
            phone_e164=unseal(c.phone_enc),
            purpose=campaign.purpose,
            variables=c.variables,
            source="campaign",
            # All due now; microsecond steps keep the upload's order in the queue.
            not_before=now - timedelta(microseconds=len(contacts) - i),
            campaign_id=campaign.id,
            campaign_contact_id=c.id,
            dedupe_key=f"campaign:{campaign.id}:{c.id}",
            retry_ladder=list(campaign.retry_ladder),
        )
        c.status = ContactStatus.QUEUED
    return len(contacts)


async def contact_count(session: AsyncSession, campaign_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count()).where(
                CampaignContact.campaign_id == campaign_id,
                CampaignContact.status != ContactStatus.SKIPPED,
            )
        )
        or 0
    )


async def start(
    session: AsyncSession,
    campaign: Campaign,
    now: datetime,
    *,
    user_id: uuid.UUID | None,
) -> Campaign:
    if campaign.status not in (CampaignStatus.DRAFT,):
        raise CampaignError("not_draft", "This campaign has already started")
    if campaign.employee_id is None:
        raise CampaignError("employee_required", "Choose which employee makes these calls")
    count = await contact_count(session, campaign.id)
    if count == 0:
        raise CampaignError("empty", "Add at least one person to call")
    if campaign.approval_id is None and await hooks.needs_list_approval(
        session, campaign.business_id, count
    ):
        campaign.approval_id = await hooks.request_approval(
            session,
            campaign.business_id,
            summary=f"Call a list of {count} people: '{campaign.name}' ({campaign.purpose})",
            payload={"campaign_id": str(campaign.id), "contacts": count, "name": campaign.name},
            requested_by=user_id,
        )
        campaign.status = CampaignStatus.PENDING_APPROVAL
        return campaign
    return await _run(session, campaign, now)


async def _run(session: AsyncSession, campaign: Campaign, now: datetime) -> Campaign:
    campaign.status, campaign.started_at = CampaignStatus.RUNNING, campaign.started_at or now
    campaign.pause_reason, campaign.carrier_strikes = None, 0
    await _queue_pending(session, campaign, now)
    await maybe_complete(session, campaign.id, now)
    return campaign


async def on_approval_decided(
    session: AsyncSession,
    business_id: uuid.UUID,
    campaign_id: uuid.UUID,
    approved: bool,
    now: datetime,
    *,
    approval_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> Campaign | None:
    """A ``list_call`` approval was decided: approved -> start calling; else back to draft.

    ``limit``: the approved number of people (APPR-06, the owner may edit it down). Only the
    first ``limit`` people still waiting (upload order) are called; the rest are skipped with
    reason ``removed_at_approval``.
    """
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.business_id == business_id)
    )
    if campaign is None or campaign.status != CampaignStatus.PENDING_APPROVAL:
        return campaign
    if approval_id is not None and campaign.approval_id != approval_id:
        return campaign  # the payload names a campaign this approval was not raised for
    if not approved:
        campaign.status, campaign.pause_reason = CampaignStatus.DRAFT, "approval_rejected"
        return campaign
    if limit is not None:
        await _trim_pending(session, campaign, max(limit, 0))
    return await _run(session, campaign, now)


async def _trim_pending(session: AsyncSession, campaign: Campaign, limit: int) -> int:
    pending = list(
        await session.scalars(
            select(CampaignContact)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == ContactStatus.PENDING,
            )
            .order_by(CampaignContact.row_number)
        )
    )
    for contact in pending[limit:]:
        contact.status, contact.reasons = ContactStatus.SKIPPED, [REMOVED_AT_APPROVAL]
    await session.flush()
    return max(len(pending) - limit, 0)


def pause(campaign: Campaign) -> Campaign:
    if campaign.status != CampaignStatus.RUNNING:
        raise CampaignError("not_running", "Only a running campaign can be paused")
    campaign.status, campaign.pause_reason = CampaignStatus.PAUSED, "owner"
    return campaign


async def resume(session: AsyncSession, campaign: Campaign, now: datetime) -> Campaign:
    if campaign.status != CampaignStatus.PAUSED:
        raise CampaignError("not_paused", "Only a paused campaign can be resumed")
    if campaign.ends_on is not None and campaign.ends_on < now.date():
        raise CampaignError("ended", "Move the last calling day forward first")
    # Jobs that waited out a business-level block retry now.
    await session.execute(
        update(OutboundJob)
        .where(
            OutboundJob.campaign_id == campaign.id,
            OutboundJob.status == JobStatus.QUEUED,
            OutboundJob.not_before > now,
            func.cardinality(OutboundJob.reasons) > 0,
        )
        .values(not_before=now)
    )
    return await _run(session, campaign, now)


async def cancel(session: AsyncSession, campaign: Campaign, now: datetime) -> Campaign:
    if campaign.status in (CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
        raise CampaignError("finished", "This campaign has already finished")
    await cancel_jobs(
        session, campaign.business_id, campaign_id=campaign.id, reason="campaign_cancelled"
    )
    campaign.status, campaign.completed_at = CampaignStatus.CANCELLED, now
    return campaign


async def set_retry_ladder(session: AsyncSession, campaign: Campaign, ladder: list[int]) -> None:
    campaign.retry_ladder = ladder
    await session.execute(
        update(OutboundJob)
        .where(OutboundJob.campaign_id == campaign.id, OutboundJob.status == JobStatus.QUEUED)
        .values(retry_ladder=ladder)
    )


async def channels_for(session: AsyncSession, business_id: uuid.UUID, default: int) -> int:
    config = await session.get(DialerConfig, business_id)
    return config.channels if config else default


@dataclass(frozen=True, slots=True)
class Progress:
    total: int
    skipped: int
    remaining: int  # pending + queued
    dialing: int
    buckets: dict[str, int]
    reasons: dict[str, int]
    eta_minutes: int | None


async def progress(session: AsyncSession, campaign: Campaign, channels: int) -> Progress:
    rows = (
        await session.execute(
            select(CampaignContact.status, CampaignContact.bucket, func.count())
            .where(CampaignContact.campaign_id == campaign.id)
            .group_by(CampaignContact.status, CampaignContact.bucket)
        )
    ).all()
    total = skipped = remaining = 0
    buckets = {b.value: 0 for b in ResultBucket}
    for status, bucket, n in rows:
        total += n
        if status == ContactStatus.SKIPPED:
            skipped += n
        elif status in (ContactStatus.PENDING, ContactStatus.QUEUED):
            remaining += n
        if bucket is not None:
            buckets[bucket.value] += n
    reason_rows = (
        await session.execute(
            select(func.unnest(CampaignContact.reasons), func.count())
            .where(CampaignContact.campaign_id == campaign.id)
            .group_by(func.unnest(CampaignContact.reasons))
        )
    ).all()
    dialing = await session.scalar(
        select(func.count()).where(
            OutboundJob.campaign_id == campaign.id, OutboundJob.status == JobStatus.DIALING
        )
    )
    eta = None
    if remaining and campaign.status != CampaignStatus.CANCELLED:
        eta = math.ceil(remaining * campaign.avg_call_seconds / max(channels, 1) / 60)
    return Progress(
        total=total,
        skipped=skipped,
        remaining=remaining,
        dialing=int(dialing or 0),
        buckets=buckets,
        reasons={str(code): int(n) for code, n in reason_rows},
        eta_minutes=eta,
    )


async def _on_list_call(session: AsyncSession, approval: Approval) -> None:
    """``approvals`` handler (registered at import, so whenever the API app is loaded).

    Runs exactly what was approved: ``payload["contacts"]`` caps how many people are called.
    A malformed edited payload raises, so approvals records ``apply_error`` and nothing is dialled.
    """
    payload = approval.payload or {}
    raw = payload.get("campaign_id")
    if not raw:
        return
    limit = None
    if approval.status == "approved" and "contacts" in payload:
        value = payload["contacts"]
        if isinstance(value, bool) or not isinstance(value, int | str) or not str(value).isdigit():
            raise ValueError("approved 'contacts' must be a whole number")
        limit = int(value)
    await on_approval_decided(
        session,
        approval.business_id,
        uuid.UUID(str(raw)),
        approval.status == "approved",
        approval.used_at or approval.decided_at or utcnow(),
        approval_id=approval.id,
        limit=limit,
    )


register_handler(hooks.LIST_CALL, _on_list_call)
