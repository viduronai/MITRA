from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from mitra_core.leads.enums import LeadSourceKind, LeadStatus
from mitra_core.schemas.common import PatchModel, ResponseModel


class IntakeOut(ResponseModel):
    lead_id: uuid.UUID
    status: LeadStatus
    duplicate: bool
    call_at: datetime | None = None


class IntakeUrls(ResponseModel):
    generic: str
    form: str
    google_ads: str
    indiamart: str
    justdial: str
    meta_webhook: str


class LeadSourceOut(ResponseModel):
    kind: LeadSourceKind
    connected: bool  # a row exists (set up, or a lead already arrived)
    enabled: bool = True
    auto_call: bool = True
    call_delay_seconds: int = 0
    heads_up: bool = False
    employee_id: uuid.UUID | None = None
    external_id: str | None = None
    credential_hint: str | None = None
    last_lead_at: datetime | None = None
    last_pulled_at: datetime | None = None
    lead_count: int = 0
    last_error: str | None = None
    simulated: bool = False  # the portal side is a simulator (no real account connected)
    # Lead consent policy: "form_checkbox" | "portal_enquiry" | "owner_attestation".
    consent_policy: str = "owner_attestation"
    attested_at: datetime | None = None  # owner_attestation sources only
    attested_by: str | None = None


class LeadSetupOut(ResponseModel):
    enabled: bool
    slug: str | None = None
    secret_hint: str | None = None
    # Present only in the response that created or rotated it: shown to the owner once.
    secret: str | None = None
    rotated_at: datetime | None = None
    previous_valid_until: datetime | None = None
    dedupe_minutes: int = 10
    urls: IntakeUrls | None = None
    sources: list[LeadSourceOut] = Field(default_factory=list)
    # Exact checkbox / attestation wording per language (en, hi, te), for snippets and the UI.
    consent_version: str
    consent_texts: dict[str, str] = Field(default_factory=dict)
    attestation_texts: dict[str, str] = Field(default_factory=dict)


class LeadSetupPatch(PatchModel):
    dedupe_minutes: int | None = Field(None, ge=0, le=1440)


ExternalId = Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z_.-]{1,64}$")]
Credential = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=400)]


class LeadSourcePatch(PatchModel):
    _nullable = frozenset({"employee_id", "external_id", "credential"})

    enabled: bool | None = None
    auto_call: bool | None = None
    # AUTO-02 choices: within 1 minute (0), 5 min, 15 min, 1 hour, next morning-ish (1 day).
    call_delay_seconds: int | None = Field(None, ge=0, le=86400)
    heads_up: bool | None = None
    employee_id: uuid.UUID | None = None
    external_id: ExternalId | None = None  # Meta page id
    credential: Credential | None = None  # IndiaMART CRM key / Meta page token (write-only)
    # Generic sources: the owner confirms "These people asked to be contacted..." (or withdraws).
    consent_attested: bool | None = None
    attestation_lang: Literal["en", "hi", "te"] | None = None


class LeadOut(ResponseModel):
    id: uuid.UUID
    source: LeadSourceKind
    source_detail: str | None
    name: str | None
    phone_last4: str
    fields: dict[str, str]
    status: LeadStatus
    reasons: list[str]
    reason_text: list[str]
    employee_id: uuid.UUID | None
    call_at: datetime | None
    received_at: datetime
    duplicate_of: uuid.UUID | None


class LeadList(ResponseModel):
    items: list[LeadOut]


class TestLeadOut(ResponseModel):
    lead: LeadOut
    duplicate: bool


class PullOut(ResponseModel):
    fetched: int
    created: int
    duplicates: int
    error: str | None = None
