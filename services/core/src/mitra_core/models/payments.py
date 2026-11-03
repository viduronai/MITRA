"""UPI collections for the business's own customers (ACT-05, ACT-11, INT-08; migration 0006).

This is the business's money, collected into the business's own Razorpay account or UPI ID.
It never touches Mitra's wallet (``models/billing.py``); nothing here is joined with billing.

* ``collection_settings``: one row per business. ``mode`` is ``none`` / ``razorpay`` / ``upi``.
  Razorpay secrets are stored sealed (``*_sealed``) and never returned by the API.
  ``webhook_token`` is the random path segment of the business's own webhook URL.
* ``payment_request``: one link sent to one customer. Amounts are integer paise.
* ``payment_event``: provider webhook events already applied (idempotency).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey

REQUEST_STATUSES = ("awaiting_approval", "sent", "paid", "failed", "expired", "cancelled")
OPEN_STATUSES = ("sent", "failed")  # still payable: reminders apply, a webhook can mark paid


def _business() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("business.id", ondelete="CASCADE"), index=True)


class CollectionSettings(Timestamps, Base):
    __tablename__ = "collection_settings"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(10), server_default="none")
    razorpay_key_id: Mapped[str | None] = mapped_column(String(64))
    razorpay_key_secret_sealed: Mapped[str | None] = mapped_column(Text)
    razorpay_webhook_secret_sealed: Mapped[str | None] = mapped_column(Text)
    webhook_token: Mapped[str] = mapped_column(String(64), unique=True)
    upi_vpa: Mapped[str | None] = mapped_column(String(100))
    payee_name: Mapped[str | None] = mapped_column(String(100))
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    link_expiry_days: Mapped[int] = mapped_column(SmallInteger, server_default="15")
    # Lending / BFSI: payment-collection calls only 08:00-19:00 (compliance gate).
    is_lender: Mapped[bool] = mapped_column(Boolean, server_default="false")


class PaymentRequest(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "payment_request"
    __table_args__ = (UniqueConstraint("business_id", "client_ref"),)

    business_id: Mapped[uuid.UUID] = _business()
    # SET NULL: a DPDP erasure removes the person, the business keeps its money records.
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact.id", ondelete="SET NULL"), index=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(120))
    phone_last4: Mapped[str | None] = mapped_column(String(4))
    amount_paise: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(10))  # razorpay | upi (copied at creation)
    provider: Mapped[str | None] = mapped_column(String(16))  # razorpay | sim
    provider_link_id: Mapped[str | None] = mapped_column(String(64))
    short_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))  # owner | employee | manager
    client_ref: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("call.id", ondelete="SET NULL"))
    approval_id: Mapped[uuid.UUID | None] = mapped_column()
    discount_percent: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column()
    send_error: Mapped[str | None] = mapped_column(String(200))
    paid_at: Mapped[datetime | None] = mapped_column()
    paid_via: Mapped[str | None] = mapped_column(String(16))  # webhook | manual
    provider_payment_id: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(String(200))
    cancelled_at: Mapped[datetime | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column()
    # The customer tapped "Already paid": the owner confirms; never marked paid automatically.
    customer_says_paid_at: Mapped[datetime | None] = mapped_column()
    # Reminders (ACT-11): when the next step is due, which step ran, what it created.
    remind_at: Mapped[datetime | None] = mapped_column()
    reminder_stage: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    reminders: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)


class PaymentEvent(UUIDPrimaryKey, Base):
    __tablename__ = "payment_event"
    __table_args__ = (UniqueConstraint("business_id", "event_id"),)

    business_id: Mapped[uuid.UUID] = _business()
    event_id: Mapped[str] = mapped_column(String(80))
    event: Mapped[str] = mapped_column(String(40))
    payment_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_request.id", ondelete="SET NULL")
    )
    outcome: Mapped[str] = mapped_column(String(20))
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
