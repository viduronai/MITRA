"""Telephony & compliance tables (migration 0004_telephony). All tenant tables under RLS.

Contacts' numbers are never stored in the clear here either: ``phone_hash`` is the same HMAC as
``contact.phone_hash`` (``mitra_core.pii.hash_phone``). The business's own numbers
(``phone_number.e164``) are public business identifiers and are stored as-is; inbound routing
looks them up through a SECURITY DEFINER function.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.telephony.enums import (
    AttemptOutcome,
    CallPurpose,
    Carrier,
    ConsentScope,
    ConsentSource,
    Decision,
    DndStatus,
    KycStatus,
    NumberHealth,
    NumberType,
    OptOutSource,
    VerificationStatus,
)

# Native enum type names are prefixed (tel_) so parallel migrations cannot collide.
NUMBER_TYPE = pg_enum(NumberType, "tel_number_type")
CARRIER = pg_enum(Carrier, "tel_carrier")
KYC_STATUS = pg_enum(KycStatus, "tel_kyc_status")
VERIFICATION = pg_enum(VerificationStatus, "tel_verification_status")
HEALTH = pg_enum(NumberHealth, "tel_number_health")
PURPOSE = pg_enum(CallPurpose, "tel_call_purpose")
CONSENT_SCOPE = pg_enum(ConsentScope, "tel_consent_scope")
CONSENT_SOURCE = pg_enum(ConsentSource, "tel_consent_source")
OPT_OUT_SOURCE = pg_enum(OptOutSource, "tel_opt_out_source")
OUTCOME = pg_enum(AttemptOutcome, "tel_attempt_outcome")
DECISION = pg_enum(Decision, "tel_decision")
DND = pg_enum(DndStatus, "tel_dnd_status")


def _business_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("business.id", ondelete="CASCADE"), index=True)


class PhoneNumber(UUIDPrimaryKey, Timestamps, Base):
    """A business number (NUM-01/03/05/09) and its trust + health state (section 3.7 card)."""

    __tablename__ = "phone_number"
    __table_args__ = (
        Index(
            "uq_phone_number_missed_call",
            "business_id",
            unique=True,
            postgresql_where=text("missed_call"),
        ),
    )

    business_id: Mapped[uuid.UUID] = _business_fk()
    # Inbound calls to this number are answered by this employee (number -> employee routing).
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL"), index=True
    )
    e164: Mapped[str | None] = mapped_column(String(16), unique=True)  # None until provisioned
    type: Mapped[NumberType] = mapped_column(NUMBER_TYPE)
    carrier: Mapped[Carrier] = mapped_column(CARRIER)
    carrier_sid: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(80))
    label: Mapped[str | None] = mapped_column(String(60))  # e.g. branch name
    kyc_status: Mapped[KycStatus] = mapped_column(KYC_STATUS)
    # Placeholder until document upload exists: {document_type, file_name, submitted_at}.
    kyc_document: Mapped[dict[str, Any] | None]
    display_name: Mapped[str | None] = mapped_column(String(60))  # CNAP / Truecaller name
    truecaller_status: Mapped[VerificationStatus] = mapped_column(
        VERIFICATION, server_default=VerificationStatus.NOT_STARTED.value
    )
    cnap_status: Mapped[VerificationStatus] = mapped_column(
        VERIFICATION, server_default=VerificationStatus.NOT_STARTED.value
    )
    answer_rate_7d: Mapped[float | None] = mapped_column(Float)
    spam_flag: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    health: Mapped[NumberHealth] = mapped_column(HEALTH, server_default=NumberHealth.HEALTHY.value)
    health_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    health_checked_at: Mapped[datetime | None]
    # Attempts before this are ignored by the monitor (set when the owner resumes a number).
    health_since: Mapped[datetime | None]
    outbound_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    forwarding_tested_at: Mapped[datetime | None]
    # CALL-20: calls to this number are rejected unanswered and called back (one per business).
    missed_call: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ConsentRecord(UUIDPrimaryKey, Base):
    """Purpose-tagged consent (CMP-03, DPDP): source, time, scope; revocable."""

    __tablename__ = "consent_record"
    __table_args__ = (
        Index("ix_consent_record_business_id_phone_hash", "business_id", "phone_hash"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    phone_hash: Mapped[str] = mapped_column(Text)
    scope: Mapped[ConsentScope] = mapped_column(CONSENT_SCOPE)
    source: Mapped[ConsentSource] = mapped_column(CONSENT_SOURCE)
    note: Mapped[str | None] = mapped_column(String(200))
    captured_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    revoked_at: Mapped[datetime | None]
    # Lead consent policy (0006): e.g. "enquiry_response"; the exact words agreed to and their
    # version; portal enquiries expire (load_facts ignores expired rows).
    purpose: Mapped[str | None] = mapped_column(String(40))
    text_version: Mapped[str | None] = mapped_column(String(20))
    consent_text: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None]


class OptOut(UUIDPrimaryKey, Base):
    """Suppression list (CMP-06). ``purpose`` NULL = do not call for any purpose."""

    __tablename__ = "opt_out"

    business_id: Mapped[uuid.UUID] = _business_fk()
    phone_hash: Mapped[str] = mapped_column(Text)
    purpose: Mapped[CallPurpose | None] = mapped_column(PURPOSE)
    source: Mapped[OptOutSource] = mapped_column(OPT_OUT_SOURCE)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class OutboundAttempt(UUIDPrimaryKey, Base):
    """Each dial attempt: frequency caps (CMP-05) and per-number answer rate (NUM-08)."""

    __tablename__ = "outbound_attempt"
    __table_args__ = (
        Index("ix_outbound_attempt_contact", "business_id", "phone_hash", "attempted_at"),
        Index("ix_outbound_attempt_number", "phone_number_id", "attempted_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("phone_number.id", ondelete="SET NULL")
    )
    purpose: Mapped[CallPurpose] = mapped_column(PURPOSE)
    outcome: Mapped[AttemptOutcome | None] = mapped_column(OUTCOME)
    carrier_call_sid: Mapped[str | None] = mapped_column(String(64))
    attempted_at: Mapped[datetime]


class ComplianceDecision(UUIDPrimaryKey, Base):
    """Every ``compliance.check`` result with its reasons (shown to the owner in plain words)."""

    __tablename__ = "compliance_decision"
    __table_args__ = (Index("ix_compliance_decision_recent", "business_id", "created_at"),)

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    phone_hash: Mapped[str] = mapped_column(Text)
    purpose: Mapped[CallPurpose] = mapped_column(PURPOSE)
    decision: Mapped[Decision] = mapped_column(DECISION)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text))
    phone_number_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("phone_number.id", ondelete="SET NULL")
    )
    defer_until: Mapped[datetime | None]
    created_at: Mapped[datetime]


class DndCache(Base):
    """DND/NCPR lookups, reused for at most 24 h (08 section 3 rule 3)."""

    __tablename__ = "dnd_cache"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), primary_key=True
    )
    phone_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[DndStatus] = mapped_column(DND)
    checked_at: Mapped[datetime]
