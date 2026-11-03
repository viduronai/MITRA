"""WhatsApp messages, approvals ("Ask me first") and the AI Manager (migration 0005_manager).

Status and kind columns are short strings with CHECK constraints (not native enums) so other
modules can add approval kinds and message purposes without a migration.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any, ClassVar

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from mitra_core.models.enums import Locale


class _EagerDefaults:
    """Fetch server defaults (``created_at``) via RETURNING, as ``Timestamps`` does."""

    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}


class WaMessage(UUIDPrimaryKey, _EagerDefaults, Base):
    """One WhatsApp message in or out. Customer numbers are stored as HMAC + last 4 only."""

    __tablename__ = "wa_message"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(3))  # out | in
    # text | template | buttons | voice | button_reply
    kind: Mapped[str] = mapped_column(String(16))
    # alert | report | approval | manager | customer | staff
    purpose: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_last4: Mapped[str] = mapped_column(String(4))
    body: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    buttons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]", default=list)
    ref: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    provider: Mapped[str] = mapped_column(String(16))
    provider_message_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(12))  # sent | failed | received
    dedupe_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class Approval(UUIDPrimaryKey, Timestamps, Base):
    """An "Ask me first" card (APPR-01..06). ``version`` bumps on every owner edit; a decision
    must name the version it saw, and ``used_at`` makes the approval single-use."""

    __tablename__ = "approval"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(String(500))
    # Server-built summaries (approvals/summaries.py): key + params, rendered per language.
    summary_key: Mapped[str | None] = mapped_column(String(48))
    summary_params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # pending | approved | declined | expired | cancelled
    status: Mapped[str] = mapped_column(String(12), default="pending")
    requested_by: Mapped[str] = mapped_column(String(120))
    default_action: Mapped[str | None] = mapped_column(String(8))
    expires_at: Mapped[datetime | None]
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_via: Mapped[str | None] = mapped_column(String(12))  # app | whatsapp | timeout
    decided_at: Mapped[datetime | None]
    decision_note: Mapped[str | None] = mapped_column(String(300))
    used_at: Mapped[datetime | None]
    apply_error: Mapped[str | None] = mapped_column(String(300))


class ApprovalEvent(UUIDPrimaryKey, _EagerDefaults, Base):
    """Append-only approval log (APPR-05): requested, edited, decided, applied, rejected."""

    __tablename__ = "approval_event"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approval.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    via: Mapped[str | None] = mapped_column(String(12))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class ApprovalRule(Timestamps, Base):
    """APPR-01: whether a kind needs approval, above what threshold, and the timeout default."""

    __tablename__ = "approval_rule"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    threshold: Mapped[int | None] = mapped_column(Integer)
    timeout_minutes: Mapped[int | None] = mapped_column(Integer)
    default_action: Mapped[str | None] = mapped_column(String(8))


class ManagerSettings(Timestamps, Base):
    """Who gets the morning report and instant alerts, when, and in which language."""

    __tablename__ = "manager_settings"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), primary_key=True
    )
    report_enabled: Mapped[bool] = mapped_column(default=True)
    report_time: Mapped[time] = mapped_column(server_default=text("'08:00'"))
    language: Mapped[Locale | None] = mapped_column(pg_enum(Locale, "locale"))
    # Empty = every owner and manager of the business.
    report_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid),
        server_default=text("'{}'::uuid[]"),
    )
    alert_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid),
        server_default=text("'{}'::uuid[]"),
    )
    alert_kinds: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        server_default=text("'{hot_lead,angry,vip,payment_failed,campaign_paused}'::text[]"),
    )
    last_report_on: Mapped[date | None]


class ManagerMessage(UUIDPrimaryKey, _EagerDefaults, Base):
    """One turn of the Manager conversation (in-app "Ask Mitra" or WhatsApp)."""

    __tablename__ = "manager_message"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(10))  # app | whatsapp
    role: Mapped[str] = mapped_column(String(8))  # owner | mitra
    text: Mapped[str] = mapped_column(Text)
    # {"approval_id": ..., "kind": "confirm"} or {"links": [...]} for the UI.
    card: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
