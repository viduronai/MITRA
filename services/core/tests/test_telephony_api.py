"""Telephony API: Go-live / Connect numbers, inbound resolution, compliance.check, attempts,
number health, and tenant isolation (API + Postgres RLS)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import Settings, get_settings
from mitra_core.main import app
from mitra_core.models.enums import MemberRole
from mitra_core.telephony.dnd import MockDndProvider, get_dnd_provider
from tests.helpers import FakeClock, add_member, bearer, create_business, create_employee, new_actor

TOKEN = "test-service-token-0123456789abcdef"
SVC = bearer(TOKEN)
CUSTOMER = "+919812345678"
TABLES = (
    "phone_number",
    "consent_record",
    "opt_out",
    "outbound_attempt",
    "compliance_decision",
    "dnd_cache",
)


def _configure(**overrides: Any) -> Settings:
    settings = Settings(**({"service_token": SecretStr(TOKEN)} | overrides))
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


async def _tenant(client: httpx.AsyncClient, name: str = "Sunrise Clinic") -> dict[str, Any]:
    owner = new_actor()
    business = await create_business(client, owner, name=name)
    employee = await create_employee(client, owner, business["id"])
    return {
        "owner": owner,
        "headers": owner.headers(business["id"]),
        "business": business,
        "employee": employee,
    }


async def _request(client: httpx.AsyncClient, t: dict[str, Any], **body: Any) -> dict[str, Any]:
    resp = await client.post(
        "/v1/phone-numbers/requests", json={"city": "Hyderabad"} | body, headers=t["headers"]
    )
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def _approve(
    client: httpx.AsyncClient, t: dict[str, Any], number_id: str, e164: str, **extra: Any
) -> httpx.Response:
    return await client.patch(
        f"/internal/v1/telephony/numbers/{number_id}",
        json={"business_id": t["business"]["id"], "e164": e164, "kyc_status": "approved"} | extra,
        headers=SVC,
    )


async def _live_number(
    client: httpx.AsyncClient, t: dict[str, Any], e164: str = "+914041234567"
) -> dict[str, Any]:
    number = await _request(client, t, employee_id=t["employee"]["id"])
    resp = await _approve(client, t, number["id"], e164, carrier_sid="EXO123")
    assert resp.status_code == 200, resp.text
    return number


async def _check(client: httpx.AsyncClient, t: dict[str, Any], **body: Any) -> dict[str, Any]:
    payload = {"business_id": t["business"]["id"], "contact_phone": CUSTOMER, "purpose": "service"}
    resp = await client.post(
        "/internal/v1/telephony/compliance/check", json=payload | body, headers=SVC
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def _consent(client: httpx.AsyncClient, t: dict[str, Any], scope: str = "service") -> None:
    resp = await client.post(
        "/internal/v1/telephony/consents",
        json={
            "business_id": t["business"]["id"],
            "contact_phone": CUSTOMER,
            "scope": scope,
            "source": "lead_form",
        },
        headers=SVC,
    )
    assert resp.status_code == 201, resp.text


async def _attempt(
    client: httpx.AsyncClient, t: dict[str, Any], number_id: str | None, **body: Any
) -> httpx.Response:
    payload = {
        "business_id": t["business"]["id"],
        "contact_phone": CUSTOMER,
        "purpose": "service",
        "phone_number_id": number_id,
    }
    return await client.post("/internal/v1/telephony/attempts", json=payload | body, headers=SVC)


# ---- Go live / Connect ---


async def test_new_local_number_flow(client: httpx.AsyncClient, clock: FakeClock) -> None:
    _configure()
    t = await _tenant(client)
    listed = (await client.get("/v1/phone-numbers", headers=t["headers"])).json()
    assert listed == {
        "items": [],
        "carrier": "sim",
        "simulated": True,
        "business_name": "Sunrise Clinic",
    }

    number = await _request(client, t, label="Main branch")
    assert number["kyc_status"] == "pending_kyc"
    assert number["carrier"] == "sim"
    assert number["e164"] is None
    assert number["display_name"] == "Sunrise Clinic"
    assert number["health"] == "healthy"
    url = f"/v1/phone-numbers/{number['id']}"

    # Not live yet: no forwarding codes, no forwarding test.
    assert (await client.get(f"{url}/forwarding", headers=t["headers"])).status_code == 409

    kyc = {"document_type": "gst", "file_name": "gst-certificate.pdf"}
    resp = await client.post(f"{url}/kyc", json=kyc, headers=t["headers"])
    assert resp.status_code == 200, resp.text
    # The simulator approves straight away with a made-up Hyderabad number.
    assert resp.json()["kyc_status"] == "approved"
    assert resp.json()["e164"].startswith("+9140")
    employees = (await client.get("/v1/employees", headers=t["headers"])).json()
    items = employees["items"] if isinstance(employees, dict) else employees
    assert all(e["status"] == "working" for e in items)  # live number: training is over
    assert (await client.post(f"{url}/kyc", json=kyc, headers=t["headers"])).status_code == 409

    resp = await client.post(f"{url}/caller-name", headers=t["headers"])
    assert resp.json()["truecaller_status"] == "pending"
    assert resp.json()["cnap_status"] == "pending"

    # Carrier approves KYC (ops / webhook through the internal API).
    assert (await _approve(client, t, number["id"], "+914041234567")).status_code == 200
    codes = (await client.get(f"{url}/forwarding", headers=t["headers"])).json()
    assert codes["target"] == "04041234567"
    assert codes["operators"][0]["busy"] == "*405*04041234567"

    resp = await client.post(f"{url}/forwarding-test", headers=t["headers"])
    assert resp.json()["status"] == "passed"
    assert resp.json()["simulated"] is True

    listed = (await client.get("/v1/phone-numbers", headers=t["headers"])).json()["items"]
    assert listed[0]["display"] == "040 4123 4567"
    assert listed[0]["kyc_status"] == "approved"
    assert listed[0]["forwarding_tested_at"] is not None


async def test_renaming_a_verified_number_needs_reverification(
    client: httpx.AsyncClient,
) -> None:
    _configure()
    t = await _tenant(client)
    number = await _live_number(client, t)
    await _approve(
        client,
        t,
        number["id"],
        "+914041234567",
        truecaller_status="verified",
        cnap_status="verified",
    )
    resp = await client.patch(
        f"/v1/phone-numbers/{number['id']}",
        json={"display_name": "Sunrise Clinic Kukatpally"},
        headers=t["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["truecaller_status"] == "pending"
    assert resp.json()["cnap_status"] == "pending"


async def test_staff_cannot_request_numbers(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    _configure()
    t = await _tenant(client)
    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    resp = await client.post(
        "/v1/phone-numbers/requests",
        json={"city": "Hyderabad"},
        headers=staff.headers(t["business"]["id"]),
    )
    assert resp.status_code == 403
    # ...but can see the card.
    resp = await client.get("/v1/phone-numbers", headers=staff.headers(t["business"]["id"]))
    assert resp.status_code == 200


async def test_number_cannot_be_registered_twice(client: httpx.AsyncClient) -> None:
    _configure()
    a, b = await _tenant(client, "A"), await _tenant(client, "B")
    await _live_number(client, a)
    other = await _request(client, b)
    resp = await _approve(client, b, other["id"], "+914041234567")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "number_taken"


# ---- inbound routing ---


async def test_resolve_dialled_number_to_business_and_employee(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    _configure()
    t = await _tenant(client)
    number = await _live_number(client, t)
    resp = await client.get(
        "/internal/v1/telephony/resolve",
        params={"to": "+914041234567", "from": CUSTOMER},
        headers=SVC,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["business_id"] == t["business"]["id"]
    assert body["employee_id"] == t["employee"]["id"]
    assert body["phone_number_id"] == number["id"]
    assert body["business_name"] == "Sunrise Clinic"
    assert body["caller_known"] is False

    # The inbound call is a relationship: a callback from the same number is now allowed.
    result = await _check(client, t, purpose="callback", called_number_id=number["id"])
    assert result["decision"] == "allow"
    assert result["caller_id"]["e164"] == "+914041234567"


async def test_resolve_unknown_or_pending_number_is_404(client: httpx.AsyncClient) -> None:
    _configure()
    t = await _tenant(client)
    await _request(client, t)  # pending KYC: not routable
    for to in ("+914041234567", "+914000000000"):
        resp = await client.get("/internal/v1/telephony/resolve", params={"to": to}, headers=SVC)
        assert resp.status_code == 404


async def test_resolve_requires_service_token(client: httpx.AsyncClient) -> None:
    _configure()
    t = await _tenant(client)
    resp = await client.get(
        "/internal/v1/telephony/resolve", params={"to": "+914041234567"}, headers=t["headers"]
    )
    assert resp.status_code == 401


# ---- compliance.check ---


async def test_compliance_check_end_to_end(client: httpx.AsyncClient, clock: FakeClock) -> None:
    _configure()
    t = await _tenant(client)
    number = await _live_number(client, t)

    blocked = await _check(client, t)
    assert blocked["decision"] == "block"
    assert [r["code"] for r in blocked["reasons"]] == ["no_consent"]

    await _consent(client, t)
    allowed = await _check(client, t)
    assert allowed["allowed"] is True
    assert allowed["caller_id"] == {
        "phone_number_id": number["id"],
        "e164": "+914041234567",
        "type": "local",
    }

    for _ in range(3):
        assert (await _attempt(client, t, number["id"], outcome="no_answer")).status_code == 201
    capped = await _check(client, t)
    assert capped["decision"] == "defer"
    assert [r["code"] for r in capped["reasons"]] == ["daily_cap"]
    assert capped["defer_until"] is not None

    resp = await client.post(
        "/internal/v1/telephony/opt-outs",
        json={"business_id": t["business"]["id"], "contact_phone": CUSTOMER},
        headers=SVC,
    )
    assert resp.status_code == 201
    again = await client.post(
        "/internal/v1/telephony/opt-outs",
        json={"business_id": t["business"]["id"], "contact_phone": CUSTOMER},
        headers=SVC,
    )
    assert again.json()["id"] == resp.json()["id"]  # idempotent
    opted = await _check(client, t)
    assert [r["code"] for r in opted["reasons"]] == ["opted_out"]

    summary = (await client.get("/v1/compliance/summary", headers=t["headers"])).json()
    assert summary["allowed"] == 1
    assert summary["counts"] == {"no_consent": 1, "daily_cap": 1, "opted_out": 1}
    assert "1 person skipped: asked not to be called" in summary["lines"]


async def test_paused_wallet_blocks_outbound(client: httpx.AsyncClient, clock: FakeClock) -> None:
    _configure()
    t = await _tenant(client)
    await _live_number(client, t)
    await _consent(client, t)
    assert (await _check(client, t))["allowed"] is True

    resp = await client.patch(
        "/v1/billing/settings", json={"monthly_cap_paise": 0}, headers=t["headers"]
    )
    assert resp.status_code == 200, resp.text
    capped = await _check(client, t)
    assert capped["decision"] == "block"
    assert [r["code"] for r in capped["reasons"]] == ["wallet_spend_cap"]


async def test_outside_hours_defers_to_ist_morning(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    _configure()
    t = await _tenant(client)
    await _live_number(client, t)
    await _consent(client, t)
    clock.advance(12 * 3600)  # 21:00 UTC = 02:30 IST
    result = await _check(client, t)
    assert result["decision"] == "defer"
    assert result["defer_until"].startswith("2026-10-19T03:30:00")  # 09:00 IST


async def test_promotional_dnd_scrub_is_cached(client: httpx.AsyncClient, clock: FakeClock) -> None:
    _configure(promotional_calling_enabled=True)
    dnd = MockDndProvider(frozenset({CUSTOMER}))
    app.dependency_overrides[get_dnd_provider] = lambda: dnd
    t = await _tenant(client)
    promo = await _request(client, t, type="local")
    await _approve(client, t, promo["id"], "+914041234567")
    await _consent(client, t, scope="promotional")

    first = await _check(client, t, purpose="promotional")
    assert first["decision"] == "block"
    assert {r["code"] for r in first["reasons"]} == {"dnd_registered", "no_caller_id"}
    await _check(client, t, purpose="promotional")
    assert dnd.lookups == 1  # second check served from dnd_cache

    clock.advance(25 * 3600)  # cache older than 24 h: looked up again
    await _check(client, t, purpose="promotional")
    assert dnd.lookups == 2


async def test_promotional_blocked_by_default(client: httpx.AsyncClient) -> None:
    _configure()
    t = await _tenant(client)
    await _live_number(client, t)
    await _consent(client, t, scope="promotional")
    result = await _check(client, t, purpose="promotional")
    assert "promotional_disabled" in [r["code"] for r in result["reasons"]]


# ---- attempts + number health ---


async def test_health_job_pauses_a_failing_number_and_owner_can_resume(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    _configure()
    t = await _tenant(client)
    number = await _live_number(client, t)
    await _consent(client, t)
    start = clock()
    for i in range(30):
        outcome = "answered" if i < 3 else "no_answer"
        at = (start - timedelta(days=3, minutes=i)).isoformat()
        resp = await _attempt(
            client,
            t,
            number["id"],
            outcome=outcome,
            attempted_at=at,
            contact_phone=f"+9198000000{i:02d}",  # different people: no frequency cap
        )
        assert resp.status_code == 201

    run = (await client.post("/internal/v1/telephony/health/run", headers=SVC)).json()
    assert run["checked"] == 1
    assert run["changes"] == [
        {
            "phone_number_id": number["id"],
            "business_id": t["business"]["id"],
            "previous": "healthy",
            "health": "paused",
            "answer_rate_7d": pytest.approx(0.1),
        }
    ]
    card = (await client.get("/v1/phone-numbers", headers=t["headers"])).json()["items"][0]
    assert card["health"] == "paused"
    assert card["outbound_enabled"] is False
    assert card["remediation"]
    assert [r["code"] for r in (await _check(client, t))["reasons"]] == ["number_paused"]

    resp = await client.post(f"/v1/phone-numbers/{number['id']}/resume", headers=t["headers"])
    assert resp.json()["health"] == "watch"
    assert resp.json()["outbound_enabled"] is True
    # The old failures are before the resume: the next run does not pause it again.
    run = (await client.post("/internal/v1/telephony/health/run", headers=SVC)).json()
    assert run["changes"][0]["health"] == "healthy"
    assert (await _check(client, t))["allowed"] is True


async def test_spam_label_pauses_and_blocks_resume(client: httpx.AsyncClient) -> None:
    _configure()
    t = await _tenant(client)
    number = await _live_number(client, t)
    await _approve(client, t, number["id"], "+914041234567", spam_flag=True)
    await client.post("/internal/v1/telephony/health/run", headers=SVC)
    resp = await client.post(f"/v1/phone-numbers/{number['id']}/resume", headers=t["headers"])
    assert resp.status_code == 409


async def test_attempt_outcome_update(client: httpx.AsyncClient) -> None:
    _configure()
    t = await _tenant(client)
    number = await _live_number(client, t)
    attempt = (await _attempt(client, t, number["id"])).json()
    assert attempt["outcome"] is None
    resp = await client.patch(
        f"/internal/v1/telephony/attempts/{attempt['id']}",
        json={"business_id": t["business"]["id"], "outcome": "answered"},
        headers=SVC,
    )
    assert resp.json()["outcome"] == "answered"


# ---- tenant isolation ---


async def test_api_cannot_cross_tenants(client: httpx.AsyncClient) -> None:
    _configure()
    a, b = await _tenant(client, "A"), await _tenant(client, "B")
    number = await _live_number(client, a)
    hb = b["headers"]
    assert (await client.get("/v1/phone-numbers", headers=hb)).json()["items"] == []
    url = f"/v1/phone-numbers/{number['id']}"
    assert (await client.get(f"{url}/forwarding", headers=hb)).status_code == 404
    assert (await client.patch(url, json={"label": "x"}, headers=hb)).status_code == 404
    assert (await client.post(f"{url}/forwarding-test", headers=hb)).status_code == 404
    # B cannot route A's number to its own employee either.
    resp = await client.patch(url, json={"employee_id": b["employee"]["id"]}, headers=a["headers"])
    assert resp.status_code == 404

    # Internal API: A's number under B's business id is invisible.
    resp = await client.patch(
        f"/internal/v1/telephony/numbers/{number['id']}",
        json={"business_id": b["business"]["id"], "spam_flag": True},
        headers=SVC,
    )
    assert resp.status_code == 404
    assert (await _attempt(client, b, number["id"])).status_code == 404
    # B's compliance check never picks A's number as caller ID.
    await _consent(client, b)
    assert [r["code"] for r in (await _check(client, b))["reasons"]] == ["no_caller_id"]


async def test_app_role_rls_on_telephony_tables(
    client: httpx.AsyncClient, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    _configure()
    a, b = await _tenant(client, "A"), await _tenant(client, "B")
    await _live_number(client, a)
    await _consent(client, a)
    await _check(client, a)
    async with admin_engine.connect() as conn:
        for table in ("phone_number", "consent_record", "compliance_decision"):
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count >= 1, table

    async with app_engine.begin() as conn:
        for table in TABLES:
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, f"{table} visible without a tenant"
        await conn.execute(
            text("SELECT set_config('app.business_id', :b, true)"), {"b": b["business"]["id"]}
        )
        for table in TABLES:
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, f"{table} leaks across tenants"
        # The definer lookup exposes only the owning business id, for live numbers only.
        found = (
            await conn.execute(text("SELECT internal_number_business('+914041234567')"))
        ).scalar_one()
        assert str(found) == a["business"]["id"]
        # Writing a row for another tenant is refused by the policy's WITH CHECK.
        with pytest.raises(Exception, match="row-level security"):
            await conn.execute(
                text(
                    "INSERT INTO opt_out (business_id, phone_hash, source) "
                    "VALUES (:a, 'x', 'owner')"
                ),
                {"a": uuid.UUID(a["business"]["id"])},
            )
