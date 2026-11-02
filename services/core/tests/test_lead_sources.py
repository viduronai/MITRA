"""Source adapters over HTTP: website form, Google Ads, IndiaMART (push + pull), JustDial, Meta
Lead Ads webhook; plus tenant isolation of lead tables (API + Postgres RLS)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.api.v1.leads import indiamart_provider
from mitra_core.leads.providers import SimIndiaMart
from mitra_core.main import app
from tests.helpers import FakeClock
from tests.leads_helpers import (
    META_SECRET,
    META_VERIFY,
    SVC,
    FakeDialer,
    configure,
    install_fakes,
    ready_tenant,
    send_lead,
)


@pytest.fixture
def dialer(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> FakeDialer:
    configure()
    return install_fakes(monkeypatch)[0]


FORM = {"name": "Lakshmi", "phone": "9123456789", "consent": "on", "website": ""}


async def _enable(client: httpx.AsyncClient, t: dict[str, Any], kind: str, **body: Any) -> None:
    resp = await client.patch(
        f"/v1/leads/sources/{kind}", json={"enabled": True} | body, headers=t["headers"]
    )
    assert resp.status_code == 200, resp.text


async def test_website_form_needs_switch_consent_and_is_cors_readable(
    client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    t = await ready_tenant(client)
    url = f"/lead-intake/{t['slug']}/form"
    off = await client.post(url, data=FORM)
    assert off.status_code == 404
    assert off.headers["access-control-allow-origin"] == "*"

    await _enable(client, t, "website_form")
    no_consent = await client.post(url, data=FORM | {"consent": ""})
    assert no_consent.status_code == 422
    assert no_consent.json()["error"]["code"] == "consent_required"

    ok = await client.post(url, data=FORM)
    assert ok.status_code == 202, ok.text
    assert ok.json() == {"status": "received"}
    assert ok.headers["access-control-allow-origin"] == "*"
    assert dialer.calls[0]["phone"] == "+919123456789"
    lead = (await client.get("/v1/leads", headers=t["headers"])).json()["items"][0]
    assert lead["source"] == "website_form"

    bot = await client.post(url, data=FORM | {"website": "http://spam"})
    assert bot.status_code == 202
    assert len(dialer.calls) == 1  # honeypot: silently dropped

    preflight = await client.options(url)
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-methods"] == "POST, OPTIONS"


async def test_website_form_is_rate_limited_per_ip(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(lead_form_max_per_ip_hour=2)
    install_fakes(monkeypatch)
    t = await ready_tenant(client)
    await _enable(client, t, "website_form")
    url = f"/lead-intake/{t['slug']}/form"
    for phone in ("9123456780", "9123456781"):
        assert (await client.post(url, data=FORM | {"phone": phone})).status_code == 202
    limited = await client.post(url, data=FORM | {"phone": "9123456782"})
    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == "*"


async def test_google_ads_uses_google_key(client: httpx.AsyncClient, dialer: FakeDialer) -> None:
    t = await ready_tenant(client)
    body = {
        "lead_id": "G-1",
        "campaign_id": 55,
        "user_column_data": [
            {"column_id": "FULL_NAME", "string_value": "Arjun"},
            {"column_id": "PHONE_NUMBER", "string_value": "+919876500001"},
        ],
    }
    url = f"/lead-intake/{t['slug']}/google-ads"
    assert (await client.post(url, json=body | {"google_key": "nope"})).status_code == 401
    resp = await client.post(url, json=body | {"google_key": t["secret"]})
    assert resp.status_code == 202, resp.text
    lead = (await client.get("/v1/leads?source=google_ads", headers=t["headers"])).json()["items"]
    assert lead[0]["source_detail"] == "Google Ads campaign 55"


async def test_indiamart_push_with_key_in_query(
    client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    t = await ready_tenant(client)
    body = {
        "CODE": 200,
        "RESPONSE": {
            "UNIQUE_QUERY_ID": "Q1",
            "SENDER_NAME": "Suresh",
            "SENDER_MOBILE": "+91-9988776655",
        },
    }
    url = f"/lead-intake/{t['slug']}/indiamart"
    resp = await client.post(url, params={"key": t["secret"]}, json=body)
    assert resp.status_code == 202, resp.text
    again = await client.post(url, params={"key": t["secret"]}, json=body)
    assert again.json()["duplicate"] is True  # IndiaMART retries are absorbed


async def test_justdial_get_push(client: httpx.AsyncClient, dialer: FakeDialer) -> None:
    t = await ready_tenant(client)
    params = {"key": t["secret"], "leadid": "JD9", "name": "Mohan", "mobile": "9988776600"}
    resp = await client.get(f"/lead-intake/{t['slug']}/justdial", params=params)
    assert resp.status_code == 202, resp.text
    assert dialer.calls[0]["variables"]["lead_name"] == "Mohan"


async def test_indiamart_pull_simulator(
    client: httpx.AsyncClient, dialer: FakeDialer, clock: FakeClock
) -> None:
    app.dependency_overrides[indiamart_provider] = lambda: SimIndiaMart()
    t = await ready_tenant(client)
    no_key = (await client.post("/v1/leads/sources/indiamart/pull", headers=t["headers"])).json()
    assert no_key["error"] == "IndiaMART key is not set"

    await _enable(client, t, "indiamart", credential="sim-crm-key-123456")
    setup = (await client.get("/v1/leads/setup", headers=t["headers"])).json()
    source = next(s for s in setup["sources"] if s["kind"] == "indiamart")
    assert source["credential_hint"] == "…3456"
    assert source["simulated"] is True
    assert "sim-crm-key-123456" not in json.dumps(setup)

    first = (await client.post("/v1/leads/sources/indiamart/pull", headers=t["headers"])).json()
    assert (first["fetched"], first["created"]) == (1, 1)
    too_soon = (await client.post("/v1/leads/sources/indiamart/pull", headers=t["headers"])).json()
    assert too_soon["error"] == "Fetched recently, try again soon"

    clock.advance(600)
    job = await client.post("/internal/v1/leads/pull", headers=SVC)
    assert job.status_code == 200, job.text
    assert job.json() == {"businesses": 1, "processed": 1}


def _meta_body(page: str, leadgen: str) -> bytes:
    payload = {
        "object": "page",
        "entry": [
            {
                "id": page,
                "changes": [
                    {"field": "leadgen", "value": {"leadgen_id": leadgen, "page_id": page}}
                ],
            }
        ],
    }
    return json.dumps(payload).encode()


def _sig(body: bytes, secret: str = META_SECRET) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}", "Content-Type": "application/json"}


async def test_meta_verification_handshake(client: httpx.AsyncClient, dialer: FakeDialer) -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": META_VERIFY,
        "hub.challenge": "1158201444",
    }
    ok = await client.get("/webhooks/meta/leadgen", params=params)
    assert ok.status_code == 200
    assert ok.text == "1158201444"
    bad = await client.get("/webhooks/meta/leadgen", params=params | {"hub.verify_token": "x"})
    assert bad.status_code == 403


async def test_meta_leadgen_webhook(client: httpx.AsyncClient, dialer: FakeDialer) -> None:
    t = await ready_tenant(client)
    await _enable(client, t, "meta", external_id="1029384756")
    body = _meta_body("1029384756", "LG-777")

    unsigned = await client.post("/webhooks/meta/leadgen", content=body)
    assert unsigned.status_code == 401
    forged = await client.post("/webhooks/meta/leadgen", content=body, headers=_sig(body, "x"))
    assert forged.status_code == 401

    resp = await client.post("/webhooks/meta/leadgen", content=body, headers=_sig(body))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"accepted": 1}
    lead = (await client.get("/v1/leads?source=meta", headers=t["headers"])).json()["items"][0]
    assert lead["name"] == "Sim Lead"
    assert lead["source_detail"] == "Simulated Meta campaign"
    assert len(dialer.calls) == 1

    retry = await client.post("/webhooks/meta/leadgen", content=body, headers=_sig(body))
    assert retry.status_code == 200  # Meta retries: same leadgen id, no second call
    assert len(dialer.calls) == 1

    unknown = _meta_body("5550001", "LG-1")
    other = await client.post("/webhooks/meta/leadgen", content=unknown, headers=_sig(unknown))
    assert other.json() == {"accepted": 0}


async def test_meta_page_belongs_to_one_business(
    client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    a = await ready_tenant(client, "A Homes")
    b = await ready_tenant(client, "B Homes")
    await _enable(client, a, "meta", external_id="4242")
    resp = await client.patch(
        "/v1/leads/sources/meta", json={"external_id": "4242"}, headers=b["headers"]
    )
    assert resp.status_code == 409


async def test_leads_are_tenant_isolated(
    client: httpx.AsyncClient, dialer: FakeDialer, app_engine: AsyncEngine
) -> None:
    a = await ready_tenant(client, "A Homes")
    b = await ready_tenant(client, "B Homes")
    await send_lead(client, a, {"phone": "9000000001", "name": "Only A"})
    assert (await client.get("/v1/leads", headers=b["headers"])).json()["items"] == []
    # A's secret does not open B's URL.
    cross = await client.post(
        f"/lead-intake/{b['slug']}",
        json={"phone": "9000000002"},
        headers={"X-Mitra-Secret": a["secret"]},
    )
    assert cross.status_code == 401

    tables = ("lead", "lead_source", "lead_intake", "webhook_endpoint", "webhook_delivery")
    async with app_engine.connect() as conn:
        for table in tables:
            # No tenant bound: RLS hides every row.
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
        await conn.execute(
            text("SELECT set_config('app.business_id', :b, false)"), {"b": b["business"]["id"]}
        )
        assert (await conn.execute(text("SELECT count(*) FROM lead"))).scalar_one() == 0
        with pytest.raises(Exception, match="row-level security"):
            await conn.execute(
                text(
                    "INSERT INTO lead (id, business_id, source, phone_hash, phone_last4, status,"
                    " received_at) VALUES (:id, :a, 'api', 'h', '0000', 'queued', now())"
                ),
                {"id": uuid.uuid4(), "a": a["business"]["id"]},
            )
        await conn.rollback()


async def test_internal_jobs_need_service_token(
    client: httpx.AsyncClient, dialer: FakeDialer
) -> None:
    assert (await client.post("/internal/v1/leads/pull")).status_code == 401
    assert (await client.post("/internal/v1/webhooks/run")).status_code == 401
