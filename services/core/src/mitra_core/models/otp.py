from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base


class OtpRequest(Base):
    """A pending phone-OTP login. Pre-auth, so NOT tenant-scoped (no business or user yet).

    The API role has no privileges on this table at all: it is reached only through the
    ``auth_otp_issue`` / ``auth_otp_verify`` SECURITY DEFINER functions (migration 0002). The
    code itself is never stored, only an HMAC of it (``mitra_core.otp.hash_code``).
    ``phone_e164`` is kept only until the row is purged (24 h) because verify must create the
    user; ``phone_hash`` is the rate-limit index.
    """

    __tablename__ = "otp_request"
    __table_args__ = (Index("ix_otp_request_phone_hash_created_at", "phone_hash", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    phone_e164: Mapped[str] = mapped_column(String(16))
    phone_hash: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
