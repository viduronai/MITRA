"""Campaign list consent (docs/08 section 8.5) and honest progress counts."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select

from mitra_core.db import tenant_session
from mitra_core.dialer import consent as list_consent
from mitra_core.models import ConsentRecord
from mitra_core.tenancy import TenantContext
from tests.dialer_helpers import configure, morning_clock, opt_out, tenant, tick
from tests.helpers import FakeClock

CSV = "Name,Phone\nRavi,9876500001\nLakshmi,9876500002\nArjun,9876500003\n"
PHONES = ["+919876500001", "+919876500002", "+919876500003"]


async def _create(client: httpx.AsyncClient, t: dict[str, Any], **extra: Any) -> dict[str, Any]:
    body = {"name": "Diwali offer", "employee_id": t["employee"]["id"], "text": CSV} | extra
    resp = await client.post("/v1/campaigns", json=body, headers=t["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()["campaign"]  # type: ignore[no-any-return]


async def _records(business_id: str) -> list[ConsentRecord]:
    bid = uuid.UUID(business_id)
    async with tenant_session(TenantContext(business_id=bid)) as s:
        return list(await s.scalars(select(ConsentRecord).where(ConsentRecord.business_id == bid)))


async def test_list_needs_the_owners_tick(client: httpx.AsyncClient, clock: FakeClock) -> None:
    """Without the tick nothing starts; with it the pasted list is actually called."""
    voice, _ = configure()
    morning_clock(clock)
    t = await tenant(client)  # nobody on the list has any consent on record yet
    campaign = await _create(client, t)
    assert campaign["consent"] is None
    url = f"/v1/campaigns/{campaign['id']}/start"
    refused = await client.post(url, headers=t["headers"])
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "consent_required"

    started = await client.post(
        url,
        json={"consent_attested": True, "consent_language": "te"},
        headers=t["headers"],
    )
    assert started.status_code == 200, started.text
    consent = started.json()["consent"]
    assert consent["scope"] == "service"
    assert consent["text"] == list_consent.SERVICE_TEXTS["te"]
    assert consent["text_version"] == list_consent.VERSION
    assert consent["by_name"] == t["owner"].name

    records = await _records(t["business"]["id"])
    assert len(records) == 3
    for r in records:
        assert r.source == "owner_attested_list"
        assert r.scope == "service"
        assert r.purpose == f"campaign:{uuid.UUID(campaign['id']).hex[:31]}"
        assert r.consent_text == list_consent.SERVICE_TEXTS["te"]
        assert r.expires_at == clock.now + timedelta(days=30)

    assert (await tick(client))["dialed"] == 3  # the gate allows them: no "No consent on record"
    assert sorted(p.phone_e164 for p in voice.placed) == PHONES


async def test_consent_ends_with_the_campaign(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    morning_clock(clock)
    t = await tenant(client)
    ends_on = (clock.now + timedelta(days=3)).date()
    campaign = await _create(client, t, consent_attested=True, ends_on=ends_on.isoformat())
    await client.post(f"/v1/campaigns/{campaign['id']}/start", headers=t["headers"])
    [first, *_] = await _records(t["business"]["id"])
    assert first.expires_at is not None
    assert first.expires_at < clock.now + timedelta(days=4)  # the last calling day, not 30 days

    clock.advance(3600)
    await client.post(f"/v1/campaigns/{campaign['id']}/cancel", headers=t["headers"])
    assert {r.expires_at for r in await _records(t["business"]["id"])} == {clock.now}


async def test_promotional_list_needs_both_statements(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure()
    morning_clock(clock)
    t = await tenant(client)
    text = await client.get(
        "/v1/campaigns/consent-text?purpose=promotional&language=hi", headers=t["headers"]
    )
    assert text.json()["text"] == (
        f"{list_consent.SERVICE_TEXTS['hi']} {list_consent.PROMOTIONAL_TEXTS['hi']}"
    )
    campaign = await _create(
        client, t, purpose="promotional", consent_attested=True, consent_language="hi"
    )
    assert campaign["consent"]["scope"] == "promotional"
    await client.post(f"/v1/campaigns/{campaign['id']}/start", headers=t["headers"])
    assert {r.scope for r in await _records(t["business"]["id"])} == {"promotional"}
    # DND / 140-series rules still decide at dial time: promotional calling is off by default.
    report = await tick(client)
    assert report["dialed"] == 0


async def test_adding_people_to_a_live_list_needs_the_tick(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure()
    morning_clock(clock)
    t = await tenant(client)
    campaign = await _create(client, t, consent_attested=True)
    await client.post(f"/v1/campaigns/{campaign['id']}/start", headers=t["headers"])
    url = f"/v1/campaigns/{campaign['id']}/contacts"
    more = {"text": "Phone\n9876500004\n"}
    refused = await client.post(url, json=more, headers=t["headers"])
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "consent_required"
    added = await client.post(url, json=more | {"consent_attested": True}, headers=t["headers"])
    assert added.status_code == 200, added.text
    assert added.json()["added"] == 1
    assert len(await _records(t["business"]["id"])) == 4


async def test_blocked_people_are_not_counted_as_called(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure()
    morning_clock(clock)
    t = await tenant(client)
    await opt_out(client, t, *PHONES)  # all three asked not to be called
    campaign = await _create(client, t, consent_attested=True)
    await client.post(f"/v1/campaigns/{campaign['id']}/start", headers=t["headers"])
    await tick(client)
    detail = (await client.get(f"/v1/campaigns/{campaign['id']}", headers=t["headers"])).json()
    p = detail["progress"]
    assert (p["called"], p["blocked"], p["remaining"]) == (0, 3, 0)


async def test_paused_campaign_has_no_eta(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    morning_clock(clock)
    t = await tenant(client)
    campaign = await _create(client, t, consent_attested=True)
    assert campaign["progress"]["eta_minutes"] == 1  # draft: estimate for the review
    await client.post(f"/v1/campaigns/{campaign['id']}/start", headers=t["headers"])
    paused = await client.post(f"/v1/campaigns/{campaign['id']}/pause", headers=t["headers"])
    assert paused.json()["status"] == "paused"
    assert paused.json()["progress"]["eta_minutes"] is None
    assert paused.json()["progress"]["called"] == 0
