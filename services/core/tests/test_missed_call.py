"""Missed-call number (CALL-20): reject, call back via the dialer, consent, abuse guards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.phones import unseal_phone
from tests.dialer_helpers import MONDAY_MORNING, SVC, configure, tenant, tick
from tests.helpers import FakeClock
from tests.manager_helpers import wa_messages
from tests.test_calls import PHONE, configure_service, end, make_tenant, start

CALLER = "+919812300001"
# Monday 2 Nov 2026, 23:00 IST: outside calling hours.
MONDAY_NIGHT = datetime(2026, 11, 2, 17, 30, tzinfo=UTC)


async def _missed_number(client: httpx.AsyncClient, t: dict[str, Any]) -> dict[str, Any]:
    resp = await client.put(
        "/v1/missed-call/number", json={"phone_number_id": t["number_id"]}, headers=t["headers"]
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def _miss(
    client: httpx.AsyncClient, to: str, caller: str = CALLER, at: datetime = MONDAY_MORNING
) -> dict[str, Any]:
    resp = await client.post(
        "/internal/v1/telephony/missed-calls",
        json={"to": to, "from": caller, "at": at.isoformat(), "carrier_call_sid": "SIM1"},
        headers=SVC,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def test_missed_call_is_called_back_within_a_minute(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    voice, _ = configure()
    t = await tenant(client)
    setup = await _missed_number(client, t)
    e164 = setup["e164"]
    assert setup["live"] is True
    assert setup["tel_uri"] == f"tel:{e164}"
    assert setup["display"] in setup["poster"]["en"]
    assert "मिस्ड कॉल" in setup["poster"]["hi"]
    assert "మిస్డ్ కాల్" in setup["poster"]["te"]

    # The voice service learns not to answer this number.
    resolved = await client.get(
        "/internal/v1/telephony/resolve", params={"to": e164, "from": CALLER}, headers=SVC
    )
    assert resolved.json()["missed_call"] is True

    first = await _miss(client, e164)
    assert first["status"] == "queued"
    assert first["deferred"] is False
    due = datetime.fromisoformat(first["call_back_at"])
    assert timedelta(0) < due - MONDAY_MORNING <= timedelta(minutes=1)
    # Calling again within the dedupe window does not queue a second call.
    assert (await _miss(client, e164))["status"] == "deduped"

    async with admin_engine.connect() as conn:
        job = (
            await conn.execute(
                text("SELECT purpose, source, called_number_id, phone_enc FROM outbound_job")
            )
        ).one()
        consent = (await conn.execute(text("SELECT source, scope FROM consent_record"))).all()
        enc = (await conn.execute(text("SELECT phone_enc FROM contact"))).scalar_one()
    assert (job.purpose, job.source, str(job.called_number_id)) == (
        "callback",
        "missed_call",
        t["number_id"],
    )
    assert [(c.source, c.scope) for c in consent] == [("missed_call", "service")]
    assert enc.startswith("v2:")

    # The dialer places it from the number the customer called, after compliance.
    clock.now = MONDAY_MORNING + timedelta(minutes=1)
    assert (await tick(client))["dialed"] == 1
    placed = voice.placed[0]
    assert placed.phone_e164 == CALLER
    assert placed.caller_id == e164
    assert placed.purpose == "callback"

    stats = (await client.get("/v1/missed-call", headers=t["headers"])).json()
    assert stats["stats"]["missed"] == 2
    assert stats["stats"]["called_back"] == 1
    assert [r["status"] for r in stats["recent"]] == ["deduped", "queued"]
    assert CALLER not in str(stats)


async def test_outside_hours_waits_for_the_morning_and_says_so_on_whatsapp(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure()
    t = await tenant(client)
    e164 = (await _missed_number(client, t))["e164"]
    out = await _miss(client, e164, at=MONDAY_NIGHT)
    assert out["deferred"] is True
    # 9:00 IST next day = 03:30 UTC.
    assert datetime.fromisoformat(out["call_back_at"]) == datetime(2026, 11, 3, 3, 30, tzinfo=UTC)
    msgs = await wa_messages(admin_engine, t["business"]["id"])
    assert len(msgs) == 1
    assert msgs[0]["kind"] == "template"
    assert "9:00 am" in str(msgs[0])


async def test_block_list_and_rate_limits(client: httpx.AsyncClient) -> None:
    configure()
    t = await tenant(client)
    e164 = (await _missed_number(client, t))["e164"]
    first = await _miss(client, e164)
    resp = await client.post(
        "/v1/missed-call/blocks",
        json={"missed_call_id": first["id"], "reason": "prank calls"},
        headers=t["headers"],
    )
    assert resp.status_code == 201, resp.text
    block = resp.json()
    assert block["phone_masked"].endswith("0001")
    again = await client.post(
        "/v1/missed-call/blocks", json={"missed_call_id": first["id"]}, headers=t["headers"]
    )
    assert again.status_code == 409
    assert (await _miss(client, e164))["status"] == "blocked"
    resp = await client.delete(f"/v1/missed-call/blocks/{block['id']}", headers=t["headers"])
    assert resp.status_code == 204

    # Per caller: at most 3 callbacks a day (each 31 minutes apart, past the dedupe window).
    statuses = [
        (await _miss(client, e164, at=MONDAY_MORNING + timedelta(minutes=31 * i)))["status"]
        for i in range(1, 4)
    ]
    assert statuses == ["queued", "queued", "rate_limited"]


async def test_only_missed_call_numbers_and_owner_controls(client: httpx.AsyncClient) -> None:
    configure()
    t = await tenant(client)
    setup = (await client.get("/v1/missed-call", headers=t["headers"])).json()
    assert setup["phone_number_id"] is None
    number = (await client.get("/v1/phone-numbers", headers=t["headers"])).json()["items"][0]
    resp = await client.post(
        "/internal/v1/telephony/missed-calls",
        json={"to": number["e164"], "from": CALLER},
        headers=SVC,
    )
    assert resp.status_code == 409
    await _missed_number(client, t)
    listed = (await client.get("/v1/phone-numbers", headers=t["headers"])).json()["items"][0]
    assert listed["missed_call"] is True
    off = await client.put(
        "/v1/missed-call/number", json={"phone_number_id": None}, headers=t["headers"]
    )
    assert off.json()["phone_number_id"] is None
    other = await tenant(client)
    resp = await client.put(
        "/v1/missed-call/number",
        json={"phone_number_id": t["number_id"]},
        headers=other["headers"],
    )
    assert resp.status_code == 404


async def test_missed_inbound_call_is_rescued_with_a_callback(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    """CALL-02: the caller hung up before speaking; the rescue routine queues a ``callback``
    with the number now on file (encrypted), no dialer history needed."""
    configure_service()
    t = await make_tenant(client)
    resp = await client.post(
        "/v1/routines/from-library",
        json={"library_id": "missed_call_rescue", "enabled": True},
        headers=t["headers"],
    )
    assert resp.status_code == 201, resp.text
    call_id = (await start(client, t["employee"]["id"])).json()["id"]
    resp = await end(client, call_id, t["employee"]["id"], transcript=[], actions=[])
    assert resp.status_code == 200, resp.text
    async with admin_engine.connect() as conn:
        result = (
            await conn.execute(text("SELECT result FROM call WHERE id = :i"), {"i": call_id})
        ).scalar_one()
        job = (
            await conn.execute(
                text("SELECT business_id, purpose, dedupe_key, phone_enc FROM outbound_job")
            )
        ).one()
        logged = (await conn.execute(text("SELECT purpose, actor FROM phone_access_log"))).all()
    assert result == "missed"
    assert job.purpose == "callback"
    assert job.dedupe_key.startswith("callback:")
    assert unseal_phone(job.business_id, job.phone_enc) == PHONE
    assert [(r.purpose, r.actor) for r in logged] == [("team_follow_up", "team")]
