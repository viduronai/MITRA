from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base


class DemoCall(Base):
    """A "Call me now" request from the marketing site. Public and pre-auth, so NOT
    tenant-scoped.

    Like ``otp_request``, the API role has no privileges on this table: it is reached only
    through the ``demo_call_request`` SECURITY DEFINER function (migration 0004), which applies
    the per-phone and per-IP rate limits. The phone number and client IP are never stored, only
    HMACs of them (``mitra_core.pii.hash_phone``) plus the last 4 digits for support. Rows are
    purged after 30 days.
    """

    __tablename__ = "demo_call"
    __table_args__ = (
        Index("ix_demo_call_phone_hash_created_at", "phone_hash", "created_at"),
        Index("ix_demo_call_ip_hash_created_at", "ip_hash", "created_at"),
        CheckConstraint("language IN ('te', 'hi', 'en')", name="language"),
        CheckConstraint("industry IN ('clinic', 'real_estate', 'coaching')", name="industry"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    ip_hash: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    industry: Mapped[str] = mapped_column(String(16))
    # TODO(telephony): 'queued' only until the Exotel dialer exists (then dialling/connected/...).
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    simulated: Mapped[bool] = mapped_column(server_default="true")
    consented_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
