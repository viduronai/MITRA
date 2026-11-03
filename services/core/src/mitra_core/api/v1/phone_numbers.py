"""Phone numbers: the "Trusted Caller ID" card (07 section 3.7) and onboarding step 6 (Go live).

With ``MITRA_TELEPHONY_CARRIER=sim`` (default) nothing is bought or dialled: a requested number
waits in ``pending_kyc`` until documents are submitted, then is approved at once with a made-up
number; forwarding tests pass instantly, flagged ``simulated``. Once the
carrier account is approved, ops provisions the number and reports it through
``PATCH /internal/v1/telephony/numbers/{id}`` (KYC approved + e164).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.errors import AppError, not_found
from mitra_core.models import Business, ComplianceDecision, Employee, PhoneNumber
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.telephony import (
    ComplianceSummaryOut,
    ForwardingOut,
    ForwardingTestOut,
    KycSubmitIn,
    NumberRequestIn,
    OperatorCodes,
    PhoneNumberList,
    PhoneNumberOut,
    PhoneNumberPatch,
)
from mitra_core.security import Tenant, get_tenant_session, require_business, require_role
from mitra_core.telephony import forwarding
from mitra_core.telephony.compliance import owner_summary
from mitra_core.telephony.enums import (
    Carrier,
    Decision,
    KycStatus,
    NumberHealth,
    NumberType,
    VerificationStatus,
)
from mitra_core.telephony.health import REMEDIATION
from mitra_core.telephony.service import display_number, number_went_live

router = APIRouter(prefix="/phone-numbers", tags=["phone numbers"])
compliance_router = APIRouter(prefix="/compliance", tags=["compliance"])

MAX_NUMBERS = 10
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)


def _out(n: PhoneNumber) -> PhoneNumberOut:
    return PhoneNumberOut(
        id=n.id,
        e164=n.e164,
        display=display_number(n.e164, mobile=n.type == NumberType.MOBILE_VIRTUAL),
        type=n.type,
        carrier=n.carrier,
        city=n.city,
        label=n.label,
        employee_id=n.employee_id,
        kyc_status=n.kyc_status,
        display_name=n.display_name,
        truecaller_status=n.truecaller_status,
        cnap_status=n.cnap_status,
        answer_rate_7d=n.answer_rate_7d,
        health=n.health,
        health_reasons=list(n.health_reasons),
        remediation=REMEDIATION[n.health],
        outbound_enabled=n.outbound_enabled,
        spam_flag=n.spam_flag,
        forwarding_tested_at=n.forwarding_tested_at,
        created_at=n.created_at,
        missed_call=n.missed_call,
    )


async def _get(session: AsyncSession, tenant: Tenant, number_id: uuid.UUID) -> PhoneNumber:
    number = await session.scalar(
        select(PhoneNumber).where(
            PhoneNumber.id == number_id, PhoneNumber.business_id == tenant.business_id
        )
    )
    if number is None:
        raise not_found("Phone number")
    return number


async def _check_employee(session: AsyncSession, tenant: Tenant, employee_id: uuid.UUID) -> None:
    found = await session.scalar(
        select(Employee.id).where(
            Employee.id == employee_id, Employee.business_id == tenant.business_id
        )
    )
    if found is None:
        raise not_found("Employee")


@router.get("", response_model=PhoneNumberList, summary="Numbers with KYC, trust and health")
async def list_numbers(
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> PhoneNumberList:
    business = await session.get(Business, tenant.business_id)
    if business is None:
        raise not_found("Business")
    numbers = await session.scalars(
        select(PhoneNumber)
        .where(PhoneNumber.business_id == tenant.business_id)
        .order_by(PhoneNumber.created_at, PhoneNumber.id)
    )
    return PhoneNumberList(
        items=[_out(n) for n in numbers],
        carrier=settings.telephony_carrier,
        simulated=settings.telephony_carrier == "sim",
        business_name=business.name,
    )


@router.post(
    "/requests",
    status_code=status.HTTP_201_CREATED,
    response_model=PhoneNumberOut,
    summary="Request a new local business number (waits for KYC)",
)
async def request_number(
    body: NumberRequestIn,
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> PhoneNumberOut:
    count = await session.scalar(
        select(func.count()).where(PhoneNumber.business_id == tenant.business_id)
    )
    if (count or 0) >= MAX_NUMBERS:
        raise AppError(409, "too_many_numbers", f"A business can have up to {MAX_NUMBERS} numbers")
    if body.employee_id:
        await _check_employee(session, tenant, body.employee_id)
    business = await session.get(Business, tenant.business_id)
    number = PhoneNumber(
        business_id=tenant.business_id,
        employee_id=body.employee_id,
        type=NumberType(body.type),
        carrier=Carrier(settings.telephony_carrier),
        city=body.city,
        label=body.label,
        kyc_status=KycStatus.PENDING_KYC,
        display_name=body.display_name or (business.name[:60] if business else None),
    )
    session.add(number)
    await session.flush()
    await session.refresh(number)
    out = _out(number)
    await session.commit()
    return out


@router.patch("/{number_id}", response_model=PhoneNumberOut, summary="Route or rename a number")
async def update_number(
    number_id: uuid.UUID,
    body: PhoneNumberPatch,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> PhoneNumberOut:
    number = await _get(session, tenant, number_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("employee_id"):
        await _check_employee(session, tenant, changes["employee_id"])
    if "display_name" in changes and changes["display_name"] != number.display_name:
        # A new name must be verified again before networks / Truecaller show it.
        for field in ("truecaller_status", "cnap_status"):
            if getattr(number, field) == VerificationStatus.VERIFIED:
                setattr(number, field, VerificationStatus.PENDING)
    for field, value in changes.items():
        setattr(number, field, value)
    await session.flush()
    await session.refresh(number)
    out = _out(number)
    await session.commit()
    return out


@router.post("/{number_id}/kyc", response_model=PhoneNumberOut, summary="Submit KYC (placeholder)")
async def submit_kyc(
    number_id: uuid.UUID,
    body: KycSubmitIn,
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> PhoneNumberOut:
    number = await _get(session, tenant, number_id)
    if number.kyc_status not in (KycStatus.PENDING_KYC, KycStatus.REJECTED):
        raise AppError(409, "kyc_not_pending", "KYC was already submitted for this number")
    # TODO(kyc): store the document (encrypted, India region) and send it to the carrier.
    number.kyc_document = {
        "document_type": body.document_type,
        "file_name": body.file_name,
        "submitted_at": clock().isoformat(),
    }
    number.kyc_status = KycStatus.SUBMITTED
    if number.carrier == Carrier.SIM:
        # The simulator approves at once with a made-up local number (it never dials anyone),
        # so a demo business can run calls and campaigns end to end.
        number.kyc_status = KycStatus.APPROVED
        number.e164 = number.e164 or f"+9140{number.id.int % 10**8:08d}"
        await number_went_live(session, tenant.business_id)
    await session.flush()
    await session.refresh(number)
    out = _out(number)
    await session.commit()
    return out


@router.post(
    "/{number_id}/caller-name",
    response_model=PhoneNumberOut,
    summary='"Show my name when calling": start Truecaller + CNAP verification',
)
async def start_caller_name(
    number_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> PhoneNumberOut:
    number = await _get(session, tenant, number_id)
    if not number.display_name:
        raise AppError(422, "display_name_required", "Set the name to show first")
    # TODO(verification): submit to Truecaller for Business and the carrier's CNAP registration.
    for field in ("truecaller_status", "cnap_status"):
        if getattr(number, field) in (VerificationStatus.NOT_STARTED, VerificationStatus.REJECTED):
            setattr(number, field, VerificationStatus.PENDING)
    await session.flush()
    await session.refresh(number)
    out = _out(number)
    await session.commit()
    return out


@router.get("/{number_id}/forwarding", response_model=ForwardingOut, summary="Forwarding codes")
async def forwarding_codes(
    number_id: uuid.UUID,
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> ForwardingOut:
    number = await _get(session, tenant, number_id)
    if not number.e164:
        raise AppError(409, "number_not_live", "This number is not live yet")
    mobile = number.type == NumberType.MOBILE_VIRTUAL
    return ForwardingOut(
        phone_number_id=number.id,
        target=forwarding.dial_form(number.e164, mobile=mobile),
        operators=[
            OperatorCodes.model_validate(c, from_attributes=True)
            for c in forwarding.codes_for(number.e164, mobile=mobile)
        ],
    )


@router.post(
    "/{number_id}/forwarding-test", response_model=ForwardingTestOut, summary="Test forwarding"
)
async def run_forwarding_test(
    number_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> ForwardingTestOut:
    number = await _get(session, tenant, number_id)
    if not number.e164:
        raise AppError(409, "number_not_live", "This number is not live yet")
    if settings.telephony_carrier != "sim":
        # TODO(carrier): ring the owner's phone, let it go unanswered and watch for the
        # forwarded call to arrive on this number; the result lands on forwarding_tested_at.
        return ForwardingTestOut(
            status="pending",
            simulated=False,
            tested_at=number.forwarding_tested_at,
            message="We'll ring your phone now. Don't answer; it should forward to Mitra.",
        )
    number.forwarding_tested_at = clock()
    tested_at = number.forwarding_tested_at
    await session.commit()
    return ForwardingTestOut(
        status="passed",
        simulated=True,
        tested_at=tested_at,
        message="Simulated: no call was placed.",
    )


@router.post("/{number_id}/resume", response_model=PhoneNumberOut, summary="Resume a paused number")
async def resume_number(
    number_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> PhoneNumberOut:
    number = await _get(session, tenant, number_id)
    if number.spam_flag:
        raise AppError(409, "spam_label_active", "Wait for the spam label appeal to finish first")
    if number.health == NumberHealth.PAUSED or not number.outbound_enabled:
        # Fresh window: the monitor ignores attempts made before the resume.
        number.health, number.health_reasons = NumberHealth.WATCH, ["Resumed by owner"]
        number.outbound_enabled, number.health_since = True, clock()
    await session.flush()
    await session.refresh(number)
    out = _out(number)
    await session.commit()
    return out


@compliance_router.get(
    "/summary", response_model=ComplianceSummaryOut, summary="Why calls were skipped, in words"
)
async def compliance_summary(
    days: int = Query(default=7, ge=1, le=90),
    clock: Clock = Depends(get_clock),
    tenant: Tenant = Depends(require_business),
    session: AsyncSession = Depends(get_tenant_session),
) -> ComplianceSummaryOut:
    since = clock() - timedelta(days=days)
    rows = await session.execute(
        select(ComplianceDecision.decision, ComplianceDecision.reasons).where(
            ComplianceDecision.business_id == tenant.business_id,
            ComplianceDecision.created_at >= since,
        )
    )
    counts: dict[str, int] = {}
    allowed = 0
    for decision, reasons in rows:
        if decision == Decision.ALLOW:
            allowed += 1
            continue
        # One person counts once, under the first (most important) reason.
        if reasons:
            counts[reasons[0]] = counts.get(reasons[0], 0) + 1
    return ComplianceSummaryOut(
        days=days, allowed=allowed, counts=counts, lines=owner_summary(counts)
    )
