"""Phone access log and the missed-call number (migration 0006_phones). Tenant tables, RLS.

None of these rows hold a phone number: callers are ``phone_hash`` (HMAC) + ``phone_last4``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, UUIDPrimaryKey


class PhoneAccessLog(UUIDPrimaryKey, Base):
    """Every time a customer's number was decrypted: who, why, when (never the number)."""

    __tablename__ = "phone_access_log"
    __table_args__ = (Index("ix_phone_access_log_business_created", "business_id", "created_at"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    # Kept after "forget this customer" (the audit trail outlives the number).
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact.id", ondelete="SET NULL"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime]


class MissedCall(UUIDPrimaryKey, Base):
    """One call to a missed-call number (CALL-20) and what Mitra did about it.

    ``status``: queued (callback in the dialer) | deduped (already queued recently) |
    rate_limited | blocked (block list or opted out).
    """

    __tablename__ = "missed_call"
    __table_args__ = (
        Index("ix_missed_call_business_received", "business_id", "received_at"),
        Index("ix_missed_call_caller", "business_id", "phone_hash", "received_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("phone_number.id", ondelete="SET NULL")
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact.id", ondelete="SET NULL")
    )
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(16))
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_job.id", ondelete="SET NULL")
    )
    call_back_at: Mapped[datetime | None]
    carrier_call_sid: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime]


class CallerBlock(UUIDPrimaryKey, Base):
    """Callers whose missed calls are ignored (abuse guard). Unique per business + caller."""

    __tablename__ = "caller_block"
    __table_args__ = (Index("uq_caller_block", "business_id", "phone_hash", unique=True),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    reason: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime]
