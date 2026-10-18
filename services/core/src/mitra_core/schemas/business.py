from __future__ import annotations

import uuid
from datetime import datetime
from functools import lru_cache
from typing import Annotated, ClassVar, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, Field

from mitra_core.models.enums import Industry, Locale, MemberRole
from mitra_core.schemas.common import (
    City,
    Languages,
    Name120,
    PatchModel,
    RequestModel,
    ResponseModel,
)


@lru_cache(maxsize=1)
def _timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def _valid_timezone(value: str) -> str:
    if value not in _timezones():
        raise ValueError("unknown IANA timezone")
    return value


Timezone = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(_valid_timezone)]


class BusinessCreate(RequestModel):
    name: Name120
    industry: Industry
    city: City | None = None
    languages: Languages = Field(default_factory=lambda: [Locale.EN])
    timezone: Timezone = "Asia/Kolkata"


class BusinessUpdate(PatchModel):
    _nullable: ClassVar[frozenset[str]] = frozenset({"city"})

    name: Name120 | None = None
    industry: Industry | None = None
    city: City | None = None
    languages: Languages | None = None
    timezone: Timezone | None = None


class BusinessOut(ResponseModel):
    id: uuid.UUID
    agency_id: uuid.UUID | None
    name: str
    industry: Industry
    city: str | None
    languages: list[Locale]
    timezone: str
    created_at: datetime
    updated_at: datetime


class MembershipOut(ResponseModel):
    business_id: uuid.UUID
    business_name: str
    role: MemberRole


class BusinessCreated(ResponseModel):
    business: BusinessOut
    membership: MembershipOut
    # A token scoped to the new business (minted fresh on idempotent replays, never stored).
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  (not a secret)
    expires_in: int
