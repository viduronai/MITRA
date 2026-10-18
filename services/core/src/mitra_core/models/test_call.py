from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, UUIDPrimaryKey


class TestCall(UUIDPrimaryKey, Base):
    """A (for now simulated) call from an employee to the owner's phone.

    Status is derived from ``created_at`` (see ``mitra_core.simulation``); the transcript is
    generated once at creation from the facts known then. The callee's number is stored only
    as an HMAC + last 4 digits, like ``contact``.
    """

    __tablename__ = "test_call"
    __test__ = False

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(String(500))
    corrections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default="[]", default=list
    )
    # Set by the API from its (injectable) clock so the simulated progression is testable.
    created_at: Mapped[datetime]
