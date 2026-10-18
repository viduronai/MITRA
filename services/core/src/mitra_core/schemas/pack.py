from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field

from mitra_core.models.enums import FactCategory, Industry, Locale, RoleTemplate, VoiceTier
from mitra_core.schemas.common import ResponseModel


class PackFact(ResponseModel):
    category: FactCategory
    key: str
    value: str


class PackBehaviour(ResponseModel):
    ask_for: list[str] = Field(default_factory=list)
    never_say: list[str] = Field(default_factory=list)
    transfer_when: list[str] = Field(default_factory=list)


class EmployeePackOut(ResponseModel):
    """Mirrors ``services/voice/src/mitra_voice/pack.py:EmployeePack`` (plus extra context)."""

    business_id: uuid.UUID
    business_name: str
    industry: Industry
    city: str | None
    business_languages: list[Locale]
    employee_id: uuid.UUID
    employee_name: str
    role_template: RoleTemplate
    languages: list[Locale]
    voice_id: str | None
    voice_tier: VoiceTier
    voice_gender: Literal["female", "male"]
    # The full opening line, AI disclosure included (``simulation.opening_line``).
    greeting: str
    behaviour: PackBehaviour
    working_hours: dict[str, Any] | None
    facts: list[PackFact]
    # Changes whenever anything above changes; use it as the prompt-cache key.
    knowledge_version: str
