"""Customers (contacts) with memory and timeline (MEM-01/03/04/05)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import StringConstraints

from mitra_core.models.enums import CallResult, CommitmentStatus, Locale, MemoryStatus
from mitra_core.schemas.common import PatchModel, ResponseModel

MemoryValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]

Tag = Literal["hot_lead", "booked", "call_back", "vip", "opted_out"]


class CustomerRow(ResponseModel):
    id: uuid.UUID
    name: str | None
    phone_last4: str
    language: Locale | None
    tags: list[Tag]
    calls: int
    last_contact_at: datetime | None
    last_result: CallResult | None
    next_step: str | None


class CustomerList(ResponseModel):
    items: list[CustomerRow]
    total: int


class MemoryFactOut(ResponseModel):
    id: uuid.UUID
    key: str
    value: str
    status: MemoryStatus
    confidence: float
    source_call_id: uuid.UUID | None
    expires_at: datetime | None
    updated_at: datetime


class MemoryFactUpdate(PatchModel):
    """An owner edit. Editing a value makes it confirmed (the owner vouches for it)."""

    value: MemoryValue | None = None
    status: MemoryStatus | None = None


class CommitmentOut(ResponseModel):
    id: uuid.UUID
    kind: str
    description: str
    due_at: datetime | None
    status: CommitmentStatus


class TimelineEvent(ResponseModel):
    kind: Literal["call", "action", "commitment"]
    at: datetime
    title: str
    detail: str | None = None
    call_id: uuid.UUID | None = None
    result: CallResult | None = None


class CustomerDetail(CustomerRow):
    created_at: datetime
    memory: list[MemoryFactOut]
    commitments: list[CommitmentOut]
    timeline: list[TimelineEvent]


class ForgetOut(ResponseModel):
    id: uuid.UUID
    forgotten: Literal[True] = True
    calls_deleted: int
    memory_deleted: int
