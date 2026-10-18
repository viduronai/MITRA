from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import (
    FactCategory,
    FactStatus,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)


class KnowledgeSource(UUIDPrimaryKey, Timestamps, Base):
    """Something the business taught its employees: a web page or pasted text."""

    __tablename__ = "knowledge_source"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[KnowledgeSourceType] = mapped_column(
        pg_enum(KnowledgeSourceType, "knowledge_source_type")
    )
    status: Mapped[KnowledgeSourceStatus] = mapped_column(
        pg_enum(KnowledgeSourceStatus, "knowledge_source_status")
    )
    title: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(2048))
    # Raw pasted text, kept so a better extractor (Step 3, LLM) can re-process it.
    content: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(300))


class Fact(UUIDPrimaryKey, Timestamps, Base):
    """One owner-reviewable fact (TRD §7 layer A). ``source_id`` is null for manual facts."""

    __tablename__ = "fact"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_source.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[FactCategory] = mapped_column(pg_enum(FactCategory, "fact_category"))
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(String(500))
    status: Mapped[FactStatus] = mapped_column(pg_enum(FactStatus, "fact_status"))
