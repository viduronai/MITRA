from __future__ import annotations

from typing import Any

import httpx
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
    load_pack_from_core,
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


async def test_core_unavailable_falls_back_only_in_local(monkeypatch: pytest.MonkeyPatch) -> None:
    async def down(*_: object, **__: object) -> None:
        raise CorePackUnavailableError("core answered 503")

    monkeypatch.setattr("mitra_voice.pack.load_pack_from_core", down)
    core = {"mitra_core_url": "http://core.test", "mitra_core_service_token": "t"}
    local = await load_pack(Settings(**core), "clinic", employee_id="emp-1")  # type: ignore[arg-type]
    assert local.business_name == "Sunrise Clinic"
    with pytest.raises(CorePackUnavailableError):
        await load_pack(Settings(mitra_env="dev", **core), "clinic", employee_id="emp-1")  # type: ignore[arg-type]


CORE_PACK = {  # shape of services/core GET /internal/v1/employees/{id}/pack
    "business_id": "6f1c0d2e-0000-4000-8000-000000000001",
    "business_name": "Sunrise Clinic",
    "industry": "clinic",
    "city": "Hyderabad",
    "business_languages": ["te", "en"],
    "employee_id": "363eb7a7-0cce-4bd9-8ddd-425d641cdfec",
    "employee_name": "Priya",
    "role_template": "receptionist",
    "languages": ["te", "en"],
    "voice_id": "priya-te-hyd",
    "voice_tier": "natural",
    "voice_gender": "female",
    "greeting": "Namaste! Thank you for calling Sunrise Clinic. This is Priya, an AI assistant. "
    "This call may be recorded.",
    "behaviour": {"ask_for": [], "never_say": [], "transfer_when": []},
    "working_hours": None,
    "facts": [{"category": "prices", "key": "Consultation fee", "value": "₹500"}],
    "knowledge_version": "0123456789abcdef",
}


async def test_load_pack_from_core_sends_the_service_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=CORE_PACK)

    pack = await load_pack_from_core(
        "http://core.test/",
        "svc-token",
        CORE_PACK["employee_id"],  # type: ignore[arg-type]
        transport=httpx.MockTransport(handler),
    )
    assert seen[0].url.path == f"/internal/v1/employees/{CORE_PACK['employee_id']}/pack"
    assert seen[0].headers["authorization"] == "Bearer svc-token"
    assert pack.employee_name == "Priya"
    assert pack.knowledge_version == "0123456789abcdef"
    assert pack.facts[0].value == "₹500"
    # Core's greeting already discloses AI + recording: spoken as-is, nothing appended.
    assert greeting_for(pack) == CORE_PACK["greeting"]


@pytest.mark.parametrize("status", [401, 404, 503])
async def test_core_errors_are_unavailable(status: int) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json={"error": "x"}))
    with pytest.raises(CorePackUnavailableError, match=str(status)):
        await load_pack_from_core("http://core.test", "t", "e", transport=transport)


async def test_unreachable_core_is_unavailable() -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(CorePackUnavailableError, match="unreachable"):
        await load_pack_from_core(
            "http://core.test", "t", "e", transport=httpx.MockTransport(refuse)
        )


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
