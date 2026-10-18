from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, ClassVar, Self

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from mitra_core.catalog import VOICES_BY_ID
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


def _known_voice(value: str) -> str:
    if value not in VOICES_BY_ID:
        raise ValueError("unknown voice_id (see GET /v1/catalog/voices)")
    return value


VoiceId = Annotated[str, StringConstraints(max_length=64), AfterValidator(_known_voice)]
Greeting = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
BehaviourItem = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
BehaviourList = Annotated[list[BehaviourItem], Field(max_length=20)]


class Behaviour(RequestModel):
    """How the employee behaves on calls. Replaced as a whole; omitted lists become empty."""

    ask_for: BehaviourList = Field(default_factory=list)
    never_say: BehaviourList = Field(default_factory=list)
    transfer_when: BehaviourList = Field(default_factory=list)


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
    _nullable: ClassVar[frozenset[str]] = frozenset({"working_hours", "voice_id", "greeting"})

    name: Name60 | None = None
    voice_tier: VoiceTier | None = None
    status: EmployeeStatus | None = None
    languages: Languages | None = None
    working_hours: WorkingHours | None = None
    # Setting a voice also sets voice_tier to that voice's tier (billing follows the voice).
    voice_id: VoiceId | None = None
    greeting: Greeting | None = None
    behaviour: Behaviour | None = None


class EmployeeOut(ResponseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    role_template: RoleTemplate
    voice_tier: VoiceTier
    status: EmployeeStatus
    languages: list[Locale]
    working_hours: WorkingHours | None
    voice_id: str | None
    greeting: str | None
    behaviour: Behaviour
    created_at: datetime
    updated_at: datetime


class EmployeeList(ResponseModel):
    items: list[EmployeeOut]
