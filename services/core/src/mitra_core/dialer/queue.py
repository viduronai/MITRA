"""The dialer queue's public API: ``enqueue_call`` (campaigns, callbacks, lead follow-ups).

Callers pass their own session with the business bound as the RLS tenant (``set_tenant``); this
module only adds/flushes rows and never commits, so enqueuing joins the caller's transaction.
The worker (``dialer.worker``) runs ``compliance.check`` right before each dial, so enqueuing a
call never means it will be placed: consent, opt-out, DND, hours and caps are decided then.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.dialer.enums import ACTIVE_JOB_STATUSES, JobStatus
from mitra_core.dialer.sealing import seal
from mitra_core.models.campaign import OutboundJob
from mitra_core.phones import remember_phone
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.telephony.enums import CallPurpose

E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
VARIABLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_VARIABLES = 20
MAX_VARIABLE_CHARS = 200
ACTIVE_PREDICATE = "status IN ('queued', 'dialing')"
DEFAULT_LADDER = (30, 120, 1440)  # minutes: 30 min -> 2 h -> next day (CALL-04)


class EnqueueError(ValueError):
    """Bad input to ``enqueue_call`` (the message never contains the phone number)."""


def is_collection(variables: dict[str, str]) -> bool:
    """A payment-collection call (routine goal ``collect_payment`` or a payment reminder):
    lenders may make these only in RBI hours (compliance gate)."""
    return variables.get("task") == "collect_payment" or bool(variables.get("payment_amount"))


def clean_variables(variables: dict[str, str]) -> dict[str, str]:
    """Script variables for the employee's prompt, e.g. ``{"lead_name": "Ravi"}``."""
    if len(variables) > MAX_VARIABLES:
        raise EnqueueError(f"at most {MAX_VARIABLES} variables")
    out: dict[str, str] = {}
    for key, value in variables.items():
        if not VARIABLE_NAME.fullmatch(key):
            raise EnqueueError(f"invalid variable name: {key[:40]!r}")
        out[key] = str(value).strip()[:MAX_VARIABLE_CHARS]
    return out


async def enqueue_call(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    employee_id: uuid.UUID,
    phone_e164: str,
    purpose: CallPurpose | str,
    variables: dict[str, str],
    source: str,
    not_before: datetime | None = None,
    campaign_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    campaign_contact_id: uuid.UUID | None = None,
    retry_ladder: list[int] | None = None,
    called_number_id: uuid.UUID | None = None,
) -> OutboundJob:
    """Queue one outbound call; returns the job (flushed, not committed).

    ``dedupe_key``: while a queued/dialing job with the same key exists for this business, that
    job is returned instead of adding a second one (e.g. ``f"lead:{lead_id}:followup"``).
    ``not_before`` must be timezone-aware; default = now. ``source`` names the caller
    ("campaign", "callback", "lead_followup", "team", ...).
    """
    if not E164.fullmatch(phone_e164):
        raise EnqueueError("phone must be E.164, e.g. +919876543210")
    if not_before is not None and not_before.tzinfo is None:
        raise EnqueueError("not_before must be timezone-aware")
    if not source or len(source) > 32:
        raise EnqueueError("source must be 1-32 characters")
    if dedupe_key is not None and not 0 < len(dedupe_key) <= 120:
        raise EnqueueError("dedupe_key must be 1-120 characters")
    ladder = list(DEFAULT_LADDER) if retry_ladder is None else list(retry_ladder)
    if len(ladder) > 6 or any(not 1 <= m <= 7 * 24 * 60 for m in ladder):
        raise EnqueueError("retry ladder: at most 6 steps of 1 minute to 7 days")

    values = {
        "id": uuid.uuid4(),
        "business_id": business_id,
        "employee_id": employee_id,
        "campaign_id": campaign_id,
        "campaign_contact_id": campaign_contact_id,
        "phone_hash": hash_phone(phone_e164),
        "phone_last4": phone_last4(phone_e164),
        "phone_enc": seal(phone_e164, business_id),
        "purpose": CallPurpose(purpose),
        "variables": clean_variables(variables),
        "source": source,
        "dedupe_key": dedupe_key,
        "status": JobStatus.QUEUED,
        "not_before": not_before or utcnow(),
        "retry_ladder": ladder,
        "called_number_id": called_number_id,
    }
    # A known customer keeps the number too (missed callers, lead follow-ups, reminders).
    await remember_phone(session, business_id, hash_phone(phone_e164), phone_e164)
    stmt = insert(OutboundJob).values(**values)
    if dedupe_key is not None:
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["business_id", "dedupe_key"],
            index_where=text(ACTIVE_PREDICATE),  # literal: must match the partial index
        )
    inserted = await session.scalar(stmt.returning(OutboundJob.id))
    job_id = inserted
    if job_id is None:  # dedupe hit: the active job with this key
        job_id = await session.scalar(
            select(OutboundJob.id).where(
                OutboundJob.business_id == business_id,
                OutboundJob.dedupe_key == dedupe_key,
                OutboundJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        )
    job = await session.get(OutboundJob, job_id, populate_existing=True)
    if job is None:  # pragma: no cover - RLS tenant not bound to business_id
        raise EnqueueError("job not visible: bind the business as the RLS tenant first")
    return job


async def cancel_jobs(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    dedupe_key: str | None = None,
    campaign_id: uuid.UUID | None = None,
    reason: str = "cancelled",
) -> int:
    """Cancel QUEUED jobs (a dialing call is left to finish). Returns how many were cancelled."""
    if dedupe_key is None and campaign_id is None:
        raise EnqueueError("give a dedupe_key or a campaign_id")
    stmt = update(OutboundJob).where(
        OutboundJob.business_id == business_id, OutboundJob.status == JobStatus.QUEUED
    )
    if dedupe_key is not None:
        stmt = stmt.where(OutboundJob.dedupe_key == dedupe_key)
    if campaign_id is not None:
        stmt = stmt.where(OutboundJob.campaign_id == campaign_id)
    result = await session.execute(
        stmt.values(status=JobStatus.CANCELLED, reasons=[reason], finished_at=utcnow())
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
