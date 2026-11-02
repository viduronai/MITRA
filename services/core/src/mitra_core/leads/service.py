"""What happens when a lead arrives (CALL-03, AUTO-02 for the lead event, CMP-03 consent).

:func:`ingest` runs inside the request transaction (the caller binds the tenant and commits):

1. same portal lead id seen before -> answered as a duplicate, nothing new is stored;
2. same phone within the business's dedupe window -> a ``duplicate`` row, no second call;
3. contact upserted (hash only) and a purpose-tagged consent record written with the source
   and time (unless the form says consent was NOT given);
4. the source's routine decides: call or not, which employee, how soon;
5. the compliance gate is consulted to tell the owner what will happen: allowed -> queued,
   outside hours -> scheduled for the next window, refused -> blocked with the reason;
6. the call is queued on the shared dialer (which re-checks compliance before dialling), the
   optional WhatsApp heads-up is sent, and ``lead.created`` is emitted for webhooks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.service import upsert_contact
from mitra_core.config import Settings
from mitra_core.errors import AppError
from mitra_core.leads.adapters import LeadInput
from mitra_core.leads.calling import HeadsUp, LeadDialer
from mitra_core.leads.enums import LeadSourceKind, LeadStatus
from mitra_core.logging import get_logger
from mitra_core.models import Business, ConsentRecord, Employee, Lead, LeadIntake, LeadSource
from mitra_core.models.enums import EmployeeStatus, RoleTemplate
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.team.routines.events import fire_event
from mitra_core.telephony import service as telephony
from mitra_core.telephony.compliance import evaluate
from mitra_core.telephony.dnd import DndProvider
from mitra_core.telephony.enums import CallPurpose, ConsentScope, ConsentSource, Decision
from mitra_core.webhooks.enums import WebhookEvent
from mitra_core.webhooks.events import lead_created_payload
from mitra_core.webhooks.service import emit_event

log = get_logger(__name__)

MAX_VARIABLES = 20


@dataclass(frozen=True, slots=True)
class IntakeDeps:
    settings: Settings
    dialer: LeadDialer
    heads_up: HeadsUp
    dnd: DndProvider


@dataclass(frozen=True, slots=True)
class IntakeResult:
    lead: Lead
    duplicate: bool
    webhooks: int  # deliveries queued (send them after commit)


async def check_rate(
    session: AsyncSession, business_id: uuid.UUID, now: datetime, settings: Settings
) -> None:
    recent = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.business_id == business_id, Lead.received_at > now - timedelta(minutes=1))
    )
    if (recent or 0) >= settings.lead_intake_max_per_minute:
        raise AppError(
            429, "rate_limited", "Too many leads in the last minute", headers={"Retry-After": "60"}
        )


async def check_ip_rate(
    session: AsyncSession, business_id: uuid.UUID, ip_hash: str, now: datetime, limit: int
) -> None:
    recent = await session.scalar(
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.business_id == business_id,
            Lead.ip_hash == ip_hash,
            Lead.received_at > now - timedelta(hours=1),
        )
    )
    if (recent or 0) >= limit:
        raise AppError(
            429,
            "rate_limited",
            "Too many enquiries from this network",
            headers={"Retry-After": "3600"},
        )


async def source_for(
    session: AsyncSession, business_id: uuid.UUID, kind: LeadSourceKind
) -> LeadSource:
    """The business's source row for ``kind``, created (on, auto-call) on first use."""
    row = await session.scalar(
        select(LeadSource).where(LeadSource.business_id == business_id, LeadSource.kind == kind)
    )
    if row is None:
        row = LeadSource(business_id=business_id, kind=kind.value, config={})
        session.add(row)
        await session.flush()
    return row


async def pick_employee(
    session: AsyncSession, business_id: uuid.UUID, preferred: uuid.UUID | None
) -> Employee | None:
    """The source's chosen employee, else a Lead Caller, else any working employee."""
    active = (Employee.business_id == business_id, Employee.status != EmployeeStatus.PAUSED)
    if preferred is not None:
        chosen = await session.scalar(select(Employee).where(Employee.id == preferred, *active))
        if chosen is not None:
            return chosen
    return await session.scalar(
        select(Employee)
        .where(*active)
        .order_by(
            Employee.role_template != RoleTemplate.LEAD_CALLER, Employee.created_at, Employee.id
        )
        .limit(1)
    )


def call_variables(data: LeadInput) -> dict[str, str]:
    """Script variables for the employee: ``{lead_name}``, ``{city}``, ``{lead_source}``..."""
    out = {"lead_source": data.source.value}
    if data.name:
        out["lead_name"] = data.name
    if data.source_detail:
        out["lead_campaign"] = data.source_detail
    for key, value in data.fields.items():
        if len(out) >= MAX_VARIABLES:
            break
        name = key if key[:1].isalpha() else f"f_{key}"
        out.setdefault(name[:40], value)
    return out


async def _existing_external(
    session: AsyncSession, business_id: uuid.UUID, data: LeadInput
) -> Lead | None:
    if not data.external_id:
        return None
    return await session.scalar(
        select(Lead).where(
            Lead.business_id == business_id,
            Lead.source == data.source.value,
            Lead.external_id == data.external_id,
        )
    )


async def _recent_same_phone(
    session: AsyncSession, business_id: uuid.UUID, phone_hash: str, since: datetime
) -> Lead | None:
    return await session.scalar(
        select(Lead)
        .where(
            Lead.business_id == business_id,
            Lead.phone_hash == phone_hash,
            Lead.received_at > since,
            Lead.status != LeadStatus.DUPLICATE.value,
        )
        .order_by(Lead.received_at.desc())
        .limit(1)
    )


def _consent_note(data: LeadInput) -> str:
    note = f"Enquiry via {data.source.value}"
    if data.consent_text:
        note += f": {data.consent_text}"
    return note[:200]


async def ingest(
    session: AsyncSession,
    business: Business,
    intake: LeadIntake,
    source: LeadSource,
    data: LeadInput,
    *,
    now: datetime,
    deps: IntakeDeps,
    ip_hash: str | None = None,
) -> IntakeResult:
    bid = business.id
    seen = await _existing_external(session, bid, data)
    if seen is not None:
        return IntakeResult(seen, duplicate=True, webhooks=0)

    phone_hash = hash_phone(data.phone_e164)
    lead = Lead(
        id=uuid.uuid4(),
        business_id=bid,
        source_id=source.id,
        source=data.source.value,
        source_detail=data.source_detail,
        external_id=data.external_id,
        phone_hash=phone_hash,
        phone_last4=phone_last4(data.phone_e164),
        name=data.name,
        fields=data.fields,
        status=LeadStatus.QUEUED.value,
        reasons=[],
        ip_hash=ip_hash,
        received_at=now,
    )
    source.last_lead_at = now
    source.lead_count += 1

    since = now - timedelta(minutes=intake.dedupe_minutes)
    earlier = await _recent_same_phone(session, bid, phone_hash, since)
    if earlier is not None and intake.dedupe_minutes > 0:
        lead.status = LeadStatus.DUPLICATE.value
        lead.duplicate_of = earlier.id
        lead.contact_id = earlier.contact_id
        session.add(lead)
        await session.flush()
        return IntakeResult(lead, duplicate=True, webhooks=0)

    contact = await upsert_contact(session, bid, data.phone_e164)
    if data.name and not contact.name:
        contact.name = data.name
    lead.contact_id = contact.id
    if data.consent is False:
        lead.status = LeadStatus.NO_CONSENT.value
    else:
        consent = ConsentRecord(
            id=uuid.uuid4(),
            business_id=bid,
            phone_hash=phone_hash,
            scope=ConsentScope.SERVICE,
            source=ConsentSource.LEAD_FORM,
            note=_consent_note(data),
            captured_at=now,
        )
        session.add(consent)
        await session.flush()  # no ORM relationship: the consent row must exist first
        lead.consent_record_id = consent.id
    session.add(lead)
    await session.flush()

    if lead.status == LeadStatus.QUEUED.value:
        await _plan_call(session, business, source, lead, data, now=now, deps=deps)

    if lead.status != LeadStatus.NO_CONSENT.value:
        # Owner routines on new leads (WhatsApp only; the call itself is planned above).
        await fire_event(session, bid, "lead.created", contact_id=contact.id, now=now)
    rows = await emit_event(
        session, bid, WebhookEvent.LEAD_CREATED, lead_created_payload(lead), now=now
    )
    await session.flush()
    return IntakeResult(lead, duplicate=False, webhooks=len(rows))


async def _plan_call(
    session: AsyncSession,
    business: Business,
    source: LeadSource,
    lead: Lead,
    data: LeadInput,
    *,
    now: datetime,
    deps: IntakeDeps,
) -> None:
    if not (source.enabled and source.auto_call):
        lead.status = LeadStatus.NOT_CALLED.value
        return
    employee = await pick_employee(session, business.id, source.employee_id)
    if employee is None:
        lead.status = LeadStatus.NO_EMPLOYEE.value
        return
    lead.employee_id = employee.id
    call_at = now + timedelta(seconds=source.call_delay_seconds)
    facts = await telephony.load_facts(
        session,
        business=business,
        phone_e164=data.phone_e164,
        purpose=CallPurpose.SERVICE,
        now=call_at,
        settings=deps.settings,
        dnd=deps.dnd,
        timezone=business.timezone,
    )
    result = evaluate(facts)
    lead.reasons = [r.code for r in result.reasons]
    if result.decision == Decision.BLOCK:
        lead.status = LeadStatus.BLOCKED.value
        telephony.log_decision(
            session,
            business_id=business.id,
            phone_e164=data.phone_e164,
            purpose=CallPurpose.SERVICE,
            result=result,
            now=now,
        )
        return
    if result.decision == Decision.DEFER and result.defer_until is not None:
        lead.status = LeadStatus.SCHEDULED.value
        call_at = result.defer_until
    lead.call_at = call_at
    try:
        lead.call_job_id = await deps.dialer(
            session,
            business.id,
            employee_id=employee.id,
            phone_e164=data.phone_e164,
            variables=call_variables(data),
            not_before=call_at,
            dedupe_key=f"lead:{lead.id}",
        )
    except ValueError as exc:  # dialer input error (EnqueueError)
        log.warning("leads.enqueue_failed", lead_id=str(lead.id), error=str(exc)[:120])
        lead.status = LeadStatus.FAILED.value
        lead.reasons = ["dialer_refused"]
        return
    if source.heads_up:
        try:
            await deps.heads_up(
                session,
                business.id,
                phone_e164=data.phone_e164,
                name=data.name,
                employee_id=employee.id,
                call_at=call_at,
            )
        except Exception as exc:  # a heads-up must never stop the call
            log.warning("leads.heads_up_failed", lead_id=str(lead.id), exc_type=type(exc).__name__)
