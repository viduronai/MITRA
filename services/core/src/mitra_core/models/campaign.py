"""Outbound dialer queue + campaigns (migration 0005_campaigns). All tenant tables under RLS.

The dialer must be able to dial, so a queued contact's number is kept SEALED (``phone_enc``,
see ``mitra_core.dialer.sealing``) next to its HMAC index (``phone_hash``) and display digits
(``phone_last4``). It is never stored or logged in the clear.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.dialer.enums import CampaignStatus, ContactStatus, JobStatus, ResultBucket
from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.telephony import OUTCOME, PURPOSE
from mitra_core.telephony.enums import AttemptOutcome, CallPurpose

JOB_STATUS = pg_enum(JobStatus, "dlr_job_status")
CAMPAIGN_STATUS = pg_enum(CampaignStatus, "dlr_campaign_status")
CONTACT_STATUS = pg_enum(ContactStatus, "dlr_contact_status")
BUCKET = pg_enum(ResultBucket, "dlr_result_bucket")

DEFAULT_LADDER_SQL = "'{30,120,1440}'::integer[]"
WEEKDAYS_SQL = "'{0,1,2,3,4,5}'::smallint[]"  # Mon-Sat (Python weekday numbers)


class DialerConfig(Timestamps, Base):
    """Per-business dialer settings: concurrent outbound channels (CALL-09)."""

    __tablename__ = "dialer_config"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), primary_key=True
    )
    channels: Mapped[int] = mapped_column(SmallInteger, server_default=text("5"))


class Campaign(UUIDPrimaryKey, Timestamps, Base):
    """A list of people one employee calls with one script (CALL-15)."""

    __tablename__ = "campaign"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[CallPurpose] = mapped_column(PURPOSE)
    status: Mapped[CampaignStatus] = mapped_column(
        CAMPAIGN_STATUS, server_default=CampaignStatus.DRAFT.value
    )
    # Script variables the employee's prompt can use ({lead_name}); CSV column -> variable.
    column_map: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    skip_recent_days: Mapped[int] = mapped_column(SmallInteger, server_default=text("7"))
    calling_days: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text(WEEKDAYS_SQL)
    )
    holidays: Mapped[list[date]] = mapped_column(ARRAY(Date), server_default=text("'{}'::date[]"))
    retry_ladder: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), server_default=text(DEFAULT_LADDER_SQL)
    )
    ends_on: Mapped[date | None] = mapped_column(Date)  # last calling day ("extend" moves it)
    avg_call_seconds: Mapped[int] = mapped_column(Integer, server_default=text("90"))
    pause_reason: Mapped[str | None] = mapped_column(String(40))
    carrier_strikes: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    approval_id: Mapped[uuid.UUID | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class CampaignContact(UUIDPrimaryKey, Timestamps, Base):
    """One person on a campaign list and their result bucket."""

    __tablename__ = "campaign_contact"
    __table_args__ = (
        Index("uq_campaign_contact_phone", "campaign_id", "phone_hash", unique=True),
        Index("ix_campaign_contact_campaign_status", "campaign_id", "status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    phone_enc: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(120))
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[ContactStatus] = mapped_column(
        CONTACT_STATUS, server_default=ContactStatus.PENDING.value
    )
    bucket: Mapped[ResultBucket | None] = mapped_column(BUCKET)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    last_outcome: Mapped[AttemptOutcome | None] = mapped_column(OUTCOME)
    call_id: Mapped[uuid.UUID | None]
    summary: Mapped[str | None] = mapped_column(String(800))
    last_called_at: Mapped[datetime | None]


class OutboundJob(UUIDPrimaryKey, Timestamps, Base):
    """One person to call, by one employee, no earlier than ``not_before`` (the dialer queue).

    Created by :func:`mitra_core.dialer.queue.enqueue_call` (campaigns, callbacks, lead
    follow-ups, reminders). The worker runs ``compliance.check`` right before each dial.
    """

    __tablename__ = "outbound_job"
    __table_args__ = (
        Index("ix_outbound_job_due", "business_id", "status", "not_before"),
        Index("ix_outbound_job_contact", "business_id", "phone_hash", "status"),
        Index("ix_outbound_job_campaign", "campaign_id", "status"),
        # One active job per dedupe key (e.g. "lead:<id>:followup"); finished jobs don't count.
        Index(
            "uq_outbound_job_dedupe",
            "business_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'dialing')"),
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employee.id", ondelete="CASCADE"))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaign.id", ondelete="CASCADE")
    )
    campaign_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaign_contact.id", ondelete="CASCADE")
    )
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    phone_enc: Mapped[str] = mapped_column(Text)
    purpose: Mapped[CallPurpose] = mapped_column(PURPOSE)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    source: Mapped[str] = mapped_column(String(32))
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[JobStatus] = mapped_column(JOB_STATUS, server_default=JobStatus.QUEUED.value)
    not_before: Mapped[datetime] = mapped_column(server_default=text("now()"))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    retry_ladder: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), server_default=text(DEFAULT_LADDER_SQL)
    )
    called_number_id: Mapped[uuid.UUID | None]  # callbacks: ring back from the number they called
    last_outcome: Mapped[AttemptOutcome | None] = mapped_column(OUTCOME)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_attempt.id", ondelete="SET NULL")
    )
    carrier_call_sid: Mapped[str | None] = mapped_column(String(64))
    dialed_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
