from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, SmallInteger, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, UUIDPrimaryKey


class IdempotencyRecord(UUIDPrimaryKey, Base):
    """Stored response for an ``Idempotency-Key``, scoped to a business (RLS like other tables).

    ``POST /v1/businesses`` has no business before it runs, so its records are stored under the
    business it created and looked up by ``(user_id, key)`` (see the partial unique index).
    """

    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint("business_id", "endpoint", "key"),
        Index(
            "uq_idempotency_record_user_business_create",
            "user_id",
            "key",
            unique=True,
            postgresql_where=text("endpoint = 'POST /v1/businesses'"),
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(SmallInteger)
    response_body: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
