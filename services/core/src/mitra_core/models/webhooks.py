"""Outgoing signed webhooks (INT-13). Migration 0005_leads; both tables under RLS.

``webhook_delivery`` is an outbox: ``emit_event`` inserts rows inside the caller's transaction
and a sender delivers them after commit, retrying with backoff. Payloads never carry a full
customer phone number (last 4 digits only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mitra_core.models.base import Base, Timestamps, UUIDPrimaryKey


class WebhookEndpoint(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "webhook_endpoint"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(String(120))
    events: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # Signing needs the secret itself, so it cannot be hashed. TODO(kms): envelope-encrypt.
    secret: Mapped[str] = mapped_column(Text)
    secret_hint: Mapped[str] = mapped_column(String(12))
    headers: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", default=dict)
    enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class WebhookDelivery(UUIDPrimaryKey, Base):
    __tablename__ = "webhook_delivery"
    __table_args__ = (
        Index("ix_webhook_delivery_due", "business_id", "status", "next_attempt_at"),
        Index("ix_webhook_delivery_endpoint", "endpoint_id", "created_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business.id", ondelete="CASCADE"))
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoint.id", ondelete="CASCADE")
    )
    event_id: Mapped[uuid.UUID]  # same for every endpoint receiving this event
    event: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(12))  # DeliveryStatus
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    next_attempt_at: Mapped[datetime | None]
    last_attempt_at: Mapped[datetime | None]
    response_status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(300))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime]
