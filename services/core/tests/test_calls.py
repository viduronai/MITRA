"""Calls: internal ingest, post-call pipeline, owner-facing calls / customers / home APIs."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import Settings, get_settings
from mitra_core.main import app
from mitra_core.models.enums import MemberRole
from tests.helpers import add_member, bearer, create_business, create_employee, new_actor

TOKEN = "test-service-token-0123456789abcdef"
PHONE = "+919812345678"


def configure_service() -> None:
    settings = Settings(service_token=SecretStr(TOKEN))
    app.dependency_overrides[get_settings] = lambda: settings


async def make_tenant(client: httpx.AsyncClient, name: str = "Sunrise Clinic") -> dict[str, Any]:
    owner = new_actor()
    business = await create_business(client, owner, name=name)
    emp = await create_employee(client, owner, business["id"])
    return {
        "owner": owner,
        "headers": owner.headers(business["id"]),
        "business": business,
        "employee": emp,
    }


async def start(
    client: httpx.AsyncClient,
    employee_id: str,
    *,
    call_id: str | None = None,
    phone: str | None = PHONE,
    started_at: datetime | None = None,
    **extra: Any,
) -> httpx.Response:
    body: dict[str, Any] = {
        "id": call_id or str(uuid.uuid4()),
        "employee_id": employee_id,
        "direction": "inbound",
        "started_at": (started_at or datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
        "language": "te",
        **extra,
    }
    if phone:
        body["caller_phone"] = phone
    return await client.post("/internal/v1/calls", json=body, headers=bearer(TOKEN))


BOOKING_TRANSCRIPT = [
    {"role": "assistant", "text": "Namaskaram, Sunrise Clinic nunchi Priya. Nenu AI assistant."},
    {"role": "user", "text": "Doctor appointment kavali repu evening, consultation fee entha?"},
    {"role": "assistant", "text": "Fee ₹500. Repu 6:15 pm ki slot undi. Mee peru?"},
    {"role": "user", "text": "Ravi Kumar. Thank you!"},
    {"role": "user", "text": "Do you have parking near the clinic?"},
    {"role": "assistant", "text": "I'll check with the team and get back to you on parking."},
]
BOOKING_ACTIONS = [
    {"name": "check_availability", "args": {"date": "2026-10-21"}, "result": {"available": True}},
    {
        "name": "book_slot",
        "args": {"date": "2026-10-21", "time": "18:15", "name": "Ravi Kumar"},
        "result": {
            "status": "booked",
            "booking_id": "SC-1001",
            "date": "2026-10-21",
            "time": "18:15",
        },
    },
    {
        "name": "send_whatsapp_template",
        "args": {"template": "booking_confirmation"},
        "result": {"status": "queued"},
    },
]


async def end(
    client: httpx.AsyncClient,
    call_id: str,
    employee_id: str,
    *,
    transcript: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> httpx.Response:
    body = {
        "employee_id": employee_id,
        "ended_at": datetime.now(UTC).isoformat(),
        "transcript": BOOKING_TRANSCRIPT if transcript is None else transcript,
        "actions": BOOKING_ACTIONS if actions is None else actions,
        "language": "te",
        "latency_stats": {"p50_ms": 640, "p95_ms": 910},
        "usage": {"stt_seconds": 120.0},
        **extra,
    }
    return await client.post(f"/internal/v1/calls/{call_id}/end", json=body, headers=bearer(TOKEN))


async def booked_call(client: httpx.AsyncClient, t: dict[str, Any], **kw: Any) -> str:
    resp = await start(client, t["employee"]["id"], **kw)
    assert resp.status_code == 201, resp.text
    call_id: str = resp.json()["id"]
    resp = await end(client, call_id, t["employee"]["id"])
    assert resp.status_code == 200, resp.text
    return call_id


# --- internal ingest --------------------------------------------------------------------------


async def test_ingest_requires_service_token(client: httpx.AsyncClient) -> None:
    resp = await client.post("/internal/v1/calls", json={}, headers=bearer("x"))
    assert resp.status_code == 503  # unset outside env=local: disabled
    configure_service()
    t = await make_tenant(client)
    body = {
        "id": str(uuid.uuid4()),
        "employee_id": t["employee"]["id"],
        "started_at": datetime.now(UTC).isoformat(),
    }
    assert (await client.post("/internal/v1/calls", json=body)).status_code == 401
    resp = await client.post("/internal/v1/calls", json=body, headers=t["headers"])
    assert resp.status_code == 401  # a user token is not a service token


async def test_start_is_idempotent_and_never_stores_raw_phone(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)
    call_id = str(uuid.uuid4())
    first = await start(client, t["employee"]["id"], call_id=call_id)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "live"
    assert first.json()["caller"]["returning"] is False
    again = await start(client, t["employee"]["id"], call_id=call_id)
    assert again.status_code == 200
    assert again.json()["id"] == call_id

    async with admin_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM call"))).scalar_one() == 1
        row = (await conn.execute(text("SELECT phone_hash, phone_last4 FROM contact"))).one()
        assert row.phone_last4 == "5678"
        assert PHONE not in row.phone_hash
        assert len(row.phone_hash) == 64
        dump = (await conn.execute(text("SELECT row_to_json(c)::text FROM call c"))).scalar_one()
        assert "9812345678" not in dump

    bad = await start(client, t["employee"]["id"], phone="98123")
    assert bad.status_code == 422
    unknown = await start(client, str(uuid.uuid4()))
    assert unknown.status_code == 404


async def test_end_runs_post_call_pipeline(client: httpx.AsyncClient) -> None:
    configure_service()
    t = await make_tenant(client)
    call_id = await booked_call(client, t)

    detail = (await client.get(f"/v1/calls/{call_id}", headers=t["headers"])).json()
    assert detail["status"] == "processed"
    assert detail["result"] == "booked"
    assert detail["employee_name"] == "Priya"
    assert detail["contact_name"] == "Ravi Kumar"
    assert detail["fields"]["appointment"] == "Wed 21 Oct, 6:15 pm"
    assert detail["sentiment"] == "positive"
    assert "Booked for Wed 21 Oct, 6:15 pm" in detail["summary"]
    assert len(detail["summary"].split()) <= 80
    assert [line["speaker"] for line in detail["transcript"][:2]] == ["employee", "caller"]
    labels = [a["label"] for a in detail["actions"]]
    assert labels == ["Booked Wed 21 Oct, 6:15 pm", "WhatsApp sent: booking confirmation"]
    assert detail["unknown_questions"] == ["Do you have parking near the clinic?"]
    assert {a["kind"] for a in detail["alerts"]} == {"unknown_question"}
    assert detail["duration_seconds"] >= 170

    # Replaying the end report changes nothing.
    replay = await end(client, call_id, t["employee"]["id"], actions=[])
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    again = (await client.get(f"/v1/calls/{call_id}", headers=t["headers"])).json()
    assert len(again["actions"]) == 2

    # Memory: stated facts confirmed, guesses inferred with an expiry.
    customer = (
        await client.get(f"/v1/customers/{detail['contact_id']}", headers=t["headers"])
    ).json()
    memory = {m["key"]: m for m in customer["memory"]}
    assert memory["name"]["status"] == "confirmed"
    assert memory["name"]["value"] == "Ravi Kumar"
    assert memory["preferred_language"]["status"] == "inferred"
    assert memory["preferred_language"]["expires_at"] is not None
    assert memory["preferred_time"]["value"] == "evening"
    assert customer["tags"] == ["booked"]
    assert customer["next_step"] == "Appointment Wed 21 Oct, 6:15 pm"
    kinds = [e["kind"] for e in customer["timeline"]]
    assert {"call", "action", "commitment"} <= set(kinds)

    # Unknown questions feed the knowledge gaps inbox.
    gaps = (await client.get("/v1/knowledge/gaps", headers=t["headers"])).json()
    from_calls = [g for g in gaps if g["source"] == "call"]
    assert from_calls[0]["question"] == "Do you have parking near the clinic?"
    assert from_calls[0]["call_id"] == call_id


async def test_returning_caller_gets_memory_card(client: httpx.AsyncClient) -> None:
    configure_service()
    t = await make_tenant(client)
    await booked_call(client, t)
    resp = await start(client, t["employee"]["id"])
    card = resp.json()["caller"]
    assert card["returning"] is True
    assert card["name"] == "Ravi Kumar"
    assert card["language"] == "te"
    assert any(m["key"] == "name" and m["status"] == "confirmed" for m in card["memory"])
    assert len(card["recent_summaries"]) == 1
    assert card["open_commitments"] == ["Appointment Wed 21 Oct, 6:15 pm"]


async def test_missed_and_callback_results_and_alerts(client: httpx.AsyncClient) -> None:
    configure_service()
    t = await make_tenant(client)
    emp = t["employee"]["id"]
    missed = (await start(client, emp)).json()["id"]
    await end(client, missed, emp, transcript=[{"role": "assistant", "text": "Hello?"}], actions=[])
    angry = (await start(client, emp, phone="+919811111111")).json()["id"]
    await end(
        client,
        angry,
        emp,
        transcript=[{"role": "user", "text": "This is the worst service, very bad, call me back"}],
        actions=[
            {"name": "schedule_callback", "args": {"topic": "refund"}, "result": {"ok": 1}},
            {"name": "alert_staff", "args": {"reason": "angry", "urgency": "urgent"}},
            {"name": "send_whatsapp_template", "args": {}, "result": {"error": "boom"}},
        ],
    )
    h = t["headers"]
    d1 = (await client.get(f"/v1/calls/{missed}", headers=h)).json()
    assert d1["result"] == "missed"
    assert d1["summary"] == "Missed call: nobody spoke."
    d2 = (await client.get(f"/v1/calls/{angry}", headers=h)).json()
    assert d2["result"] == "call_back"
    assert d2["sentiment"] == "negative"
    assert {a["kind"] for a in d2["alerts"]} == {
        "angry",
        "urgent",
        "failed_action",
        "unknown_question",
    }
    assert d2["next_step"].startswith("Call back: refund")

    home = (await client.get("/v1/home/summary", headers=h)).json()
    assert home["has_calls"] is True
    assert home["stats"]["calls_today"] == 2
    assert home["stats"]["needs_you"] == 4
    assert home["needs_you"][0]["call_id"] == angry
    assert len(home["recent_calls"]) == 2

    # The caller who missed us is reached later today: a rescued missed call.
    later = (await start(client, emp)).json()["id"]
    await end(client, later, emp)
    home = (await client.get("/v1/home/summary", headers=h)).json()
    assert home["stats"]["rescued_today"] == 1
    assert home["stats"]["booked_today"] == 1


async def test_call_list_filters_search_and_rating(client: httpx.AsyncClient) -> None:
    configure_service()
    t = await make_tenant(client)
    h = t["headers"]
    booked = await booked_call(client, t)
    other = (await start(client, t["employee"]["id"], phone=None, language="hi")).json()["id"]
    await end(
        client,
        other,
        t["employee"]["id"],
        language="hi",
        transcript=[{"role": "user", "text": "Aapke yahan MRI scan hota hai kya?"}],
        actions=[],
    )

    def ids(resp: httpx.Response) -> list[str]:
        assert resp.status_code == 200, resp.text
        return [c["id"] for c in resp.json()["items"]]

    assert set(ids(await client.get("/v1/calls", headers=h))) == {booked, other}
    assert ids(await client.get("/v1/calls?result=booked", headers=h)) == [booked]
    assert ids(await client.get("/v1/calls?result=info_only&result=booked", headers=h)) != []
    assert ids(await client.get("/v1/calls?language=hi", headers=h)) == [other]
    assert ids(await client.get("/v1/calls?q=mri%20SCAN", headers=h)) == [other]
    assert ids(await client.get("/v1/calls?q=100%25", headers=h)) == []
    assert ids(await client.get("/v1/calls?q=ravi", headers=h)) == [booked]
    emp = t["employee"]["id"]
    assert len(ids(await client.get(f"/v1/calls?employee_id={emp}", headers=h))) == 2
    assert ids(await client.get("/v1/calls?date_to=2020-01-01", headers=h)) == []

    resp = await client.post(
        f"/v1/calls/{booked}/rating", json={"rating": "down", "reason": "Too fast"}, headers=h
    )
    assert resp.status_code == 200, resp.text
    detail = (await client.get(f"/v1/calls/{booked}", headers=h)).json()
    assert (detail["rating"], detail["rating_reason"]) == ("down", "Too fast")
    bad = await client.post(f"/v1/calls/{booked}/rating", json={"rating": "meh"}, headers=h)
    assert bad.status_code == 422


async def test_export_csv_neutralises_formulas(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)
    call_id = await booked_call(client, t)
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE call SET summary = '=HYPERLINK(\"x\")' WHERE id = :id"), {"id": call_id}
        )
    resp = await client.get("/v1/calls/export.csv", headers=t["headers"])
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(resp.text.lstrip("﻿"))))
    assert rows[0][0] == "started_at"
    assert rows[1][8] == '\'=HYPERLINK("x")'
    assert rows[1][3] == "5678"

    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    resp = await client.get("/v1/calls/export.csv", headers=staff.headers(t["business"]["id"]))
    assert resp.status_code == 403


async def test_memory_edit_delete_and_forget(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)
    h = t["headers"]
    call_id = await booked_call(client, t)
    contact_id = (await client.get(f"/v1/calls/{call_id}", headers=h)).json()["contact_id"]

    listing = (await client.get("/v1/customers", headers=h)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["calls"] == 1
    assert (await client.get("/v1/customers?q=ravi", headers=h)).json()["total"] == 1
    assert (await client.get("/v1/customers?q=5678", headers=h)).json()["total"] == 1
    assert (await client.get("/v1/customers?q=nobody", headers=h)).json()["total"] == 0

    memory = (await client.get(f"/v1/customers/{contact_id}", headers=h)).json()["memory"]
    guess = next(m for m in memory if m["key"] == "preferred_time")
    url = f"/v1/customers/{contact_id}/memory/{guess['id']}"
    resp = await client.patch(url, json={"value": "after 6 pm"}, headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"
    assert resp.json()["expires_at"] is None
    assert (await client.patch(url, json={"value": None}, headers=h)).status_code == 422
    assert (await client.delete(url, headers=h)).status_code == 204
    assert (await client.delete(url, headers=h)).status_code == 404

    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    sh = staff.headers(t["business"]["id"])
    assert (await client.post(f"/v1/customers/{contact_id}/forget", headers=sh)).status_code == 403

    resp = await client.post(f"/v1/customers/{contact_id}/forget", headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["calls_deleted"] == 1
    assert resp.json()["memory_deleted"] >= 2
    assert (await client.get(f"/v1/customers/{contact_id}", headers=h)).status_code == 404
    assert (await client.get(f"/v1/calls/{call_id}", headers=h)).status_code == 404
    async with admin_engine.connect() as conn:
        for table in ("contact", "call", "call_action", "memory_fact", "interaction_summary"):
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, table
        commitments = "SELECT count(*) FROM commitment WHERE contact_id IS NOT NULL OR call_id = :c"
        count = (await conn.execute(text(commitments), {"c": call_id})).scalar_one()
        assert count == 0


async def test_web_call_without_phone_has_no_customer(client: httpx.AsyncClient) -> None:
    configure_service()
    t = await make_tenant(client)
    resp = await start(client, t["employee"]["id"], phone=None, direction="web")
    assert resp.json()["caller"] is None
    call_id = resp.json()["id"]
    await end(client, call_id, t["employee"]["id"])
    detail = (await client.get(f"/v1/calls/{call_id}", headers=t["headers"])).json()
    assert detail["contact_id"] is None
    assert detail["result"] == "booked"
    assert (await client.get("/v1/customers", headers=t["headers"])).json()["total"] == 0


async def test_end_validation(client: httpx.AsyncClient) -> None:
    configure_service()
    t = await make_tenant(client)
    emp = t["employee"]["id"]
    call_id = (await start(client, emp)).json()["id"]
    resp = await end(client, call_id, emp, ended_at="2000-01-01T00:00:00+00:00")
    assert resp.status_code == 422
    resp = await end(client, call_id, emp, actions=[{"name": "Bad Name!"}])
    assert resp.status_code == 422
    resp = await end(client, call_id, emp, usage={"blob": "x" * 9_000})
    assert resp.status_code == 422
    assert (await end(client, str(uuid.uuid4()), emp)).status_code == 404


async def test_phone_call_end_is_billed_once_and_web_calls_are_free(
    client: httpx.AsyncClient,
) -> None:
    configure_service()
    t = await make_tenant(client)
    emp = t["employee"]["id"]

    async def used() -> int:
        resp = await client.get("/v1/billing/summary", headers=t["headers"])
        assert resp.status_code == 200, resp.text
        return int(resp.json()["month_usage_paise"])

    web = (await start(client, emp, phone=None, direction="web")).json()["id"]
    await end(client, web, emp)
    assert await used() == 0

    call_id = await booked_call(client, t)
    billed = await used()
    assert billed > 0  # ~3 connected minutes at the employee's voice tier
    replay = await end(client, call_id, emp)
    assert replay.json()["replayed"] is True
    assert await used() == billed
