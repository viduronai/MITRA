from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, ClassVar, Self

from pydantic import Field, StringConstraints, model_validator

from mitra_core.models.enums import EmployeeStatus, Locale, RoleTemplate, VoiceTier
from mitra_core.schemas.common import Languages, Name60, PatchModel, RequestModel, ResponseModel

HHMM = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class TimeRange(RequestModel):
    start: HHMM
    end: HHMM

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


DayRanges = Annotated[list[TimeRange], Field(max_length=4)]


class WorkingHours(RequestModel):
    """Weekly schedule in the business's timezone; a missing day means closed."""

    mon: DayRanges | None = None
    tue: DayRanges | None = None
    wed: DayRanges | None = None
    thu: DayRanges | None = None
    fri: DayRanges | None = None
    sat: DayRanges | None = None
    sun: DayRanges | None = None


class EmployeeCreate(RequestModel):
    name: Name60
    role_template: RoleTemplate
    voice_tier: VoiceTier = VoiceTier.NATURAL
    languages: Languages
    working_hours: WorkingHours | None = None


class EmployeeUpdate(PatchModel):
    _nullable: ClassVar[frozenset[str]] = frozenset({"working_hours"})

    name: Name60 | None = None
    voice_tier: VoiceTier | None = None
    status: EmployeeStatus | None = None
    languages: Languages | None = None
    working_hours: WorkingHours | None = None


class EmployeeOut(ResponseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    role_template: RoleTemplate
    voice_tier: VoiceTier
    status: EmployeeStatus
    languages: list[Locale]
    working_hours: WorkingHours | None
    created_at: datetime
    updated_at: datetime


class EmployeeList(ResponseModel):
    items: list[EmployeeOut]
