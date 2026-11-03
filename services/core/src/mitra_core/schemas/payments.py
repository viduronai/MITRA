"""UPI collections (ACT-05/11, INT-08): collection settings and payment requests.

Secrets are write-only: responses say whether one is stored, never what it is.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from mitra_core.schemas.common import E164Phone, RequestModel, ResponseModel

Purpose = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Secret = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=128)]
ClientRef = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9:._-]{1,120}$")]
Amount = Annotated[int, Field(ge=100, le=100_000_000)]
Status = Literal["awaiting_approval", "sent", "paid", "failed", "expired", "cancelled"]


class CollectionSettingsOut(ResponseModel):
    mode: Literal["none", "razorpay", "upi"]
    razorpay_key_id: str | None  # masked: rzp_test_••••abcd
    has_key_secret: bool
    has_webhook_secret: bool
    webhook_url: str
    upi_vpa: str | None
    payee_name: str | None
    reminders_enabled: bool
    link_expiry_days: int
    is_lender: bool  # collection calls only 08:00-19:00
    simulated: bool  # links open the local simulator instead of Razorpay
    auto_confirm: bool  # False in UPI-ID mode: the owner marks payments as paid


class CollectionSettingsIn(RequestModel):
    mode: Literal["none", "razorpay", "upi"]
    razorpay_key_id: str | None = Field(default=None, max_length=64)
    razorpay_key_secret: Secret | None = None
    razorpay_webhook_secret: Secret | None = None
    upi_vpa: str | None = Field(default=None, max_length=100)
    payee_name: str | None = Field(default=None, max_length=100)
    reminders_enabled: bool | None = None
    link_expiry_days: int | None = Field(default=None, ge=1, le=180)
    is_lender: bool | None = None

    @model_validator(mode="after")
    def _fields_for_mode(self) -> Self:
        if self.mode == "upi" and not self.upi_vpa:
            raise ValueError("upi_vpa is required for UPI ID mode")
        return self


class PaymentRequestIn(RequestModel):
    contact_id: uuid.UUID | None = None
    phone: E164Phone | None = None
    customer_name: str | None = Field(default=None, max_length=120)
    amount_paise: Amount
    purpose: Purpose
    due_date: date | None = None
    client_ref: ClientRef | None = None

    @model_validator(mode="after")
    def _one_customer(self) -> Self:
        if (self.contact_id is None) == (self.phone is None):
            raise ValueError("give exactly one of contact_id or phone")
        return self


class PaymentRequestOut(ResponseModel):
    id: uuid.UUID
    contact_id: uuid.UUID | None
    customer_name: str | None
    phone_last4: str | None
    amount_paise: int
    purpose: str
    due_date: date | None
    status: Status
    mode: Literal["razorpay", "upi"]
    provider: str | None
    short_url: str | None
    source: Literal["owner", "employee", "manager"]
    employee_id: uuid.UUID | None
    call_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    discount_percent: int
    sent_at: datetime | None
    send_error: str | None
    paid_at: datetime | None
    paid_via: str | None
    failure_reason: str | None
    cancelled_at: datetime | None
    expires_at: datetime | None
    customer_says_paid_at: datetime | None
    remind_at: datetime | None
    reminder_stage: int
    created_at: datetime


class PaymentTotals(ResponseModel):
    collected_this_month_paise: int
    paid_this_month: int
    pending_paise: int
    pending_count: int
    failed_count: int


class PaymentList(ResponseModel):
    items: list[PaymentRequestOut]
    totals: PaymentTotals


class InternalPaymentLinkIn(RequestModel):
    """From the voice service: an employee sends a payment link during or after a call."""

    employee_id: uuid.UUID
    contact_phone: E164Phone
    amount_paise: Amount
    purpose: Purpose
    discount_percent: int = Field(default=0, ge=0, le=100)
    call_id: uuid.UUID | None = None
    client_ref: ClientRef


class InternalPaymentLinkOut(ResponseModel):
    payment_request_id: uuid.UUID
    status: Status
    needs_approval: bool


class PaymentTickOut(ResponseModel):
    reminded: int
    skipped: int
    failed: int
