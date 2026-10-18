"""Employee pack: everything a live call needs about the business and the employee, loaded once
at call start (WORKFLOWS §3, step 4) so nothing blocks the hot path.

Fields mirror services/core: ``employee`` (name, role_template, languages, voice_id, greeting,
behaviour) and confirmed ``fact`` rows (category, key, value).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import structlog
from pydantic import Field, TypeAdapter
from pydantic.dataclasses import dataclass

from mitra_voice.config import SERVICE_ROOT, Settings

log = structlog.get_logger(__name__)

Lang = Literal["en", "hi", "te"]
Industry = Literal["clinic", "real_estate", "education", "other"]
FactCategory = Literal["services", "prices", "timings", "location", "contact", "faq", "policy"]
Scenario = Literal["clinic", "real_estate"]

FIXTURES_DIR = SERVICE_ROOT / "fixtures"
SCENARIO_FIXTURES: dict[Scenario, str] = {
    "clinic": "sunrise-clinic.json",
    "real_estate": "greenfield-realty.json",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Fact:
    category: FactCategory
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=500)


@dataclass(frozen=True, slots=True, kw_only=True)
class Behaviour:
    ask_for: list[str] = Field(default_factory=list)
    never_say: list[str] = Field(default_factory=list)
    transfer_when: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmployeePack:
    business_id: str
    business_name: str = Field(min_length=1, max_length=200)
    industry: Industry
    employee_id: str
    employee_name: str = Field(min_length=1, max_length=60)
    role_template: str
    languages: list[Lang] = Field(min_length=1)
    voice_id: str | None = None
    voice_gender: Literal["female", "male"] = "female"
    greeting: str | None = Field(default=None, max_length=300)
    behaviour: Behaviour = Field(default_factory=Behaviour)
    facts: list[Fact] = Field(default_factory=list)
    knowledge_version: str = "unversioned"

    @property
    def default_language(self) -> Lang:
        return self.languages[0]

    def find_fact(self, category: FactCategory, keywords: tuple[str, ...] = ()) -> Fact | None:
        """First fact in ``category`` whose key/value mentions a keyword (or the first at all)."""
        candidates = [f for f in self.facts if f.category == category]
        for fact in candidates:
            text = f"{fact.key} {fact.value}".lower()
            if any(k in text for k in keywords):
                return fact
        return candidates[0] if candidates and not keywords else None


_PACK_ADAPTER = TypeAdapter(EmployeePack)


def pack_from_dict(data: object) -> EmployeePack:
    """Validate untrusted pack data (fixture file or core response)."""
    return _PACK_ADAPTER.validate_python(data)


def load_fixture(path: Path) -> EmployeePack:
    return pack_from_dict(json.loads(path.read_text(encoding="utf-8")))


class CorePackUnavailableError(RuntimeError):
    pass


async def load_pack_from_core(core_url: str, service_token: str, employee_id: str) -> EmployeePack:
    """Load the pack from services/core. Not available yet.

    TODO(core): core has no service-to-service auth or pack endpoint. Needed:
      ``GET /internal/v1/employees/{employee_id}/pack`` authenticated with a service credential
      (signed service JWT or mTLS, not a user OTP token). It must resolve the employee's
      business, bind the RLS tenant (``app.business_id``) from it, and return the business
      name/industry, employee fields (name, role_template, languages, voice_id, greeting,
      behaviour), *confirmed* facts only, and a knowledge version for prompt-cache keys.
      Later: customer memory card by hashed caller phone (WORKFLOWS §3 step 3).
    """
    del core_url, service_token, employee_id
    raise CorePackUnavailableError("services/core has no internal pack endpoint yet")


async def load_pack(
    settings: Settings, scenario: Scenario, employee_id: str | None = None
) -> EmployeePack:
    """Core when configured and an employee id is given, else the scenario fixture.

    Outside ``local`` a configured-but-failing core load is an error, never a silent fixture.
    """
    if settings.mitra_core_url and settings.mitra_core_service_token and employee_id:
        try:
            return await load_pack_from_core(
                settings.mitra_core_url,
                settings.mitra_core_service_token.get_secret_value(),
                employee_id,
            )
        except CorePackUnavailableError:
            if not settings.is_local:
                raise
            log.warning("pack.core_unavailable_using_fixture", scenario=scenario)
    return load_fixture(FIXTURES_DIR / SCENARIO_FIXTURES[scenario])
