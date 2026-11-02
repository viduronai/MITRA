"""Lead intake (INT-01/02/03/06/12/14) and instant lead calling (CALL-03). Migration 0005_leads.

All three tables are tenant tables under RLS. A lead's phone number is never stored in the clear:
``phone_hash`` is the same HMAC as ``contact.phone_hash`` and the number itself only travels to
the dialer queue. The intake secret is stored as a SHA-256 hash (it is 256 bits of randomness, so
a plain hash cannot be brute-forced); the owner sees it once, when it is created or rotated.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey


class LeadIntake(Timestamps, Base):
    """One per business: the public intake URL slug and its secret (rotatable)."""

    __tablename__ = "lead_intake"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), primary_key=True
    )
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    secret_hash: Mapped[str] = mapped_column(Text)
    secret_hint: Mapped[str] = mapped_column(String(12))  # "mli_ab12…" for the UI
    # After a rotation the old secret keeps working for a grace period (update Zapier etc.).
    previous_secret_hash: Mapped[str | None] = mapped_column(Text)
    previous_valid_until: Mapped[datetime | None]
    rotated_at: Mapped[datetime | None]
    dedupe_minutes: Mapped[int] = mapped_column(Integer, server_default=text("10"))


class LeadSource(UUIDPrimaryKey, Timestamps, Base):
    """A connected lead source and its event routine (AUTO-02: who calls, how fast)."""

    __tablename__ = "lead_source"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))  # LeadSourceKind
    enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    auto_call: Mapped[bool] = mapped_column(server_default=text("true"))
    call_delay_seconds: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    heads_up: Mapped[bool] = mapped_column(server_default=text("false"))  # NUM-07
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    # Meta page id: maps the app-wide Meta webhook to this business.
    external_id: Mapped[str | None] = mapped_column(String(64))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    # IndiaMART pull key. TODO(kms): envelope-encrypt like OAuth tokens (08 section 6).
    credential: Mapped[str | None] = mapped_column(Text)
    credential_hint: Mapped[str | None] = mapped_column(String(12))
    last_lead_at: Mapped[datetime | None]
    last_pulled_at: Mapped[datetime | None]
    lead_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(String(300))


class Lead(UUIDPrimaryKey, Base):
    """One received lead, its consent record and what happened to it (the instant call)."""

    __tablename__ = "lead"
    __table_args__ = (
        Index("ix_lead_dedupe", "business_id", "phone_hash", "received_at"),
        Index("ix_lead_recent", "business_id", "received_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead_source.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(20))  # LeadSourceKind, kept for ROI
    source_detail: Mapped[str | None] = mapped_column(String(120))  # ad campaign / form name
    external_id: Mapped[str | None] = mapped_column(String(80))  # portal's own lead id
    # Erasure ("forget this customer") deletes the contact and, by cascade, their leads.
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), index=True
    )
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    name: Mapped[str | None] = mapped_column(String(120))
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    status: Mapped[str] = mapped_column(String(20))  # LeadStatus
    reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]"), default=list
    )
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead.id", ondelete="SET NULL")
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    call_job_id: Mapped[uuid.UUID | None]
    call_at: Mapped[datetime | None]
    consent_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("consent_record.id", ondelete="SET NULL")
    )
    ip_hash: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime]
