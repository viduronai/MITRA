"""Lead intake API (INT-12): secret auth, 202, dedupe, consent records, instant calling (CALL-03),
calling-hours deferral, rate limits and secret rotation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.pii import hash_phone
from tests.helpers import FakeClock
from tests.leads_helpers import (
    LEAD_PHONE,
    FakeDialer,
    configure,
    enable_leads,
    install_fakes,
    ready_tenant,
    send_lead,
    tenant,
)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> Any:
    configure()
    return install_fakes(monkeypatch)


@pytest.fixture
def dialer(fakes: Any) -> FakeDialer:
    return fakes[0]  # type: ignore[no-any-return]


LEAD = {"name": "Ravi", "phone": "98123 45678", "city": "Kondapur", "budget": "80L"}


async def test_setup_shows_secret_once(
    clock: FakeClock, client: httpx.AsyncClient, fakes: Any
) -> None:
    t = await tenant(client)
    resp = await client.get("/v1/leads/setup", headers=t["headers"])
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert {s["kind"] for s in resp.json()["sources"]} >= {"meta", "indiamart", "api"}

    setup = await enable_leads(client, t)
    assert setup["secret"].startswith("mli_")
    assert setup["urls"]["generic"].endswith(f"/lead-intake/{setup['slug']}")
    again = (await client.post("/v1/leads/setup", headers=t["headers"])).json()
    assert again["secret"] is None
    assert again["slug"] == setup["slug"]
    assert (await client.get("/v1/leads/setup", headers=t["headers"])).json()["secret"] is None


async def test_lead_is_accepted_and_called_within_a_minute(
    client: httpx.AsyncClient, dialer: FakeDialer, clock: FakeClock, admin_engine: AsyncEngine
) -> None:
    t = await ready_tenant(client)
    resp = await send_lead(client, t, LEAD)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["duplicate"] is False
    assert datetime.fromisoformat(body["call_at"]) == clock.now

    [call] = dialer.calls
    assert call["phone"] == LEAD_PHONE
    assert str(call["employee_id"]) == t["employee"]["id"]
    assert call["variables"] == {
        "lead_source": "api",
        "lead_name": "Ravi",
        "city": "Kondapur",
        "budget": "80L",
    }
    assert call["dedupe_key"] == f"lead:{body['lead_id']}"

    async with admin_engine.connect() as conn:
        lead = (
            await conn.execute(text("SELECT * FROM lead WHERE id = :id"), {"id": body["lead_id"]})
        ).one()
        consent = (
            await conn.execute(
                text("SELECT * FROM consent_record WHERE id = :id"), {"id": lead.consent_record_id}
            )
        ).one()
        raw = await conn.execute(
            text("SELECT count(*) FROM lead WHERE fields::text LIKE '%98123%'")
        )
    assert lead.phone_hash == hash_phone(LEAD_PHONE)
    assert lead.phone_last4 == "5678"
    assert lead.source == "api"
    assert (consent.scope, consent.source) == ("service", "lead_form")
    assert consent.phone_hash == hash_phone(LEAD_PHONE)
    assert "api" in consent.note
    assert raw.scalar_one() == 0  # the number is never stored in the clear

    listed = (await client.get("/v1/leads", headers=t["headers"])).json()["items"]
    assert listed[0]["name"] == "Ravi"
    assert listed[0]["status"] == "queued"


async def test_wrong_secret_and_unknown_slug_look_the_same(
    clock: FakeClock, client: httpx.AsyncClient, fakes: Any
) -> None:
    t = await ready_tenant(client)
    wrong = await send_lead(client, t, LEAD, secret="mli_wrong")
    missing = await client.post(
        "/lead-intake/nope-123456", json=LEAD, headers={"X-Mitra-Secret": t["secret"]}
    )
    no_header = await client.post(f"/lead-intake/{t['slug']}", json=LEAD)
    for resp in (wrong, missing, no_header):
        assert resp.status_code == 401
        assert resp.json()["error"]["message"] == "Unknown intake URL or wrong secret"


async def test_invalid_payloads(clock: FakeClock, client: httpx.AsyncClient, fakes: Any) -> None:
    t = await ready_tenant(client)
    bad_phone = await send_lead(client, t, {"name": "X", "phone": "12345"})
    assert bad_phone.status_code == 422
    assert bad_phone.json()["error"]["code"] == "invalid_lead"
    not_object = await client.post(
        f"/lead-intake/{t['slug']}", content=b"[1,2]", headers={"X-Mitra-Secret": t["secret"]}
    )
    assert not_object.status_code == 422
    huge = await client.post(
        f"/lead-intake/{t['slug']}",
        content=b"{" + b" " * 70_000 + b"}",
        headers={"X-Mitra-Secret": t["secret"]},
    )
    assert huge.status_code == 413


async def test_same_phone_within_window_is_a_duplicate(
    client: httpx.AsyncClient, dialer: FakeDialer, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    first = (await send_lead(client, t, LEAD)).json()
    clock.advance(120)
    second = await send_lead(client, t, LEAD | {"phone": "+91-98123-45678"})
    assert second.status_code == 202
    assert second.json()["duplicate"] is True
    assert second.json()["status"] == "duplicate"
    assert len(dialer.calls) == 1
    leads = (await client.get("/v1/leads", headers=t["headers"])).json()["items"]
    assert leads[0]["duplicate_of"] == first["lead_id"]

    clock.advance(11 * 60)  # past the 10-minute window: a new enquiry, a new call
    third = (await send_lead(client, t, LEAD)).json()
    assert third["duplicate"] is False
    assert len(dialer.calls) == 2

    # Owners can change the window.
    resp = await client.patch("/v1/leads/setup", json={"dedupe_minutes": 0}, headers=t["headers"])
    assert resp.json()["dedupe_minutes"] == 0
    assert (await send_lead(client, t, LEAD)).json()["duplicate"] is False


async def test_same_external_id_is_accepted_once(
    client: httpx.AsyncClient, dialer: FakeDialer, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    first = (await send_lead(client, t, LEAD | {"external_id": "row-7"})).json()
    clock.advance(3600)
    again = (await send_lead(client, t, LEAD | {"external_id": "row-7"})).json()
    assert again == first | {"duplicate": True}
    assert len(dialer.calls) == 1


async def test_consent_refused_means_no_call_and_no_consent_record(
    clock: FakeClock, client: httpx.AsyncClient, dialer: FakeDialer, admin_engine: AsyncEngine
) -> None:
    t = await ready_tenant(client)
    body = (await send_lead(client, t, LEAD | {"consent": False})).json()
    assert body["status"] == "no_consent"
    assert dialer.calls == []
    async with admin_engine.connect() as conn:
        count = await conn.execute(
            text("SELECT count(*) FROM consent_record WHERE phone_hash = :h"),
            {"h": hash_phone(LEAD_PHONE)},
        )
    assert count.scalar_one() == 0


async def test_out_of_hours_lead_is_scheduled_for_next_window(
    client: httpx.AsyncClient, dialer: FakeDialer, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    clock.now = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)  # 22:30 IST
    body = (await send_lead(client, t, LEAD)).json()
    assert body["status"] == "scheduled"
    next_morning = datetime(2026, 10, 19, 3, 30, tzinfo=UTC)  # 09:00 IST
    assert datetime.fromisoformat(body["call_at"]) == next_morning
    assert dialer.calls[0]["not_before"] == next_morning
    lead = (await client.get("/v1/leads", headers=t["headers"])).json()["items"][0]
    assert lead["reason_text"] == ["outside allowed calling hours"]


async def test_no_number_blocks_and_explains(
    clock: FakeClock, client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    t = await tenant(client)
    await enable_leads(client, t)
    body = (await send_lead(client, t, LEAD)).json()
    assert body["status"] == "blocked"
    assert dialer.calls == []
    lead = (await client.get("/v1/leads", headers=t["headers"])).json()["items"][0]
    assert lead["reasons"] == ["no_caller_id"]
    assert lead["reason_text"] == ["no verified number for this kind of call"]


async def test_opted_out_lead_is_blocked(
    clock: FakeClock, client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    t = await ready_tenant(client)
    resp = await client.post(
        "/internal/v1/telephony/opt-outs",
        json={"business_id": t["business"]["id"], "contact_phone": LEAD_PHONE, "source": "owner"},
        headers={"Authorization": "Bearer test-service-token-0123456789abcdef"},
    )
    assert resp.status_code == 201, resp.text
    body = (await send_lead(client, t, LEAD)).json()
    assert body["status"] == "blocked"
    assert dialer.calls == []


async def test_source_routine_delay_employee_and_switches(
    client: httpx.AsyncClient, fakes: Any, clock: FakeClock
) -> None:
    dialer, heads_up, _ = fakes
    t = await ready_tenant(client)
    other = await client.post(
        "/v1/employees",
        json={"name": "Ravi", "role_template": "receptionist", "languages": ["te"]},
        headers=t["headers"],
    )
    patch = {"call_delay_seconds": 300, "employee_id": other.json()["id"], "heads_up": True}
    resp = await client.patch("/v1/leads/sources/zapier", json=patch, headers=t["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["connected"] is True

    body = (await send_lead(client, t, LEAD | {"source": "zapier"})).json()
    assert datetime.fromisoformat(body["call_at"]) == clock.now + timedelta(minutes=5)
    assert str(dialer.calls[0]["employee_id"]) == other.json()["id"]
    assert heads_up.sent[0]["phone_e164"] == LEAD_PHONE

    await client.patch("/v1/leads/sources/zapier", json={"auto_call": False}, headers=t["headers"])
    clock.advance(3600)
    assert (await send_lead(client, t, LEAD | {"source": "zapier"})).json()[
        "status"
    ] == "not_called"

    await client.patch("/v1/leads/sources/zapier", json={"enabled": False}, headers=t["headers"])
    off = await send_lead(client, t, LEAD | {"source": "zapier"})
    assert off.status_code == 409
    assert off.json()["error"]["code"] == "source_disabled"

    sources = (await client.get("/v1/leads/setup", headers=t["headers"])).json()["sources"]
    zapier = next(s for s in sources if s["kind"] == "zapier")
    assert zapier["lead_count"] == 2
    assert zapier["last_lead_at"] is not None


async def test_dialer_refusal_marks_failed(
    clock: FakeClock, client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    t = await ready_tenant(client)
    dialer.fail = True
    body = (await send_lead(client, t, LEAD)).json()
    assert body["status"] == "failed"


async def test_rate_limit_per_business(
    clock: FakeClock, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(lead_intake_max_per_minute=2)
    install_fakes(monkeypatch)
    t = await ready_tenant(client)
    for i in range(2):
        assert (await send_lead(client, t, LEAD | {"phone": f"98123000{i}0"})).status_code == 202
    limited = await send_lead(client, t, LEAD | {"phone": "9812300099"})
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


async def test_rotated_secret_has_grace_then_expires(
    clock: FakeClock, client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine
) -> None:
    t = await ready_tenant(client)
    old = t["secret"]
    rotated = (await client.post("/v1/leads/setup/rotate-secret", headers=t["headers"])).json()
    assert rotated["secret"] != old
    assert rotated["previous_valid_until"] is not None
    assert (await send_lead(client, t, LEAD, secret=old)).status_code == 202
    assert (await send_lead(client, t, LEAD, secret=rotated["secret"])).status_code == 202
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE lead_intake SET previous_valid_until = now() - interval '1 minute'")
        )
    assert (await send_lead(client, t, LEAD, secret=old)).status_code == 401


async def test_staff_cannot_manage_but_can_see_leads(
    clock: FakeClock, client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine
) -> None:
    from mitra_core.models.enums import MemberRole
    from tests.helpers import add_member

    t = await ready_tenant(client)
    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    headers = staff.headers(t["business"]["id"])
    assert (await client.post("/v1/leads/setup/rotate-secret", headers=headers)).status_code == 403
    assert (await client.get("/v1/leads", headers=headers)).status_code == 200


async def test_send_test_lead_uses_owner_phone(
    clock: FakeClock, client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    t = await ready_tenant(client)
    for kind in ("meta", "indiamart", "google_ads", "justdial", "website_form"):
        resp = await client.post(f"/v1/leads/sources/{kind}/test", headers=t["headers"])
        assert resp.status_code == 200, resp.text
        assert resp.json()["lead"]["source"] == kind
        assert resp.json()["lead"]["fields"]["is_test"] == "true"
    assert dialer.calls[0]["phone"] == t["owner"].phone
    # The same phone within 10 minutes: only the first test actually calls.
    assert len(dialer.calls) == 1


async def test_real_dialer_queue_gets_the_job(
    clock: FakeClock, client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine
) -> None:
    from mitra_core.leads.calling import get_lead_dialer
    from mitra_core.main import app

    del app.dependency_overrides[get_lead_dialer]  # the shared dialer queue, for real
    t = await ready_tenant(client)
    body = (await send_lead(client, t, LEAD)).json()
    assert body["status"] == "queued"
    async with admin_engine.connect() as conn:
        job = (
            await conn.execute(
                text("SELECT * FROM outbound_job WHERE dedupe_key = :k"),
                {"k": f"lead:{body['lead_id']}"},
            )
        ).one()
    assert job.source == "lead"
    assert job.purpose == "service"
    assert job.phone_hash == hash_phone(LEAD_PHONE)
    assert job.variables["lead_name"] == "Ravi"


async def test_real_whatsapp_heads_up_is_sent(
    clock: FakeClock, client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine
) -> None:
    from mitra_core.leads.calling import get_heads_up
    from mitra_core.main import app

    del app.dependency_overrides[get_heads_up]  # the manager's WhatsApp sender (simulator)
    t = await ready_tenant(client)
    await client.patch("/v1/leads/sources/api", json={"heads_up": True}, headers=t["headers"])
    assert (await send_lead(client, t, LEAD)).json()["status"] == "queued"
    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT * FROM wa_message WHERE template = 'call_heads_up'"))
        ).one()
    assert row.phone_hash == hash_phone(LEAD_PHONE)
    assert row.params["business"] == "Sunrise Homes"


async def test_new_lead_fires_owner_routine(
    client: httpx.AsyncClient, clock: FakeClock, fakes: Any, admin_engine: AsyncEngine
) -> None:
    t = await ready_tenant(client)
    spec = {
        "trigger": {"type": "event", "event": "lead.created"},
        "action": {"verb": "whatsapp", "employee_id": t["employee"]["id"], "goal": "confirm"},
    }
    resp = await client.post(
        "/v1/routines",
        json={"name": "Welcome", "spec": spec, "enabled": True},
        headers=t["headers"],
    )
    assert resp.status_code == 201, resp.text
    await send_lead(client, t, LEAD)
    await send_lead(client, t, LEAD | {"phone": "9811100000", "consent": False})
    async with admin_engine.connect() as conn:
        runs = await conn.execute(
            text("SELECT count(*) FROM routine_run WHERE routine_id = :r"), {"r": resp.json()["id"]}
        )
    assert runs.scalar_one() == 1  # the no-consent lead fires nothing
