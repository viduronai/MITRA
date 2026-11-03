from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import Locale


class Contact(UUIDPrimaryKey, Timestamps, Base):
    """A business's customer / lead.

    Raw phone numbers are NEVER stored here. ``phone_hash`` is HMAC-SHA256 of the E.164 number
    (see ``mitra_core.pii.hash_phone``) and serves as the lookup/dedupe index; ``phone_last4``
    is for display only. ``phone_enc`` is the number sealed with the business's key
    (``mitra_core.phones``); read it only through ``phones.reveal_phone`` (access-logged).
    """

    __tablename__ = "contact"
    __table_args__ = (UniqueConstraint("business_id", "phone_hash"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    phone_enc: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[Locale | None] = mapped_column(pg_enum(Locale, "locale"))
