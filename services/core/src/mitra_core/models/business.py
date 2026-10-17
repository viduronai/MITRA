from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import Industry


class Agency(UUIDPrimaryKey, Timestamps, Base):
    """Agency managing several client businesses. RLS-enabled with no policy yet (deny-all)."""

    __tablename__ = "agency"

    name: Mapped[str] = mapped_column(String(120))


class Business(UUIDPrimaryKey, Timestamps, Base):
    """The tenant. RLS policy keys on ``id`` (not ``business_id``)."""

    __tablename__ = "business"

    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agency.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    industry: Mapped[Industry] = mapped_column(pg_enum(Industry, "industry"))
    city: Mapped[str | None] = mapped_column(String(80))
    languages: Mapped[list[str]] = mapped_column(server_default=text("'{}'::text[]"))
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'Asia/Kolkata'"))


class Branch(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "branch"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(80))
