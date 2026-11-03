"""API schemas: approvals, Ask Mitra thread, manager settings, WhatsApp simulator."""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, computed_field

from mitra_core.approvals.edits import editable_fields
from mitra_core.models.enums import Locale
from mitra_core.schemas.common import PatchModel, RequestModel, ResponseModel

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
AskText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
RuleKind = Literal["discount", "refund", "cancellation", "big_booking", "list_call", "payment_link"]


class ApprovalOut(ResponseModel):
    id: uuid.UUID
    kind: str
    summary: str
    payload: dict[str, Any]
    version: int
    status: str
    requested_by: str
    default_action: str | None
    expires_at: datetime | None
    decided_by: uuid.UUID | None
    decided_via: str | None
    decided_at: datetime | None
    decision_note: str | None
    apply_error: str | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def editable(self) -> list[str] | None:
        """Payload fields the owner may change before approving; ``None`` = any field."""
        return editable_fields(self.kind)


class ApprovalEventOut(ResponseModel):
    id: uuid.UUID
    event: str
    version: int
    actor_user_id: uuid.UUID | None
    via: str | None
    detail: dict[str, Any]
    created_at: datetime


class ApprovalDetail(ResponseModel):
    approval: ApprovalOut
    events: list[ApprovalEventOut]


class ApprovalList(ResponseModel):
    items: list[ApprovalOut]
    pending: int


class ApprovalEdit(RequestModel):
    version: int = Field(ge=1)
    payload: dict[str, Any]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class ApprovalDecision(RequestModel):
    action: Literal["approve", "decline"]
    version: int = Field(ge=1)
    note: Note | None = None


class RuleOut(ResponseModel):
    kind: str
    enabled: bool
    threshold: int | None
    timeout_minutes: int | None
    default_action: str | None


class RuleIn(RequestModel):
    kind: RuleKind
    enabled: bool
    threshold: int | None = Field(default=None, ge=0, le=100_000_000)
    timeout_minutes: int | None = Field(default=None, ge=1, le=10_080)
    default_action: Literal["approve", "decline"] | None = None


class RulesOut(ResponseModel):
    items: list[RuleOut]


class RulesIn(RequestModel):
    items: list[RuleIn] = Field(max_length=10)


class AskIn(RequestModel):
    text: AskText


class ThreadMessageOut(ResponseModel):
    id: uuid.UUID
    role: str
    channel: str
    text: str
    card: dict[str, Any] | None
    created_at: datetime


class ThreadOut(ResponseModel):
    items: list[ThreadMessageOut]


class Recipient(ResponseModel):
    user_id: uuid.UUID
    name: str | None
    role: str
    phone_last4: str


class ManagerSettingsOut(ResponseModel):
    report_enabled: bool
    report_time: time
    language: Locale | None
    report_user_ids: list[uuid.UUID]
    alert_user_ids: list[uuid.UUID]
    alert_kinds: list[str]
    people: list[Recipient]


class ManagerSettingsPatch(PatchModel):
    _nullable = frozenset({"language"})

    report_enabled: bool | None = None
    report_time: time | None = None
    language: Locale | None = None
    report_user_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    alert_user_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    alert_kinds: (
        list[Literal["hot_lead", "angry", "vip", "payment_failed", "campaign_paused"]] | None
    ) = None


class WaMessageOut(ResponseModel):
    id: uuid.UUID
    direction: str
    kind: str
    purpose: str
    user_id: uuid.UUID | None
    phone_last4: str
    body: str
    template: str | None
    buttons: list[dict[str, Any]]
    ref: dict[str, Any]
    provider_message_id: str | None
    status: str
    created_at: datetime


class WaMessageList(ResponseModel):
    items: list[WaMessageOut]


class SimInboundIn(RequestModel):
    """Simulate the logged-in owner replying on WhatsApp (dev only)."""

    kind: Literal["text", "voice", "button_reply"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    button_id: Annotated[str, StringConstraints(max_length=200)] | None = None
    context_id: Annotated[str, StringConstraints(max_length=128)] | None = None


class SimInboundOut(ResponseModel):
    outcome: str


class TickOut(ResponseModel):
    reports: int
    expired: int


class InternalWhatsAppSendIn(RequestModel):
    """What the AI employee promised to WhatsApp the caller (voice -> core, after the call)."""

    employee_id: uuid.UUID
    contact_phone: Annotated[str, StringConstraints(pattern=r"^\+[1-9][0-9]{7,14}$")]
    kind: Literal["booking_confirmation", "location", "document", "follow_up"]
    client_ref: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    call_id: uuid.UUID | None = None
    document: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    topic: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    when: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None


class InternalWhatsAppSendOut(ResponseModel):
    status: Literal["sent", "blocked", "failed", "duplicate", "not_in_knowledge", "invalid"]
