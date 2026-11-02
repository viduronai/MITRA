from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from mitra_core.schemas.common import PatchModel, RequestModel, ResponseModel
from mitra_core.webhooks.enums import SUBSCRIBABLE, WebhookEvent

MAX_HEADERS = 10
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_HEADER_VALUE = re.compile(r"^[\x20-\x7e]{0,500}$")
_RESERVED = frozenset(
    {"host", "content-length", "content-type", "user-agent", "connection", "transfer-encoding"}
)


def _headers(value: dict[str, str]) -> dict[str, str]:
    if len(value) > MAX_HEADERS:
        raise ValueError(f"at most {MAX_HEADERS} custom headers")
    seen: set[str] = set()
    for name, val in value.items():
        low = name.lower()
        if not _HEADER_NAME.fullmatch(name) or low in _RESERVED or low.startswith("x-mitra-"):
            raise ValueError(f"header name not allowed: {name[:64]}")
        if low in seen:
            raise ValueError(f"duplicate header: {name[:64]}")
        seen.add(low)
        if not _HEADER_VALUE.fullmatch(val):
            raise ValueError(f"header value not allowed for {name[:64]}")
    return value


def _events(value: list[WebhookEvent]) -> list[WebhookEvent]:
    if any(e not in SUBSCRIBABLE for e in value):
        raise ValueError("unknown event")
    if len(set(value)) != len(value):
        raise ValueError("events must be unique")
    return value


Url = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2048)]
Headers = Annotated[dict[str, str], AfterValidator(_headers)]
Events = Annotated[list[WebhookEvent], Field(min_length=1, max_length=3), AfterValidator(_events)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class WebhookIn(RequestModel):
    url: Url
    events: Events
    description: Description | None = None
    headers: Headers = Field(default_factory=dict)


class WebhookPatch(PatchModel):
    _nullable = frozenset({"description"})

    url: Url | None = None
    events: Events | None = None
    description: Description | None = None
    headers: Headers | None = None
    enabled: bool | None = None


class WebhookOut(ResponseModel):
    id: uuid.UUID
    url: str
    description: str | None
    events: list[str]
    secret_hint: str
    secret: str | None = None  # only right after creation / rotation
    headers: dict[str, str]
    enabled: bool
    consecutive_failures: int
    last_delivery_at: datetime | None = None
    last_delivery_ok: bool | None = None
    created_at: datetime


class WebhookList(ResponseModel):
    items: list[WebhookOut]
    events: list[str]


class DeliveryOut(ResponseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_id: uuid.UUID
    event: str
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_attempt_at: datetime | None
    response_status: int | None
    error: str | None
    duration_ms: int | None
    created_at: datetime


class DeliveryList(ResponseModel):
    items: list[DeliveryOut]
