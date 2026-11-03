"""The founder's lead consent policy (docs/08 "Lead consent policy"): form checkbox, portal
enquiry consent with 30-day expiry, owner attestation for generic sources, and promotional
contact still blocked."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.pii import hash_phone
from tests.helpers import FakeClock
from tests.leads_helpers import (
    CONSENT_VERSION,
    SVC,
    FakeDialer,
    FakeHeadsUp,
    attest,
    configure,
    install_fakes,
    ready_tenant,
    send_lead,
)

PHONE = "+919811122233"


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> tuple[FakeDialer, FakeHeadsUp]:
    configure()
    dialer, heads_up, _ = install_fakes(monkeypatch)
    return dialer, heads_up


async def _consents(admin_engine: AsyncEngine) -> list[Any]:
    async with admin_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT * FROM consent_record WHERE phone_hash = :h ORDER BY captured_at"),
            {"h": hash_phone(PHONE)},
        )
        return list(rows)


async def _check(
    client: httpx.AsyncClient, t: dict[str, Any], at: datetime, purpose: str = "service"
) -> dict[str, Any]:
    resp = await client.post(
        "/internal/v1/telephony/compliance/check",
        json={
            "business_id": t["business"]["id"],
            "contact_phone": PHONE,
            "purpose": purpose,
            "at": at.isoformat(),
        },
        headers=SVC,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def _codes(result: dict[str, Any]) -> list[str]:
    return [r["code"] for r in result["reasons"]]


# ---- rule 1: forms Mitra controls --------------------------------------------------------------


async def test_website_form_needs_the_checkbox_and_stores_exact_text(
    client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    dialer, _ = fakes
    t = await ready_tenant(client, "Sunrise Homes")
    await client.patch(
        "/v1/leads/sources/website_form", json={"enabled": True}, headers=t["headers"]
    )
    url = f"/lead-intake/{t['slug']}/form"
    form = {"name": "Lakshmi", "phone": PHONE[3:], "consent": "yes", "consent_lang": "te"}

    unticked = await client.post(url, data=form | {"consent": ""})
    no_version = await client.post(url, data=form)  # an old snippet without the policy text
    for resp in (unticked, no_version):
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "consent_required"
    assert dialer.calls == []

    ok = await client.post(url, data=form | {"consent_version": CONSENT_VERSION})
    assert ok.status_code == 202, ok.text
    [consent] = await _consents(admin_engine)
    assert (consent.scope, consent.source) == ("service", "website_form")
    assert consent.text_version == CONSENT_VERSION
    assert consent.consent_text.startswith("నా enquiry గురించి Sunrise Homes నుంచి call")
    assert consent.captured_at == clock.now
    assert consent.expires_at is None
    assert len(dialer.calls) == 1

    setup = (await client.get("/v1/leads/setup", headers=t["headers"])).json()
    assert setup["consent_version"] == CONSENT_VERSION
    assert setup["consent_texts"]["en"] == (
        "I agree to get a call or WhatsApp from Sunrise Homes, possibly from an AI assistant, "
        "about my enquiry."
    )


async def test_google_form_without_the_box_is_stored_not_called(
    client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine
) -> None:
    dialer, heads_up = fakes
    t = await ready_tenant(client)
    await client.patch(
        "/v1/leads/sources/google_forms", json={"heads_up": True}, headers=t["headers"]
    )
    lead = {"Name": "Ravi", "Phone": PHONE, "source": "google_forms"}
    missing = (await send_lead(client, t, lead)).json()
    assert missing["status"] == "no_consent"
    assert dialer.calls == []
    assert heads_up.sent == []
    assert await _consents(admin_engine) == []

    ticked = lead | {"consent": True, "consent_version": CONSENT_VERSION, "external_id": "r2"}
    await client.patch("/v1/leads/setup", json={"dedupe_minutes": 0}, headers=t["headers"])
    assert (await send_lead(client, t, ticked)).json()["status"] == "queued"
    [consent] = await _consents(admin_engine)
    assert consent.source == "google_forms"


# ---- rule 2: third-party lead forms ------------------------------------------------------------


async def test_portal_enquiry_is_service_consent_for_30_days_only(
    client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    body = {"CODE": 200, "RESPONSE": {"UNIQUE_QUERY_ID": "Q9", "SENDER_MOBILE": PHONE}}
    resp = await client.post(
        f"/lead-intake/{t['slug']}/indiamart", params={"key": t["secret"]}, json=body
    )
    assert resp.json()["status"] == "queued"
    [consent] = await _consents(admin_engine)
    assert (consent.scope, consent.source, consent.purpose) == (
        "service",
        "indiamart",
        "enquiry_response",
    )
    assert consent.expires_at == clock.now + timedelta(days=30)

    day_29 = await _check(client, t, clock.now + timedelta(days=29))
    assert "no_consent" not in _codes(day_29)
    assert day_29["decision"] == "allow"
    day_31 = await _check(client, t, clock.now + timedelta(days=31))
    assert day_31["decision"] == "block"
    assert "no_consent" in _codes(day_31)


async def test_portal_expiry_is_configurable(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    configure(lead_portal_consent_days=7)
    install_fakes(monkeypatch)
    t = await ready_tenant(client)
    params = {"key": t["secret"], "leadid": "JD1", "mobile": PHONE[3:]}
    await client.get(f"/lead-intake/{t['slug']}/justdial", params=params)
    assert "no_consent" in _codes(await _check(client, t, clock.now + timedelta(days=8)))


async def test_portal_explicit_refusal_means_no_contact(
    client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine
) -> None:
    dialer, _ = fakes
    t = await ready_tenant(client)
    body = {
        "lead_id": "G7",
        "google_key": t["secret"],
        "user_column_data": [
            {"column_id": "PHONE_NUMBER", "string_value": PHONE},
            {"column_name": "Marketing consent", "string_value": "No"},
        ],
    }
    resp = await client.post(f"/lead-intake/{t['slug']}/google-ads", json=body)
    assert resp.json()["status"] == "no_consent"
    assert dialer.calls == []
    assert await _consents(admin_engine) == []


# ---- rule 3: generic sources -------------------------------------------------------------------


async def test_generic_source_needs_owner_attestation(
    client: httpx.AsyncClient, fakes: Any, admin_engine: AsyncEngine
) -> None:
    dialer, _ = fakes
    t = await ready_tenant(client)
    await attest(client, t, "zapier", on=False)
    stored = (await send_lead(client, t, {"phone": PHONE, "source": "zapier"})).json()
    assert stored["status"] == "no_attestation"
    assert dialer.calls == []
    assert await _consents(admin_engine) == []
    lead = (await client.get("/v1/leads", headers=t["headers"])).json()["items"][0]
    assert lead["status"] == "no_attestation"

    resp = await client.patch(
        "/v1/leads/sources/zapier",
        json={"consent_attested": True, "attestation_lang": "hi"},
        headers=t["headers"],
    )
    source = resp.json()
    assert source["consent_policy"] == "owner_attestation"
    assert source["attested_by"] == t["owner"].name
    assert source["attested_at"] is not None
    async with admin_engine.connect() as conn:
        rows = list(
            await conn.execute(
                text(
                    "SELECT * FROM lead_consent_attestation"
                    " WHERE source = 'zapier' ORDER BY attested_at"
                )
            )
        )
    assert rows[0].revoked_at is not None  # the first tick (from setup) was withdrawn
    assert rows[-1].revoked_at is None
    assert rows[-1].user_id == t["owner"].user_id
    assert rows[-1].text == "इन लोगों ने अपनी enquiry के बारे में संपर्क करने को कहा है।"

    await client.patch("/v1/leads/setup", json={"dedupe_minutes": 0}, headers=t["headers"])
    called = (await send_lead(client, t, {"phone": PHONE, "source": "zapier"})).json()
    assert called["status"] == "queued"
    [consent] = await _consents(admin_engine)
    assert consent.source == "owner_attested"
    assert consent.text_version == "attest-v1"


async def test_attestation_only_for_generic_sources(client: httpx.AsyncClient, fakes: Any) -> None:
    t = await ready_tenant(client)
    for kind in ("meta", "website_form"):
        resp = await client.patch(
            f"/v1/leads/sources/{kind}", json={"consent_attested": True}, headers=t["headers"]
        )
        assert resp.status_code == 422
    sources = (await client.get("/v1/leads/setup", headers=t["headers"])).json()["sources"]
    policy = {s["kind"]: s["consent_policy"] for s in sources}
    assert policy["meta"] == "portal_enquiry"
    assert policy["google_forms"] == "form_checkbox"
    assert policy["google_sheets"] == "owner_attestation"


# ---- rule 4: promotional untouched -------------------------------------------------------------


async def test_lead_consent_never_allows_promotional_calls(
    client: httpx.AsyncClient, fakes: Any, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    assert (await send_lead(client, t, {"phone": PHONE})).json()["status"] == "queued"
    configure(promotional_calling_enabled=True)  # even with 140-series calling switched on
    result = await _check(client, t, clock.now, purpose="promotional")
    assert result["decision"] == "block"
    assert "no_consent" in _codes(result)
