"""Simulated test calls: status progression (injected clock), transcript, corrections."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from tests.helpers import (
    FakeClock,
    add_fact,
    add_member,
    create_business,
    create_employee,
    new_actor,
)


async def _setup(client: httpx.AsyncClient, **business: Any) -> tuple[dict[str, str], str]:
    owner = new_actor()
    biz = await create_business(client, owner, **business)
    employee = await create_employee(client, owner, biz["id"], name="Priya")
    return owner.headers(biz["id"]), employee["id"]


async def _call(client: httpx.AsyncClient, headers: dict[str, str], employee_id: str) -> str:
    resp = await client.post("/v1/test-calls", json={"employee_id": employee_id}, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body == {"id": body["id"], "status": "queued", "simulated": True}
    return str(body["id"])


async def _get(client: httpx.AsyncClient, headers: dict[str, str], call_id: str) -> dict[str, Any]:
    resp = await client.get(f"/v1/test-calls/{call_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def _employee_lines(call: dict[str, Any]) -> list[str]:
    return [line["text"] for line in call["transcript"] if line["speaker"] == "employee"]


async def test_status_progresses_with_time(client: httpx.AsyncClient, clock: FakeClock) -> None:
    headers, employee_id = await _setup(client)
    call_id = await _call(client, headers, employee_id)

    seen = []
    for _ in range(4):
        call = await _get(client, headers, call_id)
        assert call["simulated"] is True
        seen.append((call["status"], len(call["transcript"]), call["summary"] is not None))
        clock.advance(2)
    total = len(call["transcript"])
    assert [s[0] for s in seen] == ["queued", "ringing", "connected", "completed"]
    assert seen[0][1] == seen[1][1] == 0
    assert 0 < seen[2][1] < total
    assert [s[2] for s in seen] == [False, False, False, True]
    clock.advance(3600)
    assert (await _get(client, headers, call_id))["status"] == "completed"

    times = [line["at_ms"] for line in call["transcript"]]
    assert times == sorted(times)
    assert times[0] == 0


async def test_transcript_answers_from_confirmed_facts_only(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    headers, employee_id = await _setup(client, name="Sunrise Clinic")
    await add_fact(client, headers, "prices", "Consultation fee", "₹500")
    await add_fact(client, headers, "timings", "Timings", "Mon-Sat 9 AM to 8 PM")
    suggested = await add_fact(client, headers, "location", "Address", "Road No. 3, Madhapur")
    await client.patch(
        f"/v1/knowledge/facts/{suggested['id']}", json={"status": "suggested"}, headers=headers
    )
    call_id = await _call(client, headers, employee_id)
    clock.advance(10)
    call = await _get(client, headers, call_id)

    lines = _employee_lines(call)
    assert "Thank you for calling Sunrise Clinic. This is Priya" in lines[0]
    assert "The consultation fee is ₹500." in lines
    assert "Our timings are Mon-Sat 9 AM to 8 PM." in lines
    assert not any("Madhapur" in line for line in lines)  # not confirmed => not said
    assert any("exact location on WhatsApp" in line for line in lines)
    assert "answered 2 of 3" in call["summary"]
    assert "location" in call["summary"]
    callers = [line["text"] for line in call["transcript"] if line["speaker"] == "caller"]
    assert callers[0] == "Hi, what is the consultation fee?"


async def test_missing_fee_is_politely_deferred_and_greeting_is_used(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    headers, employee_id = await _setup(client)
    greeting = "Namaskaram! Sunrise Clinic nunchi Priya maatladutunnanu."
    await client.patch(f"/v1/employees/{employee_id}", json={"greeting": greeting}, headers=headers)
    call_id = await _call(client, headers, employee_id)
    clock.advance(10)
    lines = _employee_lines(await _get(client, headers, call_id))
    assert lines[0] == greeting
    assert any("confirm the exact fee" in line for line in lines)


async def test_real_estate_script(client: httpx.AsyncClient, clock: FakeClock) -> None:
    headers, employee_id = await _setup(client, name="Green Homes", industry="real_estate")
    await add_fact(client, headers, "timings", "Site visit timings", "Sat-Sun 10 AM to 5 PM")
    call_id = await _call(client, headers, employee_id)
    clock.advance(10)
    call = await _get(client, headers, call_id)
    assert "Of course! Site visit timings: Sat-Sun 10 AM to 5 PM." in _employee_lines(call)
    assert call["transcript"][1]["text"].startswith("Hi, I saw your ad")


async def test_knowledge_correction_upserts_confirmed_fact(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    headers, employee_id = await _setup(client)
    call_id = await _call(client, headers, employee_id)
    url = f"/v1/test-calls/{call_id}/corrections"

    resp = await client.post(
        url, json={"text": "Say the consultation fee is ₹500"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["applied_to"] == "knowledge"
    assert "Consultation fee: ₹500" in body["change_summary"]
    facts = (await client.get("/v1/knowledge/facts", headers=headers)).json()
    assert [(f["category"], f["key"], f["value"], f["status"]) for f in facts] == [
        ("prices", "Consultation fee", "₹500", "confirmed")
    ]
    assert body["fact_id"] == facts[0]["id"]

    resp = await client.post(url, json={"text": "The consultation fee is ₹600."}, headers=headers)
    assert resp.json()["fact_id"] == facts[0]["id"]
    assert "Updated" in resp.json()["change_summary"]
    facts = (await client.get("/v1/knowledge/facts", headers=headers)).json()
    assert [f["value"] for f in facts] == ["₹600"]

    # A re-test now answers with the corrected fact.
    retest = await _call(client, headers, employee_id)
    clock.advance(10)
    assert "The consultation fee is ₹600." in _employee_lines(await _get(client, headers, retest))


async def test_behaviour_corrections(client: httpx.AsyncClient) -> None:
    headers, employee_id = await _setup(client)
    call_id = await _call(client, headers, employee_id)
    url = f"/v1/test-calls/{call_id}/corrections"
    never = await client.post(
        url, json={"text": "Don't promise same-day appointments"}, headers=headers
    )
    ask = await client.post(url, json={"text": "Ask for the patient's age"}, headers=headers)
    again = await client.post(url, json={"text": "Ask for the patient's age"}, headers=headers)
    assert never.json()["applied_to"] == ask.json()["applied_to"] == "behaviour"
    assert again.status_code == 201
    behaviour = (await client.get(f"/v1/employees/{employee_id}", headers=headers)).json()[
        "behaviour"
    ]
    assert behaviour == {
        "ask_for": ["Ask for the patient's age"],
        "never_say": ["Don't promise same-day appointments"],
        "transfer_when": [],
    }


async def test_behaviour_list_limit(client: httpx.AsyncClient) -> None:
    headers, employee_id = await _setup(client)
    full = {"ask_for": [f"Ask item {i}" for i in range(20)]}
    resp = await client.patch(
        f"/v1/employees/{employee_id}", json={"behaviour": full}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    call_id = await _call(client, headers, employee_id)
    resp = await client.post(
        f"/v1/test-calls/{call_id}/corrections", json={"text": "Ask for email"}, headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "behaviour_full"


async def test_custom_phone_is_stored_as_last4_only(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    headers, employee_id = await _setup(client)
    resp = await client.post(
        "/v1/test-calls",
        json={"employee_id": employee_id, "phone": "+919123456789"},
        headers=headers,
    )
    call = await _get(client, headers, resp.json()["id"])
    assert call["phone_last4"] == "6789"
    async with admin_engine.connect() as conn:
        row = (await conn.execute(text("SELECT phone_hash FROM test_call"))).scalar_one()
    assert "9123456789" not in row


async def test_validation_and_errors(client: httpx.AsyncClient, admin_engine: AsyncEngine) -> None:
    headers, employee_id = await _setup(client)
    for body in (
        {"employee_id": "nope"},
        {"employee_id": employee_id, "phone": "12345"},
        {"employee_id": employee_id, "extra": True},
    ):
        resp = await client.post("/v1/test-calls", json=body, headers=headers)
        assert resp.status_code == 422, body
    resp = await client.post(
        "/v1/test-calls", json={"employee_id": str(uuid.uuid4())}, headers=headers
    )
    assert resp.status_code == 404
    assert (await client.get(f"/v1/test-calls/{uuid.uuid4()}", headers=headers)).status_code == 404
    call_id = await _call(client, headers, employee_id)
    for bad in ("", "x" * 301):
        resp = await client.post(
            f"/v1/test-calls/{call_id}/corrections", json={"text": bad}, headers=headers
        )
        assert resp.status_code == 422


async def test_staff_can_watch_but_not_start_or_correct(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    owner = new_actor()
    biz = await create_business(client, owner)
    employee = await create_employee(client, owner, biz["id"])
    call_id = await _call(client, owner.headers(biz["id"]), employee["id"])
    staff = (await add_member(admin_engine, biz["id"], MemberRole.STAFF)).headers(biz["id"])
    assert (await client.get(f"/v1/test-calls/{call_id}", headers=staff)).status_code == 200
    resp = await client.post("/v1/test-calls", json={"employee_id": employee["id"]}, headers=staff)
    assert resp.status_code == 403
    resp = await client.post(
        f"/v1/test-calls/{call_id}/corrections", json={"text": "Fee is ₹1"}, headers=staff
    )
    assert resp.status_code == 403


async def test_create_is_idempotent(client: httpx.AsyncClient) -> None:
    headers, employee_id = await _setup(client)
    keyed = headers | {"Idempotency-Key": "call-1"}
    body = {"employee_id": employee_id}
    first = await client.post("/v1/test-calls", json=body, headers=keyed)
    second = await client.post("/v1/test-calls", json=body, headers=keyed)
    assert first.json() == second.json()
    assert second.headers["idempotent-replayed"] == "true"
