"""API shapes for the AI team, hand-offs, staff, routines and live calls."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import Field, StringConstraints

from mitra_core.models.enums import EmployeeStatus, Locale, RoleTemplate
from mitra_core.schemas.common import (
    E164Phone,
    Languages,
    Name60,
    PatchModel,
    RequestModel,
    ResponseModel,
)
from mitra_core.team.routines.spec import EventName, RoutineSpec

Text300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Task = Literal[
    "book_visit",
    "remind_appointment",
    "follow_up",
    "collect_payment",
    "feedback",
    "send_report",
    "call_back",
    "brief_staff",
]
Channel = Literal["call", "whatsapp", "whatsapp_then_call"]
RuleResult = Literal["booked", "interested", "call_back", "not_interested", "info_only", "missed"]

# --- templates & hire ---------------------------------------------------------------------------


class TemplateRoleOut(ResponseModel):
    id: str
    name: str
    title: str
    base_role: RoleTemplate
    voice_id: str


class TemplateRuleOut(ResponseModel):
    from_role: str
    when_result: str
    to_role: str | None
    task: str
    channel: str
    delay_minutes: int


class TeamTemplateOut(ResponseModel):
    id: str
    industry: str
    name: str
    recommended: bool
    roles: list[TemplateRoleOut]
    rules: list[TemplateRuleOut]


class HireTeamIn(RequestModel):
    template_id: Literal["real_estate", "clinic", "coaching"]
    languages: Languages | None = None
    names: dict[str, Name60] = Field(default_factory=dict, max_length=8)
    # Reuse an employee hired during onboarding for the matching base role (no duplicate).
    reuse_existing: bool = True


# --- map -----------------------------------------------------------------------------------------


class MemberOut(ResponseModel):
    employee_id: uuid.UUID
    name: str
    team_role: str
    base_role: RoleTemplate
    status: EmployeeStatus
    position: int
    calls_7d: int = 0
    received_7d: int = 0
    waiting: int = 0


class RuleOut(ResponseModel):
    id: uuid.UUID
    team_id: uuid.UUID | None
    from_employee_id: uuid.UUID
    when_result: str
    condition: dict[str, Any]
    to_employee_id: uuid.UUID | None
    task: str
    channel: str
    delay_minutes: int
    enabled: bool
    version: int
    handoffs_7d: int = 0


class TeamOut(ResponseModel):
    id: uuid.UUID
    name: str
    template_id: str | None
    active: bool
    members: list[MemberOut]
    rules: list[RuleOut]


class TeamMapOut(ResponseModel):
    teams: list[TeamOut]
    # Employees not in any team, so a solo employee from onboarding still shows on the map.
    others: list[MemberOut]


class RuleCondition(RequestModel):
    field: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    op: Literal["present", "equals", "contains"] = "present"
    value: Annotated[str, StringConstraints(max_length=80)] | None = None


class RuleIn(RequestModel):
    team_id: uuid.UUID | None = None
    from_employee_id: uuid.UUID
    when_result: RuleResult
    condition: RuleCondition | None = None
    to_employee_id: uuid.UUID | None = None
    task: Task
    channel: Channel = "call"
    delay_minutes: int = Field(default=10, ge=0, le=10080)
    enabled: bool = True


class RulePatch(PatchModel):
    _nullable: ClassVar[frozenset[str]] = frozenset({"condition", "to_employee_id"})

    when_result: RuleResult | None = None
    condition: RuleCondition | None = None
    to_employee_id: uuid.UUID | None = None
    task: Task | None = None
    channel: Channel | None = None
    delay_minutes: int | None = Field(default=None, ge=0, le=10080)
    enabled: bool | None = None


class TaskOut(ResponseModel):
    id: uuid.UUID
    kind: str
    task: str
    channel: str
    status: str
    due_at: datetime
    contact_id: uuid.UUID | None
    customer_name: str | None = None
    from_employee_id: uuid.UUID | None
    to_employee_id: uuid.UUID | None
    source_call_id: uuid.UUID | None
    created_at: datetime


# --- staff & hand-off cards ----------------------------------------------------------------------


class StaffIn(RequestModel):
    name: Name60
    phone_e164: E164Phone
    role_label: Annotated[str, StringConstraints(max_length=60)] | None = None
    ladder_position: int | None = Field(default=None, ge=1, le=9)
    ring_timeout_s: int = Field(default=20, ge=5, le=60)
    receives_briefs: bool = True
    is_owner: bool = False


class StaffPatch(PatchModel):
    _nullable: ClassVar[frozenset[str]] = frozenset({"role_label", "ladder_position"})

    name: Name60 | None = None
    phone_e164: E164Phone | None = None
    role_label: Annotated[str, StringConstraints(max_length=60)] | None = None
    ladder_position: int | None = Field(default=None, ge=1, le=9)
    ring_timeout_s: int | None = Field(default=None, ge=5, le=60)
    receives_briefs: bool | None = None
    is_owner: bool | None = None
    active: bool | None = None


class StaffOut(ResponseModel):
    id: uuid.UUID
    name: str
    phone_e164: str
    role_label: str | None
    ladder_position: int | None
    ring_timeout_s: int
    receives_briefs: bool
    is_owner: bool
    active: bool


class HandoffCardOut(ResponseModel):
    id: uuid.UUID
    call_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    employee_id: uuid.UUID | None
    caller_last4: str | None
    reason: str
    message: str
    callback_by: datetime | None
    attempts: list[dict[str, Any]]
    status: str
    created_at: datetime
    resolved_at: datetime | None


# --- routines ------------------------------------------------------------------------------------


class LibraryRoutineOut(ResponseModel):
    id: str
    name: str
    trigger: dict[str, Any]
    audience: str | None
    goal: str
    verb: str
    employee_id: uuid.UUID | None


class RoutineIn(RequestModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    spec: RoutineSpec
    enabled: bool = False


class FromLibraryIn(RequestModel):
    library_id: Annotated[str, StringConstraints(max_length=40)]
    employee_id: uuid.UUID | None = None
    enabled: bool = False


class RoutinePatch(PatchModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    spec: RoutineSpec | None = None
    enabled: bool | None = None


class RoutineOut(ResponseModel):
    id: uuid.UUID
    name: str
    library_id: str | None
    spec: dict[str, Any]
    sentence: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None


class DryRunIn(RequestModel):
    spec: RoutineSpec


class PersonOut(ResponseModel):
    contact_id: uuid.UUID
    name: str | None
    last4: str
    skip: str | None = None


class DryRunOut(ResponseModel):
    sentence: str
    would_contact: list[PersonOut]
    skipped: list[PersonOut]
    needs_approval: bool
    note: str | None = None


class RunOut(ResponseModel):
    id: uuid.UUID
    routine_id: uuid.UUID
    trigger: str
    status: str
    audience_count: int
    contacted_count: int
    skipped: dict[str, int]
    contacts: list[dict[str, Any]]
    started_at: datetime
    finished_at: datetime | None


class DecisionIn(RequestModel):
    approved: bool


class EventIn(RequestModel):
    event: EventName
    contact_id: uuid.UUID


# --- live calls ----------------------------------------------------------------------------------


class LiveCallOut(ResponseModel):
    id: uuid.UUID
    employee_id: uuid.UUID | None
    employee_name: str | None
    direction: str
    phone_last4: str | None
    customer_name: str | None = None
    started_at: datetime
    language: Locale | None


class LiveTurnOut(ResponseModel):
    seq: int
    role: str
    text: str


class LiveDetailOut(ResponseModel):
    call: LiveCallOut
    live: bool
    turns: list[LiveTurnOut]
    whispers: list[dict[str, Any]]


class WhisperIn(RequestModel):
    text: Text300


# --- internal (voice service) -------------------------------------------------------------------


class LadderStepOut(ResponseModel):
    name: str
    phone_e164: str
    ring_timeout_s: int
    is_owner: bool


class LadderOut(ResponseModel):
    steps: list[LadderStepOut]
    callback_by: datetime
    callback_local: str
    callback_day: Literal["today", "tomorrow"]


class CardIn(RequestModel):
    employee_id: uuid.UUID
    call_id: uuid.UUID | None = None
    caller_phone: E164Phone | None = None
    reason: Annotated[str, StringConstraints(max_length=300)] = ""
    message: Annotated[str, StringConstraints(max_length=1000)] = ""
    attempts: list[dict[str, Any]] = Field(default_factory=list, max_length=5)


class CardCreatedOut(ResponseModel):
    id: uuid.UUID
    callback_by: datetime | None


class LiveTurnIn(RequestModel):
    employee_id: uuid.UUID
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(max_length=2000)]


class InstructionsOut(ResponseModel):
    instructions: list[dict[str, Any]]
