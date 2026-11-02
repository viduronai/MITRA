"""Customer memory (TRD §8): episodic summaries, facts about the customer, open promises.

Every row hangs off a ``contact`` with ``ON DELETE CASCADE``, so erasing a contact erases its
memory too (MEM-04, DPDP).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import CommitmentStatus, MemoryStatus


class InteractionSummary(UUIDPrimaryKey, Base):
    """≤ 80-word summary of one call; the last 5 are read at call start."""

    __tablename__ = "interaction_summary"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(String(800))
    created_at: Mapped[datetime]


class MemoryFact(UUIDPrimaryKey, Timestamps, Base):
    """A fact about a customer. Inferred facts are never stated to the customer as certain."""

    __tablename__ = "memory_fact"
    __table_args__ = (UniqueConstraint("contact_id", "key"),)

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), index=True
    )
    source_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("call.id", ondelete="SET NULL"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(300))
    status: Mapped[MemoryStatus] = mapped_column(pg_enum(MemoryStatus, "memory_status"))
    confidence: Mapped[float] = mapped_column(Numeric(3, 2, asdecimal=False))
    expires_at: Mapped[datetime | None]


class Commitment(UUIDPrimaryKey, Timestamps, Base):
    """A promise or open loop ("call back tomorrow", "appointment Tue 6:15 pm")."""

    __tablename__ = "commitment"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), index=True
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("call.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(300))
    due_at: Mapped[datetime | None]
    status: Mapped[CommitmentStatus] = mapped_column(pg_enum(CommitmentStatus, "commitment_status"))
