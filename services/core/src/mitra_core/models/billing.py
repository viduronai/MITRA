"""Billing tables (migration 0004_billing). All money is integer paise.

``wallet_txn`` and ``usage_event`` are append-only: the app role may only SELECT and INSERT
them. ``rate_card`` is global (read-only for the app role).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import VoiceTier


class RateCard(UUIDPrimaryKey, Base):
    __tablename__ = "rate_card"

    tier: Mapped[VoiceTier] = mapped_column(pg_enum(VoiceTier, "voice_tier"))
    # 'retail' | 'agency' (wholesale)
    channel: Mapped[str] = mapped_column(String(16))
    paise_per_min: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime]


class Wallet(Timestamps, Base):
    """One per business, created lazily (with the sign-up trial credit) on first use."""

    __tablename__ = "wallet"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), primary_key=True
    )
    balance_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    bonus_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    monthly_cap_paise: Mapped[int | None] = mapped_column(BigInteger)
    low_balance_threshold_paise: Mapped[int] = mapped_column(BigInteger)
    low_balance_alerted: Mapped[bool] = mapped_column(default=False)
    autopay_enabled: Mapped[bool] = mapped_column(default=False)
    autopay_amount_paise: Mapped[int] = mapped_column(BigInteger)
    credits_expire_at: Mapped[datetime | None]
    # Month (first day, IST) that month_usage_paise belongs to; rolled over lazily.
    usage_month: Mapped[date | None]
    month_usage_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    grace_day: Mapped[date | None]
    grace_seconds_used: Mapped[int] = mapped_column(Integer, default=0)
    billing_name: Mapped[str | None] = mapped_column(String(120))
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str | None] = mapped_column(String(2))


class WalletTxn(UUIDPrimaryKey, Base):
    """Ledger line. kind: topup | bonus | usage | passthrough | refund | expiry."""

    __tablename__ = "wallet_txn"
    __table_args__ = (UniqueConstraint("business_id", "kind", "ref"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    # For passthrough: number_rental | whatsapp | sms | verification
    category: Mapped[str | None] = mapped_column(String(32))
    paid_delta_paise: Mapped[int] = mapped_column(BigInteger)
    bonus_delta_paise: Mapped[int] = mapped_column(BigInteger)
    balance_after_paise: Mapped[int] = mapped_column(BigInteger)
    bonus_after_paise: Mapped[int] = mapped_column(BigInteger)
    ref: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime]


class UsageEvent(UUIDPrimaryKey, Base):
    """One rated call. ``employee_id`` is a plain column (no FK) so the row is never rewritten."""

    __tablename__ = "usage_event"
    __table_args__ = (UniqueConstraint("business_id", "call_id"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    employee_id: Mapped[uuid.UUID]
    employee_name: Mapped[str] = mapped_column(String(60))
    direction: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    connected_ms: Mapped[int] = mapped_column(BigInteger)
    billable_seconds: Mapped[int] = mapped_column(Integer)
    grace_seconds: Mapped[int] = mapped_column(Integer)
    tier: Mapped[VoiceTier] = mapped_column(pg_enum(VoiceTier, "voice_tier"))
    rate_paise_per_min: Mapped[int] = mapped_column(Integer)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    started_at: Mapped[datetime]
    created_at: Mapped[datetime]


class TopupOrder(UUIDPrimaryKey, Timestamps, Base):
    """A wallet top-up through a payment provider. status: created | paid | failed."""

    __tablename__ = "topup_order"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16))
    provider_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    # manual | autopay
    source: Mapped[str] = mapped_column(String(16))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    bonus_paise: Mapped[int] = mapped_column(BigInteger)
    gst_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    paid_at: Mapped[datetime | None]


class Invoice(UUIDPrimaryKey, Base):
    """GST tax invoice, one per paid top-up. Numbered per financial year (MIT/26-27/000001)."""

    __tablename__ = "invoice"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    topup_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topup_order.id", ondelete="CASCADE"), unique=True
    )
    number: Mapped[str] = mapped_column(String(16), unique=True)
    issued_at: Mapped[datetime]
    billing_name: Mapped[str] = mapped_column(String(120))
    gstin: Mapped[str | None] = mapped_column(String(15))
    place_of_supply: Mapped[str | None] = mapped_column(String(2))
    intra_state: Mapped[bool]
    description: Mapped[str] = mapped_column(String(200))
    taxable_paise: Mapped[int] = mapped_column(BigInteger)
    cgst_paise: Mapped[int] = mapped_column(BigInteger)
    sgst_paise: Mapped[int] = mapped_column(BigInteger)
    igst_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
