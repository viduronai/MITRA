"""Database side of telephony: load compliance facts, log decisions, route inbound numbers,
record attempts and run the number-health monitor. Every query runs under the RLS tenant the
caller bound (``set_tenant``); queries also filter on ``business_id`` explicitly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.billing import service as billing
from mitra_core.config import Settings
from mitra_core.models import (
    Business,
    ComplianceDecision,
    ConsentRecord,
    Contact,
    DndCache,
    Employee,
    OptOut,
    OutboundAttempt,
    PhoneNumber,
)
from mitra_core.models.enums import EmployeeStatus, Industry, RoleTemplate
from mitra_core.pii import hash_phone
from mitra_core.telephony import health as health_monitor
from mitra_core.telephony.compliance import (
    ComplianceFacts,
    ComplianceResult,
    NumberInfo,
)
from mitra_core.telephony.dnd import CACHE_HOURS, DndProvider
from mitra_core.telephony.enums import (
    AttemptOutcome,
    CallPurpose,
    ConsentScope,
    ConsentSource,
    DndStatus,
    NumberHealth,
)
from mitra_core.tenancy import TenantContext, set_tenant

# Sectors whose service calls must come from 1600/1601 (TRAI, phased). None of today's
# industries is in a 1601 phase yet (08 section 1); add them here as phases roll out.
MANDATED_INDUSTRIES: frozenset[Industry] = frozenset()

_NUMBER_LOOKUP = text("SELECT internal_number_business(:e164)")
_NUMBERED = text("SELECT internal_numbered_businesses()")


def display_number(e164: str | None, *, mobile: bool = False) -> str | None:
    """Indian formatting for the UI: +914041234567 -> 040 4123 4567, mobiles as 98765 43210."""
    if not e164:
        return None
    if not e164.startswith("+91") or len(e164) != 13:
        return e164
    n = e164[3:]
    if mobile:
        return f"{n[:5]} {n[5:]}"
    # 2-digit metro codes (Hyderabad 40, Bengaluru 80, ...) else 3-digit (Vijayawada 866).
    code = 2 if n[:2] in {"11", "20", "22", "33", "40", "44", "79", "80"} else 3
    rest = n[code:]
    return f"0{n[:code]} {rest[: len(rest) - 4]} {rest[-4:]}"


def number_info(n: PhoneNumber) -> NumberInfo:
    return NumberInfo(
        id=n.id,
        e164=n.e164,
        type=n.type,
        kyc_status=n.kyc_status,
        health=n.health,
        outbound_enabled=n.outbound_enabled,
        truecaller_status=n.truecaller_status,
        cnap_status=n.cnap_status,
    )


async def dnd_status(
    session: AsyncSession,
    business_id: uuid.UUID,
    phone_e164: str,
    phone_hash: str,
    now: datetime,
    provider: DndProvider,
) -> DndStatus:
    """Cached for at most 24 h; UNKNOWN results are never cached (retry next time)."""
    cached = await session.get(DndCache, (business_id, phone_hash))
    if cached is not None and now - cached.checked_at < timedelta(hours=CACHE_HOURS):
        return cached.status
    status = await provider.lookup(phone_e164)
    if status != DndStatus.UNKNOWN:
        if cached is None:
            session.add(
                DndCache(
                    business_id=business_id, phone_hash=phone_hash, status=status, checked_at=now
                )
            )
        else:
            cached.status, cached.checked_at = status, now
    return status


async def load_facts(
    session: AsyncSession,
    *,
    business: Business,
    phone_e164: str,
    purpose: CallPurpose,
    now: datetime,
    settings: Settings,
    dnd: DndProvider,
    number_id: uuid.UUID | None = None,
    called_number_id: uuid.UUID | None = None,
    dlt_template_id: str | None = None,
    timezone: str = "Asia/Kolkata",
    collection: bool = False,
) -> ComplianceFacts:
    bid = business.id
    phone_hash = hash_phone(phone_e164)
    consents = await session.scalars(
        select(ConsentRecord.scope).where(
            ConsentRecord.business_id == bid,
            ConsentRecord.phone_hash == phone_hash,
            ConsentRecord.revoked_at.is_(None),
            # Portal enquiries are consent for a limited time (lead consent policy, 0006).
            or_(ConsentRecord.expires_at.is_(None), ConsentRecord.expires_at > now),
        )
    )
    opt_outs = list(
        await session.scalars(
            select(OptOut.purpose).where(OptOut.business_id == bid, OptOut.phone_hash == phone_hash)
        )
    )
    attempts = await session.scalars(
        select(OutboundAttempt.attempted_at).where(
            OutboundAttempt.business_id == bid,
            OutboundAttempt.phone_hash == phone_hash,
            OutboundAttempt.attempted_at > now - timedelta(days=7),
        )
    )
    numbers = await session.scalars(select(PhoneNumber).where(PhoneNumber.business_id == bid))
    status = None
    if purpose == CallPurpose.PROMOTIONAL:
        status = await dnd_status(session, bid, phone_e164, phone_hash, now, dnd)
    pause = billing.status_of(await billing.lock_wallet(session, bid, now)).pause_reason
    lender = False
    if collection:  # payments module: lenders' collection calls keep RBI hours
        from mitra_core.models import CollectionSettings

        lender = bool(
            await session.scalar(
                select(CollectionSettings.is_lender).where(CollectionSettings.business_id == bid)
            )
        )
    return ComplianceFacts(
        purpose=purpose,
        now=now,
        consents=frozenset(consents),
        opted_out_all=None in opt_outs,
        opted_out_purposes=frozenset(p for p in opt_outs if p is not None),
        dnd=status,
        attempts=list(attempts),
        numbers=[number_info(n) for n in numbers],
        called_number_id=called_number_id,
        requested_number_id=number_id,
        timezone=timezone,
        promotional_enabled=settings.promotional_calling_enabled,
        dlt_enforced=settings.dlt_enforced,
        dlt_template_id=dlt_template_id,
        sector_mandated=business.industry in MANDATED_INDUSTRIES,
        wallet_pause=pause.value if pause else None,
        collection=collection,
        lender=lender,
    )


def log_decision(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    phone_e164: str,
    purpose: CallPurpose,
    result: ComplianceResult,
    now: datetime,
) -> ComplianceDecision:
    row = ComplianceDecision(
        id=uuid.uuid4(),
        business_id=business_id,
        phone_hash=hash_phone(phone_e164),
        purpose=purpose,
        decision=result.decision,
        reasons=[r.code for r in result.reasons],
        phone_number_id=result.caller.id if result.caller else None,
        defer_until=result.defer_until,
        created_at=now,
    )
    session.add(row)
    return row


# ---- inbound routing ---------------------------------------------------------------------------


async def business_for_number(session: AsyncSession, e164: str) -> uuid.UUID | None:
    """Owning business of a live number (SECURITY DEFINER lookup, migration 0004_telephony)."""
    found: uuid.UUID | None = (
        await session.execute(_NUMBER_LOOKUP, {"e164": e164})
    ).scalar_one_or_none()
    return found


async def answering_employee(
    session: AsyncSession, business_id: uuid.UUID, number: PhoneNumber
) -> Employee | None:
    """The number's routed employee, else the business's receptionist, else its first employee."""
    if number.employee_id:
        routed = await session.scalar(
            select(Employee).where(
                Employee.id == number.employee_id, Employee.business_id == business_id
            )
        )
        if routed is not None:
            return routed
    return await session.scalar(
        select(Employee)
        .where(Employee.business_id == business_id, Employee.status != EmployeeStatus.PAUSED)
        .order_by(
            (Employee.role_template != RoleTemplate.RECEPTIONIST),
            Employee.created_at,
            Employee.id,
        )
        .limit(1)
    )


async def note_inbound_relationship(
    session: AsyncSession, business_id: uuid.UUID, caller_e164: str
) -> bool:
    """The caller contacted the business: an existing relationship for service callbacks
    (08 section 3 rule 1). Returns whether the caller was already a known contact."""
    phone_hash = hash_phone(caller_e164)
    known = await session.scalar(
        select(Contact.id).where(
            Contact.business_id == business_id, Contact.phone_hash == phone_hash
        )
    )
    has_consent = await session.scalar(
        select(ConsentRecord.id)
        .where(
            ConsentRecord.business_id == business_id,
            ConsentRecord.phone_hash == phone_hash,
            ConsentRecord.scope == ConsentScope.SERVICE,
            ConsentRecord.revoked_at.is_(None),
            or_(ConsentRecord.expires_at.is_(None), ConsentRecord.expires_at > func.now()),
        )
        .limit(1)
    )
    if has_consent is None:
        session.add(
            ConsentRecord(
                business_id=business_id,
                phone_hash=phone_hash,
                scope=ConsentScope.SERVICE,
                source=ConsentSource.INBOUND_CALL,
                note="Called the business",
            )
        )
    return known is not None


# ---- health monitor ----------------------------------------------------------------------------


async def _counts(
    session: AsyncSession, number_id: uuid.UUID, start: datetime, end: datetime
) -> tuple[int, int]:
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(OutboundAttempt.outcome == AttemptOutcome.ANSWERED),
            ).where(
                and_(
                    OutboundAttempt.phone_number_id == number_id,
                    OutboundAttempt.outcome.is_not(None),
                    OutboundAttempt.attempted_at >= start,
                    OutboundAttempt.attempted_at < end,
                )
            )
        )
    ).one()
    return int(row[0]), int(row[1])


async def assess_number(
    session: AsyncSession, number: PhoneNumber, now: datetime
) -> health_monitor.HealthAssessment:
    since = number.health_since
    week = now - timedelta(days=7)
    start = max(week, since) if since else week
    attempts, answered = await _counts(session, number.id, start, now)
    prev_attempts = prev_answered = 0
    if since is None or since <= week - timedelta(days=7):
        prev_attempts, prev_answered = await _counts(
            session, number.id, week - timedelta(days=7), week
        )
    return health_monitor.assess(
        health_monitor.HealthInputs(
            attempts_7d=attempts,
            answered_7d=answered,
            attempts_prev_7d=prev_attempts,
            answered_prev_7d=prev_answered,
            spam_flag=number.spam_flag,
        )
    )


def apply_assessment(
    number: PhoneNumber, result: health_monitor.HealthAssessment, now: datetime
) -> NumberHealth:
    previous = number.health
    number.health = result.health
    number.health_reasons = result.reasons
    number.answer_rate_7d = result.answer_rate_7d
    number.health_checked_at = now
    if result.health == NumberHealth.PAUSED:
        number.outbound_enabled = False  # pause outbound; inbound keeps working
    return previous


async def numbered_businesses(session: AsyncSession) -> list[uuid.UUID]:
    return list((await session.execute(_NUMBERED)).scalars())


async def run_health_for_business(
    session: AsyncSession, business_id: uuid.UUID, now: datetime
) -> list[tuple[PhoneNumber, NumberHealth]]:
    await set_tenant(session, TenantContext(business_id=business_id))
    numbers = await session.scalars(
        select(PhoneNumber).where(PhoneNumber.business_id == business_id).order_by(PhoneNumber.id)
    )
    changed: list[tuple[PhoneNumber, NumberHealth]] = []
    for number in numbers:
        if number.e164 is None:
            continue
        previous = apply_assessment(number, await assess_number(session, number, now), now)
        if previous != number.health:
            changed.append((number, previous))
    await session.flush()
    return changed
