"""Campaign API schemas (CALL-15) and dialer settings (CALL-09)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from mitra_core.dialer.enums import CampaignStatus, ContactStatus, ResultBucket
from mitra_core.models.enums import Locale
from mitra_core.schemas.common import E164Phone, RequestModel
from mitra_core.telephony.enums import AttemptOutcome, CallPurpose, ConsentScope

ListText = Annotated[str, Field(min_length=1, max_length=2_000_000)]
Ladder = Annotated[list[Annotated[int, Field(ge=5, le=7 * 24 * 60)]], Field(max_length=6)]
Weekdays = Annotated[list[Annotated[int, Field(ge=0, le=6)]], Field(min_length=1, max_length=7)]
Holidays = Annotated[list[date], Field(max_length=60)]
CampaignPurpose = CallPurpose  # promotional stays blocked by compliance unless enabled


class ListIn(RequestModel):
    text: ListText
    phone_column: str | None = None
    name_column: str | None = None
    column_map: dict[str, str] | None = None


class RowErrorOut(BaseModel):
    row_number: int
    reason: str


class SampleRow(BaseModel):
    row_number: int
    phone_last4: str
    name: str | None
    variables: dict[str, str]


class ListPreviewOut(BaseModel):
    headers: list[str]
    phone_column: str
    name_column: str | None
    column_map: dict[str, str]
    valid: int
    invalid: int
    duplicates: int
    errors: list[RowErrorOut]
    sample: list[SampleRow]


class CampaignIn(ListIn):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    employee_id: uuid.UUID
    purpose: CampaignPurpose = CallPurpose.SERVICE
    skip_recent_days: Annotated[int, Field(ge=0, le=90)] = 7
    calling_days: Weekdays = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    holidays: Holidays = Field(default_factory=list)
    retry_ladder: Ladder = Field(default_factory=lambda: [30, 120, 1440])
    ends_on: date | None = None
    # The owner's list attestation (docs/08 section 8.5); without it the campaign cannot start.
    consent_attested: bool = False
    consent_language: Locale | None = None


class ConsentIn(RequestModel):
    """Start / add people: the owner's tick, in their language (exact words are stored)."""

    consent_attested: bool = False
    consent_language: Locale | None = None


class ExtendIn(ListIn):
    consent_attested: bool = False
    consent_language: Locale | None = None


class ConsentOut(BaseModel):
    scope: ConsentScope
    text: str
    text_version: str
    by_name: str | None
    at: datetime


class ConsentTextOut(BaseModel):
    """The words the owner will tick for a list of this purpose, in their language."""

    text: str
    version: str


class CampaignPatch(RequestModel):
    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    employee_id: uuid.UUID | None = None
    calling_days: Weekdays | None = None
    holidays: Holidays | None = None
    retry_ladder: Ladder | None = None
    ends_on: date | None = None
    avg_call_seconds: Annotated[int, Field(ge=15, le=1800)] | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("nothing to update")
        return self


class Progress(BaseModel):
    total: int
    called: int  # dialled at least once
    blocked: int  # stopped by compliance before any call
    skipped: int
    remaining: int
    dialing: int
    done: int
    buckets: dict[str, int]
    reasons: dict[str, int]
    blocked_summary: list[str]
    eta_minutes: int | None
    channels: int


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    employee_id: uuid.UUID | None
    employee_name: str | None
    purpose: CallPurpose
    status: CampaignStatus
    pause_reason: str | None
    column_map: dict[str, str]
    variables: list[str]
    skip_recent_days: int
    calling_days: list[int]
    holidays: list[date]
    retry_ladder: list[int]
    ends_on: date | None
    avg_call_seconds: int
    approval_id: uuid.UUID | None
    consent: ConsentOut | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    progress: Progress


class CampaignCreatedOut(BaseModel):
    campaign: CampaignOut
    added: int
    skipped_recent: int
    invalid: int
    duplicates: int


class CampaignList(BaseModel):
    items: list[CampaignOut]


class ContactsAddedOut(BaseModel):
    added: int
    skipped_recent: int
    invalid: int
    duplicates: int
    campaign: CampaignOut


class ContactOut(BaseModel):
    id: uuid.UUID
    row_number: int
    name: str | None
    phone_last4: str
    status: ContactStatus
    bucket: ResultBucket | None
    reasons: list[str]
    attempts: int
    last_outcome: AttemptOutcome | None
    last_called_at: datetime | None
    call_id: uuid.UUID | None
    summary: str | None


class ContactList(BaseModel):
    items: list[ContactOut]
    total: int


class DialerSettingsOut(BaseModel):
    channels: int


class DialerSettingsIn(RequestModel):
    channels: Annotated[int, Field(ge=1, le=50)]


class CallbackIn(RequestModel):
    """Internal: the voice brain's ``schedule_callback`` tool (CALL-05)."""

    business_id: uuid.UUID
    employee_id: uuid.UUID
    contact_phone: E164Phone
    at: datetime
    note: Annotated[str, Field(max_length=200)] | None = None
    contact_name: Annotated[str, Field(max_length=120)] | None = None
    called_number_id: uuid.UUID | None = None


class CallbackOut(BaseModel):
    job_id: uuid.UUID
    not_before: datetime
    status: str


class TickOut(BaseModel):
    businesses: int
    dialed: int
    deferred: int
    blocked: int
    finished: int
    paused_campaigns: list[uuid.UUID]
