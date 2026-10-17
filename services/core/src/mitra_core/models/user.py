from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import Locale, MemberRole


class AppUser(UUIDPrimaryKey, Timestamps, Base):
    """A person who logs in (owner/staff). Not a tenant table: one user can join many businesses.

    RLS: a user sees themself plus members of the current business; may only write themself.
    """

    __tablename__ = "app_user"

    phone_e164: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    preferred_locale: Mapped[Locale] = mapped_column(
        pg_enum(Locale, "locale"), server_default=Locale.EN.value
    )


class Membership(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("business_id", "user_id"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MemberRole] = mapped_column(pg_enum(MemberRole, "member_role"))
