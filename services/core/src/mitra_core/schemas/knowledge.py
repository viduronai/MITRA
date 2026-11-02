from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyUrl, Field, StringConstraints, UrlConstraints

from mitra_core.models.enums import (
    FactCategory,
    FactStatus,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from mitra_core.schemas.common import PatchModel, RequestModel, ResponseModel

HttpUrl = Annotated[
    AnyUrl, UrlConstraints(max_length=2048, allowed_schemes=["http", "https"], host_required=True)
]
FactKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
FactValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
SourceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]


class UrlSourceIn(RequestModel):
    type: Literal[KnowledgeSourceType.URL]
    url: HttpUrl


class TextSourceIn(RequestModel):
    type: Literal[KnowledgeSourceType.TEXT]
    text: SourceText


SourceIn = Annotated[UrlSourceIn | TextSourceIn, Field(discriminator="type")]


class SourceOut(ResponseModel):
    id: uuid.UUID
    type: KnowledgeSourceType
    status: KnowledgeSourceStatus
    title: str | None
    url: str | None
    error: str | None
    created_at: datetime


class FactIn(RequestModel):
    category: FactCategory
    key: FactKey
    value: FactValue


class FactUpdate(PatchModel):
    value: FactValue | None = None
    status: FactStatus | None = None


class FactOut(ResponseModel):
    id: uuid.UUID
    category: FactCategory
    key: str
    value: str
    source_id: uuid.UUID | None
    status: FactStatus


class GapOut(ResponseModel):
    category: FactCategory
    key: str
    question: str
    # "checklist": industry must-know; "call": a caller asked and the employee had no answer.
    source: Literal["checklist", "call"] = "checklist"
    call_id: uuid.UUID | None = None
