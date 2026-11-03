"""AI Manager: Ask Mitra answers from data (te/hi/en), confirm cards for commands, coaching,
daily report, instant alerts, WhatsApp conversation, and the LLM planner interface."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.db import tenant_session
from mitra_core.manager import commands
from mitra_core.manager.alerts import alerts_for_call
from mitra_core.manager.intents import detect_language, parse
from mitra_core.manager.planner import LlmPlanner
from mitra_core.manager.report import tick
from mitra_core.models import Call
from mitra_core.models.enums import MemberRole
from mitra_core.tenancy import TenantContext
from tests.helpers import FakeClock, add_member
from tests.manager_helpers import add_call, add_contact, ask, make_business, wa_messages

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)  # 14:30 IST, the FakeClock default


async def _seed_week(admin: AsyncEngine, biz: dict[str, Any]) -> dict[str, Any]:
    emp = biz["employee"]["id"]
    ramesh = await add_contact(admin, biz["id"], "Ramesh", "+919800000011")
    lakshmi = await add_contact(admin, biz["id"], "Lakshmi", "+919800000012")
    await add_call(
        admin, biz["id"], started_at=NOW - timedelta(hours=1), result="booked", employee_id=emp
    )
    await add_call(
        admin, biz["id"], started_at=NOW - timedelta(hours=2), result="booked", employee_id=emp
    )
    await add_call(
        admin,
        biz["id"],
        started_at=NOW - timedelta(days=1),
        result="interested",
        employee_id=emp,
        contact_id=ramesh,
        summary="Asked about MRI price",
        transcript_text="How much is an MRI scan?",
        alerts=[{"kind": "hot_lead", "message": "Hot lead: Ramesh is interested"}],
    )
    await add_call(
        admin,
        biz["id"],
        started_at=NOW - timedelta(days=3),
        result="missed",
        contact_id=lakshmi,
        unknown=["Is there parking?"],
    )
    await add_call(admin, biz["id"], started_at=NOW - timedelta(days=20), result="booked")
    return {"ramesh": ramesh, "lakshmi": lakshmi}


async def test_week_summary_uses_real_numbers(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    await _seed_week(admin_engine, biz)
    reply = await ask(client, biz["owner"], biz["id"], "What happened this week?")
    assert reply["text"].splitlines()[0] == "This week: 4 calls"
    assert "2 booked · 1 interested · 1 missed" in reply["text"]
    assert "1 questions we could not answer" in reply["text"]


async def test_answers_in_owner_language(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    await _seed_week(admin_engine, biz)
    hi = await ask(client, biz["owner"], biz["id"], "इस हफ्ते क्या हुआ?")
    assert hi["text"].startswith("इस हफ्ते: 4 कॉल")
    te = await ask(client, biz["owner"], biz["id"], "ఈ వారం ఏమైంది?")
    assert te["text"].startswith("ఈ వారం: 4 కాల్స్")
    tenglish = await ask(client, biz["owner"], biz["id"], "ninna enni calls vachayi?")
    assert tenglish["text"].startswith("నిన్న: 1 కాల్స్")


async def test_attention_search_and_empty_states(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    empty = await ask(client, biz["owner"], biz["id"], "What needs my attention today?")
    assert empty["text"] == "Nothing needs you right now."
    none = await ask(client, biz["owner"], biz["id"], "What happened this week?")
    assert none["text"] == "This week: no calls yet."
    await _seed_week(admin_engine, biz)
    att = await ask(client, biz["owner"], biz["id"], "What needs my attention today?")
    assert "Hot lead: Ramesh is interested" in att["text"]
    found = await ask(client, biz["owner"], biz["id"], "Who called about MRI?")
    assert found["text"].startswith("1 calls about “MRI”")
    assert found["card"]["links"][0]["href"].startswith("/calls/")
    missing = await ask(client, biz["owner"], biz["id"], "Who called about dental implants?")
    assert missing["text"].startswith("No calls about")


async def test_thread_is_private_per_user_and_business(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    await ask(client, biz["owner"], biz["id"], "help")
    other = await make_business(client, "Other")
    res = await client.get("/v1/manager/thread", headers=other["headers"])
    assert res.json()["items"] == []
    manager = await add_member(admin_engine, biz["id"], MemberRole.MANAGER, "Meena")
    res = await client.get("/v1/manager/thread", headers=manager.headers(biz["id"]))
    assert res.json()["items"] == []
    res = await client.get("/v1/manager/thread", headers=biz["headers"])
    assert [m["role"] for m in res.json()["items"]] == ["owner", "mitra"]


async def test_pause_needs_confirmation_then_applies(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    emp_id = biz["employee"]["id"]
    reply = await ask(client, biz["owner"], biz["id"], "Pause Priya")
    card = reply["card"]
    assert card["type"] == "confirm"
    assert card["status"] == "pending"
    emp = (await client.get(f"/v1/employees/{emp_id}", headers=biz["headers"])).json()
    assert emp["status"] != "paused"  # nothing happens before the confirm tap
    res = await client.post(
        f"/v1/approvals/{card['approval_id']}/decide",
        json={"action": "approve", "version": card["version"]},
        headers=biz["headers"],
    )
    assert res.status_code == 200, res.text
    emp = (await client.get(f"/v1/employees/{emp_id}", headers=biz["headers"])).json()
    assert emp["status"] == "paused"
    thread = (await client.get("/v1/manager/thread", headers=biz["headers"])).json()["items"]
    assert thread[-1]["card"]["status"] == "approved"


async def test_staff_cannot_command(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    staff = await add_member(admin_engine, biz["id"], MemberRole.STAFF, "Ravi")
    reply = await ask(client, staff, biz["id"], "Pause Priya")
    assert reply["card"] is None
    assert reply["text"].startswith("Only the owner or a manager")


async def test_coaching_becomes_behaviour_after_confirm(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    biz = await make_business(client)
    reply = await ask(client, biz["owner"], biz["id"], "Next time offer Saturday first")
    assert (
        reply["text"] == "I'll change how Priya behaves: “Next time offer Saturday first”. Confirm?"
    )
    card = reply["card"]
    assert card["kind"] == "behaviour_update"
    res = await client.post(
        f"/v1/approvals/{card['approval_id']}/decide",
        json={"action": "approve", "version": card["version"]},
        headers=biz["headers"],
    )
    assert res.status_code == 200
    emp = (
        await client.get(f"/v1/employees/{biz['employee']['id']}", headers=biz["headers"])
    ).json()
    assert "Next time offer Saturday first" in emp["behaviour"]["ask_for"]


async def test_callback_goes_to_dialer_queue(
    client: httpx.AsyncClient,
    admin_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    biz = await make_business(client)
    await _seed_week(admin_engine, biz)
    reply = await ask(client, biz["owner"], biz["id"], "Call Ramesh back at 5")
    assert reply["text"] == "Priya will call Ramesh back at 05:00 PM, Sun 18 Oct. Confirm?"
    card = reply["card"]
    detail = (
        await client.get(f"/v1/approvals/{card['approval_id']}", headers=biz["headers"])
    ).json()
    assert detail["approval"]["payload"]["not_before"] == "2026-10-18T17:00:00+05:30"

    async def fake_phone(session: Any, contact: Any) -> str:
        return "+919800000011"

    monkeypatch.setattr(commands, "_phone_for", fake_phone)
    res = await client.post(
        f"/v1/approvals/{card['approval_id']}/decide",
        json={"action": "approve", "version": card["version"]},
        headers=biz["headers"],
    )
    assert res.status_code == 200
    assert res.json()["apply_error"] is None
    async with admin_engine.connect() as conn:
        rows = (await conn.execute(text("SELECT source, phone_last4 FROM outbound_job"))).all()
    assert [(r.source, r.phone_last4) for r in rows] == [("manager", "0011")]


async def test_callback_without_number_reports_apply_error(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    await _seed_week(admin_engine, biz)
    reply = await ask(client, biz["owner"], biz["id"], "call back Ramesh")
    res = await client.post(
        f"/v1/approvals/{reply['card']['approval_id']}/decide",
        json={"action": "approve", "version": 1},
        headers=biz["headers"],
    )
    assert res.json()["status"] == "approved"
    assert "no dialable number" in res.json()["apply_error"]


async def test_call_list_counts_matching_contacts(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    await _seed_week(admin_engine, biz)
    reply = await ask(
        client, biz["owner"], biz["id"], "Call all leads from yesterday who said maybe"
    )
    assert reply["text"].startswith("Call 1 people (Yesterday, interested, call back)?")
    nobody = await ask(
        client,
        biz["owner"],
        biz["id"],
        "Call everyone who was missed this week but interested today",
    )
    assert nobody["card"] is not None or nobody["text"].startswith("Nobody")


async def test_daily_report_once_per_day_after_time(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    await _seed_week(admin_engine, biz)
    early = datetime(2026, 10, 18, 2, 0, tzinfo=UTC)  # 07:30 IST, before the 08:00 default
    assert (await tick(early)).reports == 0
    later = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)  # 08:30 IST
    assert (await tick(later)).reports >= 1
    assert (await tick(later + timedelta(hours=1))).reports == 0
    msgs = [m for m in await wa_messages(admin_engine, biz["id"]) if m["purpose"] == "report"]
    assert len(msgs) == 1
    # The owner has not written in 24 hours: the approved daily_report template goes out.
    assert msgs[0]["kind"] == "template"
    assert msgs[0]["body"].startswith(
        "Good morning! Yesterday at Sunrise Clinic: 1 calls, 0 booked"
    )


async def test_tick_expires_overdue_approvals(client: httpx.AsyncClient) -> None:
    from mitra_core.approvals import request_approval

    biz = await make_business(client)
    bid = uuid.UUID(biz["id"])
    async with tenant_session(TenantContext(business_id=bid)) as session:
        await request_approval(
            session,
            bid,
            kind="discount",
            summary="5% off",
            payload={},
            requested_by="call:x",
            now=NOW,
        )
        await session.commit()
    assert (await tick(NOW + timedelta(hours=3))).expired == 1


async def test_alerts_for_call_dedupes(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    call_id = await add_call(
        admin_engine,
        biz["id"],
        started_at=NOW,
        result="interested",
        alerts=[
            {"kind": "hot_lead", "message": "Hot lead: Ravi is interested"},
            {"kind": "unknown_question", "message": "x"},
        ],
    )
    bid = uuid.UUID(biz["id"])
    for _ in range(2):
        async with tenant_session(TenantContext(business_id=bid)) as session:
            call = await session.get(Call, call_id)
            assert call is not None
            await alerts_for_call(session, call)
            await session.commit()
    alerts = [m for m in await wa_messages(admin_engine, biz["id"]) if m["purpose"] == "alert"]
    assert len(alerts) == 1
    assert alerts[0]["body"] == (
        "Alert: Hot lead at Sunrise Clinic. Hot lead: Ravi is interested Open Mitra for details."
    )


async def test_whatsapp_conversation_and_confirm_button(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    await _seed_week(admin_engine, biz)
    res = await client.post(
        "/v1/manager/whatsapp-sim/inbound",
        json={"kind": "text", "text": "what happened today?"},
        headers=biz["headers"],
    )
    assert res.json()["outcome"] == "answered"
    res = await client.post(
        "/v1/manager/whatsapp-sim/inbound",
        json={"kind": "voice", "text": "Pause Priya"},  # simulated voice-note transcript
        headers=biz["headers"],
    )
    msgs = (await client.get("/v1/manager/whatsapp-sim/messages", headers=biz["headers"])).json()[
        "items"
    ]
    replies = [m for m in msgs if m["direction"] == "out"]
    assert replies[0]["body"].startswith("Today: 2 calls")
    assert "Open in app: http" in replies[0]["body"]
    card = replies[1]
    assert [b["title"] for b in card["buttons"]] == ["Confirm", "Cancel"]
    res = await client.post(
        "/v1/manager/whatsapp-sim/inbound",
        json={
            "kind": "button_reply",
            "button_id": card["buttons"][0]["id"],
            "context_id": card["provider_message_id"],
        },
        headers=biz["headers"],
    )
    assert res.json()["outcome"] == "decided"
    emp = (
        await client.get(f"/v1/employees/{biz['employee']['id']}", headers=biz["headers"])
    ).json()
    assert emp["status"] == "paused"


async def test_settings_roundtrip(client: httpx.AsyncClient, admin_engine: AsyncEngine) -> None:
    biz = await make_business(client)
    res = await client.get("/v1/manager/settings", headers=biz["headers"])
    assert res.status_code == 200
    body = res.json()
    assert body["report_time"] == "08:00:00"
    assert body["report_enabled"] is True
    assert [p["role"] for p in body["people"]] == ["owner"]
    res = await client.patch(
        "/v1/manager/settings",
        json={"report_time": "07:30", "language": "te", "report_user_ids": [str(uuid.uuid4())]},
        headers=biz["headers"],
    )
    assert res.status_code == 422
    res = await client.patch(
        "/v1/manager/settings",
        json={"report_time": "07:30", "language": "te"},
        headers=biz["headers"],
    )
    assert res.json()["language"] == "te"
    assert res.json()["report_time"] == "07:30:00"
    staff = await add_member(admin_engine, biz["id"], MemberRole.STAFF, "Ravi")
    res = await client.patch(
        "/v1/manager/settings", json={"language": "hi"}, headers=staff.headers(biz["id"])
    )
    assert res.status_code == 403


def test_intent_rules() -> None:
    assert parse("What needs my attention today?").name == "attention"
    assert parse("How many site visits tomorrow?").day_offset == 1
    assert parse("Who called about MRI?").query == "MRI"
    assert parse("call Ramesh back at 5:30 pm").when == "5:30 pm"
    assert parse("Tell Priya to always greet in Telugu").query == "Priya"
    assert detect_language("repu enni bookings undi") == "te"
    assert detect_language("aaj kitne calls aaye") == "hi"
    when = commands.parse_when("5", datetime(2026, 10, 18, 18, 0, tzinfo=UTC))
    assert (when.day, when.hour) == (19, 17)


async def test_llm_planner_maps_and_falls_back() -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"intent": "bookings", "day_offset": 1})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    planner = LlmPlanner("http://llm", "k", "m", transport=httpx.MockTransport(ok))
    intent = await planner.plan("రేపు ఎన్ని సైట్ విజిట్స్?")
    assert (intent.name, intent.day_offset, intent.lang) == ("bookings", 1, "te")

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    planner = LlmPlanner("http://llm", "k", "m", transport=httpx.MockTransport(broken))
    assert (await planner.plan("Pause Priya")).name == "pause"
