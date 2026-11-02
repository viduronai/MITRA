"""Telephony & compliance API schemas (public Connect / Go-live, and the internal voice API)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from mitra_core.schemas.common import City, E164Phone, RequestModel, ResponseModel
from mitra_core.telephony.enums import (
    AttemptOutcome,
    CallPurpose,
    Carrier,
    ConsentScope,
    ConsentSource,
    Decision,
    KycStatus,
    NumberHealth,
    NumberType,
    OptOutSource,
    VerificationStatus,
)

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
CarrierSid = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,64}$")]
DltTemplateId = Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z-]{1,40}$")]

# ---- public: Connect / Go-live ---------------------------------------------------------------


class PhoneNumberOut(ResponseModel):
    id: uuid.UUID
    e164: str | None
    display: str | None  # "040 4123 4567"
    type: NumberType
    carrier: Carrier
    city: str | None
    label: str | None
    employee_id: uuid.UUID | None
    kyc_status: KycStatus
    display_name: str | None
    truecaller_status: VerificationStatus
    cnap_status: VerificationStatus
    answer_rate_7d: float | None
    health: NumberHealth
    health_reasons: list[str]
    remediation: list[str]
    outbound_enabled: bool
    spam_flag: bool
    forwarding_tested_at: datetime | None
    created_at: datetime


class PhoneNumberList(ResponseModel):
    items: list[PhoneNumberOut]
    carrier: Literal["sim", "exotel", "plivo"]
    # True while numbers come from the local carrier simulator (nothing is bought or dialled).
    simulated: bool
    business_name: str


class NumberRequestIn(RequestModel):
    type: Literal["local", "mobile_virtual"] = "local"
    city: City
    employee_id: uuid.UUID | None = None
    label: Label | None = None
    display_name: Label | None = None


class PhoneNumberPatch(RequestModel):
    employee_id: uuid.UUID | None = None
    label: Label | None = None
    display_name: Label | None = None


class KycSubmitIn(RequestModel):
    """Placeholder until document upload exists: we record what was chosen, not the file."""

    document_type: Literal["gst", "shop_establishment", "udyam", "pan", "clinic_registration"]
    file_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class OperatorCodes(ResponseModel):
    operator: Literal["jio", "airtel", "vi", "bsnl"]
    name: str
    busy: str
    no_answer: str
    unreachable: str
    cancel: str


class ForwardingOut(ResponseModel):
    phone_number_id: uuid.UUID
    target: str  # the Mitra number calls are forwarded to (dial form)
    operators: list[OperatorCodes]


class ForwardingTestOut(ResponseModel):
    status: Literal["passed", "pending"]
    simulated: bool
    tested_at: datetime | None
    message: str


class ComplianceSummaryOut(ResponseModel):
    days: int
    allowed: int
    counts: dict[str, int]
    lines: list[str]  # "18 people skipped: on Do-Not-Disturb list"


# ---- internal: voice service / routines --------------------------------------------------------


class ResolveOut(ResponseModel):
    business_id: uuid.UUID
    business_name: str
    employee_id: uuid.UUID
    phone_number_id: uuid.UUID
    caller_known: bool


class ComplianceCheckIn(RequestModel):
    business_id: uuid.UUID
    contact_phone: E164Phone
    purpose: CallPurpose
    at: datetime | None = None  # default: now
    number_id: uuid.UUID | None = None  # preferred caller ID
    called_number_id: uuid.UUID | None = None  # callback: the number the customer called
    dlt_template_id: DltTemplateId | None = None
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"


class ReasonOut(ResponseModel):
    code: str
    message: str


class CallerIdOut(ResponseModel):
    phone_number_id: uuid.UUID
    e164: str
    type: NumberType


class ComplianceCheckOut(ResponseModel):
    decision: Decision
    allowed: bool
    reasons: list[ReasonOut]
    caller_id: CallerIdOut | None
    defer_until: datetime | None
    decision_id: uuid.UUID


class AttemptIn(RequestModel):
    business_id: uuid.UUID
    contact_phone: E164Phone
    purpose: CallPurpose
    phone_number_id: uuid.UUID | None = None
    outcome: AttemptOutcome | None = None
    carrier_call_sid: CarrierSid | None = None
    attempted_at: datetime | None = None


class AttemptOutcomeIn(RequestModel):
    business_id: uuid.UUID
    outcome: AttemptOutcome


class AttemptOut(ResponseModel):
    id: uuid.UUID
    outcome: AttemptOutcome | None
    attempted_at: datetime


class OptOutIn(RequestModel):
    business_id: uuid.UUID
    contact_phone: E164Phone
    purpose: CallPurpose | None = None  # None = never call for any purpose
    source: OptOutSource = OptOutSource.VOICE


class ConsentIn(RequestModel):
    business_id: uuid.UUID
    contact_phone: E164Phone
    scope: ConsentScope
    source: ConsentSource
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class CreatedOut(ResponseModel):
    id: uuid.UUID


class CarrierUpdateIn(RequestModel):
    """What the carrier / verification partners tell us (KYC approved, Truecaller, spam label)."""

    business_id: uuid.UUID
    e164: E164Phone | None = None
    carrier_sid: CarrierSid | None = None
    kyc_status: KycStatus | None = None
    truecaller_status: VerificationStatus | None = None
    cnap_status: VerificationStatus | None = None
    spam_flag: bool | None = None


class HealthChange(ResponseModel):
    phone_number_id: uuid.UUID
    business_id: uuid.UUID
    previous: NumberHealth
    health: NumberHealth
    answer_rate_7d: float | None


class HealthRunOut(ResponseModel):
    checked: int
    changes: list[HealthChange] = Field(default_factory=list)
