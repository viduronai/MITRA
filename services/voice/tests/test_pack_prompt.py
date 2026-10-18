from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from mitra_voice.config import Settings
from mitra_voice.logging import redact_phones
from mitra_voice.pack import (
    FIXTURES_DIR,
    SCENARIO_FIXTURES,
    CorePackUnavailableError,
    load_fixture,
    load_pack,
    pack_from_dict,
)
from mitra_voice.prompt import GLOBAL_RULES, build_prompt, greeting_for

CLINIC = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")


def _pack(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "business_id": "b",
        "business_name": "Sunrise Clinic",
        "industry": "clinic",
        "employee_id": "e",
        "employee_name": "Priya",
        "role_template": "receptionist",
        "languages": ["te", "en"],
    }
    return {**base, **overrides}


def test_all_scenario_fixtures_load() -> None:
    for name in SCENARIO_FIXTURES.values():
        pack = load_fixture(FIXTURES_DIR / name)
        assert pack.facts
        assert pack.find_fact("prices") is not None


def test_pack_validation_rejects_bad_data() -> None:
    with pytest.raises(ValidationError):
        pack_from_dict(_pack(languages=[]))
    with pytest.raises(ValidationError):
        pack_from_dict(_pack(languages=["ta"]))
    with pytest.raises(ValidationError):
        pack_from_dict(_pack(facts=[{"category": "gossip", "key": "k", "value": "v"}]))
    with pytest.raises(ValidationError):
        pack_from_dict(_pack(greeting="x" * 301))


def test_prompt_sections_are_ordered_static_first() -> None:
    prompt = build_prompt(CLINIC).system_prompt()
    assert prompt.startswith(GLOBAL_RULES)
    headers = ("\n\nROLE\n", "\n\nCONFIRMED FACTS\n", "\n\nCUSTOMER MEMORY\n")
    role, facts, memory = (prompt.index(h) for h in headers)
    assert role < facts < memory
    assert "You are Priya, the receptionist at Sunrise Clinic" in prompt
    assert "- [prices] Consultation fee: ₹500" in prompt
    assert "Before booking, ask for: the patient's name" in prompt
    assert "knowledge version fixture-2026-10-18" in prompt
    assert "New caller" in prompt
    assert "returning caller" in build_prompt(CLINIC, "A returning caller.").customer_memory


def test_greeting_discloses_ai_in_each_language() -> None:
    te = greeting_for(CLINIC)
    assert te.startswith("Namaskaram, Sunrise Clinic nunchi Priya, AI assistant ni")
    assert "record" in te
    assert "an AI assistant" in greeting_for(CLINIC, "en")
    hi = greeting_for(CLINIC, "hi")
    assert "AI assistant" in hi
    assert hi.endswith("sakti hoon?")
    male = pack_from_dict(_pack(employee_name="Arjun", voice_gender="male"))
    assert greeting_for(male, "hi").endswith("sakta hoon?")


def test_custom_greeting_gets_the_disclosure_appended() -> None:
    custom = pack_from_dict(_pack(greeting="Welcome to Sunrise Clinic!", languages=["en"]))
    assert greeting_for(custom) == (
        "Welcome to Sunrise Clinic! I'm an AI assistant, and this call may be recorded."
    )
    disclosed = pack_from_dict(_pack(greeting="Hi, I'm Priya, the clinic's AI receptionist."))
    assert greeting_for(disclosed) == "Hi, I'm Priya, the clinic's AI receptionist."


async def test_load_pack_uses_fixture_without_core() -> None:
    pack = await load_pack(Settings(), "real_estate")
    assert pack.business_name == "Greenfield Homes"


async def test_core_pack_stub_falls_back_only_in_local() -> None:
    core = {"mitra_core_url": "http://localhost:8000", "mitra_core_service_token": "t"}
    local = await load_pack(Settings(**core), "clinic", employee_id="emp-1")  # type: ignore[arg-type]
    assert local.business_name == "Sunrise Clinic"
    with pytest.raises(CorePackUnavailableError):
        await load_pack(Settings(mitra_env="dev", **core), "clinic", employee_id="emp-1")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("call me on 98765 43210 please", "call me on [phone] please"),
        ("my number is +91-98765-43210.", "my number is [phone]."),
        ("landline 040 2345 6789", "landline [phone]"),
        ("fee is ₹500 at 5 PM", "fee is ₹500 at 5 PM"),
        ("Plot 12, Road No. 3", "Plot 12, Road No. 3"),
    ],
)
def test_phone_numbers_are_redacted_from_logged_text(text: str, expected: str) -> None:
    assert redact_phones(text) == expected
