"""Internal employee pack for the voice service: service auth, tenancy, content."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import _DEV_SERVICE_TOKEN, Settings, get_settings
from mitra_core.main import app
from tests.helpers import add_fact, bearer, create_business, create_employee, new_actor

TOKEN = "test-service-token-0123456789abcdef"


def _configure(**overrides: Any) -> None:
    settings = Settings(**({"service_token": SecretStr(TOKEN)} | overrides))
    app.dependency_overrides[get_settings] = lambda: settings


async def _pack(client: httpx.AsyncClient, employee_id: str, token: str = TOKEN) -> httpx.Response:
    return await client.get(f"/internal/v1/employees/{employee_id}/pack", headers=bearer(token))


async def _tenant(client: httpx.AsyncClient, name: str, **employee: Any) -> dict[str, Any]:
    owner = new_actor()
    business = await create_business(client, owner, name=name)
    emp = await create_employee(client, owner, business["id"], **employee)
    return {"headers": owner.headers(business["id"]), "business": business, "employee": emp}


async def test_disabled_without_token_outside_local(client: httpx.AsyncClient) -> None:
    resp = await _pack(client, str(uuid.uuid4()), token="anything")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "internal_api_disabled"


async def test_rejects_missing_wrong_and_user_tokens(client: httpx.AsyncClient) -> None:
    _configure()
    t = await _tenant(client, "Sunrise Clinic")
    url = f"/internal/v1/employees/{t['employee']['id']}/pack"
    assert (await client.get(url)).status_code == 401
    assert (await _pack(client, t["employee"]["id"], token=TOKEN + "x")).status_code == 401
    assert (await _pack(client, t["employee"]["id"], token=_DEV_SERVICE_TOKEN)).status_code == 401
    user_resp = await client.get(url, headers=t["headers"])  # a valid USER token
    assert user_resp.status_code == 401
    # And the service token is not a user credential on the public API.
    assert (await client.get("/v1/me", headers=bearer(TOKEN))).status_code == 401


async def test_local_env_accepts_dev_placeholder(client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(env="local")
    t = await _tenant(client, "Sunrise Clinic")
    assert (await _pack(client, t["employee"]["id"], token=_DEV_SERVICE_TOKEN)).status_code == 200


def test_service_token_config_rules() -> None:
    secrets = {
        "jwt_secret": SecretStr("s" * 40),
        "phone_hash_key": SecretStr("p" * 40),
        "otp_hash_key": SecretStr("o" * 40),
    }
    assert Settings(env="prod", **secrets).effective_service_token is None  # disabled
    assert Settings(env="test").effective_service_token is None
    assert Settings(env="local").effective_service_token == _DEV_SERVICE_TOKEN
    with pytest.raises(ValidationError, match="dev placeholder"):
        Settings(env="prod", service_token=SecretStr(_DEV_SERVICE_TOKEN), **secrets)
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(env="dev", service_token=SecretStr("short"))
    assert Settings(env="prod", service_token=SecretStr(TOKEN), **secrets)


async def test_pack_contents_confirmed_facts_only(client: httpx.AsyncClient) -> None:
    _configure()
    t = await _tenant(
        client, "Sunrise Clinic", working_hours={"mon": [{"start": "09:00", "end": "18:00"}]}
    )
    h, emp = t["headers"], t["employee"]
    await client.patch(
        f"/v1/employees/{emp['id']}",
        json={"voice_id": "arjun-te-vij", "behaviour": {"never_say": ["Medical advice"]}},
        headers=h,
    )
    await add_fact(client, h, "prices", "Consultation fee", "₹500")
    hidden = await add_fact(client, h, "location", "Address", "Road No. 3, Madhapur")
    await client.patch(
        f"/v1/knowledge/facts/{hidden['id']}", json={"status": "suggested"}, headers=h
    )

    resp = await _pack(client, emp["id"])
    assert resp.status_code == 200, resp.text
    pack = resp.json()
    assert pack["business_id"] == t["business"]["id"]
    assert (pack["business_name"], pack["industry"], pack["city"]) == (
        "Sunrise Clinic",
        "clinic",
        "Hyderabad",
    )
    assert pack["business_languages"] == ["te", "en"]
    assert (pack["employee_id"], pack["employee_name"], pack["role_template"]) == (
        emp["id"],
        "Priya",
        "receptionist",
    )
    assert pack["languages"] == ["te", "en"]
    assert (pack["voice_id"], pack["voice_tier"], pack["voice_gender"]) == (
        "arjun-te-vij",
        "smart",
        "male",
    )
    assert pack["behaviour"] == {
        "ask_for": [],
        "never_say": ["Medical advice"],
        "transfer_when": [],
    }
    assert pack["working_hours"]["mon"] == [{"start": "09:00", "end": "18:00"}]
    assert pack["facts"] == [{"category": "prices", "key": "Consultation fee", "value": "₹500"}]
    assert len(pack["knowledge_version"]) == 16

    # Confirming the hidden fact changes both the facts and the version.
    await client.patch(
        f"/v1/knowledge/facts/{hidden['id']}", json={"status": "confirmed"}, headers=h
    )
    again = (await _pack(client, emp["id"])).json()
    assert len(again["facts"]) == 2
    assert again["knowledge_version"] != pack["knowledge_version"]
    assert (await _pack(client, emp["id"])).json()["knowledge_version"] == again[
        "knowledge_version"
    ]


@pytest.mark.parametrize(
    "greeting",
    [
        None,
        "Welcome to Sunrise Clinic, how may I help?",
        "Namaskaram! " + "Sunrise Clinic lo meeku swagatham. " * 8,  # long: no room for both
    ],
)
async def test_greeting_always_carries_disclosure(
    client: httpx.AsyncClient, greeting: str | None
) -> None:
    _configure()
    t = await _tenant(client, "Sunrise Clinic")
    if greeting:
        resp = await client.patch(
            f"/v1/employees/{t['employee']['id']}",
            json={"greeting": greeting[:300]},
            headers=t["headers"],
        )
        assert resp.status_code == 200, resp.text
    pack = (await _pack(client, t["employee"]["id"])).json()
    assert "an AI assistant from Sunrise Clinic" in pack["greeting"]
    assert "recorded" in pack["greeting"]
    assert len(pack["greeting"]) <= 300
    if greeting and len(greeting) < 100:
        assert pack["greeting"].endswith(greeting)


async def test_pack_is_scoped_to_the_employees_business(client: httpx.AsyncClient) -> None:
    _configure()
    a = await _tenant(client, "Clinic A")
    b = await _tenant(client, "Realty B")
    await add_fact(client, a["headers"], "faq", "Owner", "A only")
    await add_fact(client, b["headers"], "faq", "Owner", "B only")
    pack_b = (await _pack(client, b["employee"]["id"])).json()
    assert pack_b["business_name"] == "Realty B"
    assert [f["value"] for f in pack_b["facts"]] == ["B only"]
    pack_a = (await _pack(client, a["employee"]["id"])).json()
    assert [f["value"] for f in pack_a["facts"]] == ["A only"]
    assert (await _pack(client, str(uuid.uuid4()))).status_code == 404
    assert (await _pack(client, "not-a-uuid")).status_code == 422


async def test_lookup_function_is_narrow(
    client: httpx.AsyncClient, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    t = await _tenant(client, "Sunrise Clinic")
    async with app_engine.connect() as conn:
        # The app role, with no tenant bound, learns the business id and nothing more ...
        got = await conn.execute(
            text("SELECT internal_employee_business(:i)"), {"i": uuid.UUID(t["employee"]["id"])}
        )
        assert str(got.scalar_one()) == t["business"]["id"]
        assert (await conn.execute(text("SELECT count(*) FROM employee"))).scalar_one() == 0
    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT p.prosecdef, p.proconfig, "
                    "  EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0) "
                    "FROM pg_proc p WHERE p.proname = 'internal_employee_business'"
                )
            )
        ).one()
    assert row[0] is True
    assert row[1] == ["search_path=pg_catalog, public"]
    assert row[2] is False  # not executable by PUBLIC
