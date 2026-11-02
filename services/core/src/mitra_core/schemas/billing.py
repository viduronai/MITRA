"""Billing API shapes. Money is always integer paise (``*_paise``)."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import AfterValidator, AwareDatetime, Field, StringConstraints

from mitra_core.billing.rating import CallDirection, CallOutcome, PauseReason
from mitra_core.models.enums import VoiceTier
from mitra_core.schemas.common import PatchModel, RequestModel, ResponseModel

Paise = Annotated[int, Field(ge=0, le=10**12)]
CallId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[\x21-\x7e]+$")]
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def _gstin(value: str) -> str:
    value = value.strip().upper()
    if not GSTIN_RE.fullmatch(value):
        raise ValueError("not a valid GSTIN")
    return value


Gstin = Annotated[str, StringConstraints(max_length=20), AfterValidator(_gstin)]
PassthroughCategory = Literal["number_rental", "whatsapp", "sms", "verification"]


# ---------- internal (service-to-service) ----------


class UsageIn(RequestModel):
    call_id: CallId
    employee_id: uuid.UUID
    direction: CallDirection
    outcome: CallOutcome
    connected_seconds: float = Field(ge=0, le=24 * 3600)
    started_at: AwareDatetime


class UsageOut(ResponseModel):
    usage_event_id: uuid.UUID
    call_id: str
    billable_seconds: int
    grace_seconds: int
    tier: VoiceTier
    rate_paise_per_min: int
    amount_paise: int
    balance_paise: int
    bonus_paise: int
    outbound_paused: bool
    pause_reason: PauseReason | None
    low_balance: bool
    # True only on the call that crossed the alert threshold (send the WhatsApp alert once).
    low_balance_alert: bool
    autopay_topup_id: uuid.UUID | None
    replayed: bool


class AllowanceOut(ResponseModel):
    allowed: bool
    reason: PauseReason | None
    max_seconds: int
    tier: VoiceTier
    rate_paise_per_min: int


class PassthroughIn(RequestModel):
    business_id: uuid.UUID
    category: PassthroughCategory
    amount_paise: Annotated[int, Field(gt=0, le=1_00_000_00)]
    ref: CallId
    description: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class PassthroughOut(ResponseModel):
    txn_id: uuid.UUID
    created: bool
    balance_paise: int
    bonus_paise: int


class NumberRentalIn(RequestModel):
    business_id: uuid.UUID
    month: Annotated[str, StringConstraints(pattern=r"^20[0-9]{2}-(0[1-9]|1[0-2])$")]
    numbers: Annotated[int, Field(ge=0, le=100)]


class NumberRentalOut(ResponseModel):
    month: str
    usage_paise: int
    amount_paise: int
    waived: bool
    txn_id: uuid.UUID | None


# ---------- public ----------


class TierRate(ResponseModel):
    tier: VoiceTier
    paise_per_min: int
    minutes_left: int


class BonusSlab(ResponseModel):
    min_paise: int
    pct: int


class TopupRules(ResponseModel):
    min_paise: int
    max_paise: int
    gst_rate_pct: int
    bonus_slabs: list[BonusSlab]


class NumberRentalInfo(ResponseModel):
    fee_paise: int
    waiver_usage_paise: int
    # Usage still needed this month for the waiver (0 = already waived).
    remaining_to_waive_paise: int


class BillingProfile(ResponseModel):
    billing_name: str | None
    gstin: str | None
    state_code: str | None


class BillingSummary(ResponseModel):
    balance_paise: int
    bonus_paise: int
    available_paise: int
    rates: list[TierRate]
    month: date
    month_usage_paise: int
    month_extras_paise: int
    monthly_cap_paise: int | None
    cap_remaining_paise: int | None
    outbound_paused: bool
    pause_reason: PauseReason | None
    low_balance: bool
    low_balance_threshold_paise: int
    autopay_enabled: bool
    autopay_amount_paise: int
    credits_expire_at: datetime | None
    grace_seconds_left_today: int
    number_rental: NumberRentalInfo
    topup_rules: TopupRules
    profile: BillingProfile


class BillingSettingsIn(PatchModel):
    _nullable: ClassVar[frozenset[str]] = frozenset(
        {"monthly_cap_paise", "billing_name", "gstin", "state_code"}
    )

    monthly_cap_paise: Paise | None = None
    autopay_enabled: bool | None = None
    autopay_amount_paise: Annotated[int, Field(ge=500_00, le=10_00_000_00)] | None = None
    low_balance_threshold_paise: Annotated[int, Field(ge=0, le=1_00_000_00)] | None = None
    billing_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    gstin: Gstin | None = None
    state_code: Annotated[str, StringConstraints(pattern=r"^[0-9]{2}$")] | None = None


class TopupIn(RequestModel):
    amount_paise: Annotated[int, Field(ge=1, le=10**12)]


class TopupConfirmIn(RequestModel):
    payment_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    signature: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TopupOut(ResponseModel):
    id: uuid.UUID
    status: str
    source: str
    provider: str
    provider_order_id: str
    amount_paise: int
    bonus_paise: int
    gst_paise: int
    total_paise: int
    created_at: datetime
    paid_at: datetime | None
    invoice_id: uuid.UUID | None = None
    checkout: dict[str, Any] | None = None


class TxnOut(ResponseModel):
    id: uuid.UUID
    kind: str
    category: str | None
    paid_delta_paise: int
    bonus_delta_paise: int
    balance_after_paise: int
    bonus_after_paise: int
    description: str
    created_at: datetime


class TxnList(ResponseModel):
    items: list[TxnOut]


class UsageDay(ResponseModel):
    day: date
    calls: int
    billable_seconds: int
    amount_paise: int


class UsageByEmployee(ResponseModel):
    employee_id: uuid.UUID
    employee_name: str
    tier: VoiceTier
    calls: int
    billable_seconds: int
    amount_paise: int


class UsageReport(ResponseModel):
    since: date
    by_day: list[UsageDay]
    by_employee: list[UsageByEmployee]


class InvoiceSummary(ResponseModel):
    id: uuid.UUID
    number: str
    issued_at: datetime
    taxable_paise: int
    total_paise: int


class InvoiceList(ResponseModel):
    items: list[InvoiceSummary]


class InvoiceParty(ResponseModel):
    name: str
    gstin: str | None
    state_code: str | None
    address: str | None = None


class InvoiceOut(ResponseModel):
    id: uuid.UUID
    number: str
    issued_at: datetime
    supplier: InvoiceParty
    buyer: InvoiceParty
    place_of_supply: str | None
    intra_state: bool
    description: str
    sac_code: str
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
    gst_rate_pct: int
