"""AI team: templates, one-tap hire, team map, hand-off rules, follow-up tasks, staff ladder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models import HandoffRule
from mitra_core.models.enums import MemberRole
from mitra_core.team import ports
from mitra_core.team.handoff import rule_matches
from mitra_core.team.humans import callback_promise
from tests.helpers import add_member, bearer, new_actor
from tests.test_calls import (
    PHONE,
    TOKEN,
    booked_call,
    configure_service,
    end,
    make_tenant,
    start,
)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture WhatsApps (manager's sender is swapped out) and give contacts a number."""
    sent: list[dict[str, Any]] = []

    async def send(
        _s: Any, business_id: uuid.UUID, to: str, body: str, *, kind: str, **extra: Any
    ) -> str:
        sent.append({"to": to, "text": body, "kind": kind, **extra})
        return f"wa-{len(sent)}"

    async def phone(_s: Any, _contact: Any) -> str:
        return PHONE

    monkeypatch.setattr(ports, "send_whatsapp", send)
    monkeypatch.setattr(ports, "contact_phone", phone)
    return sent


async def hire(client: httpx.AsyncClient, headers: dict[str, str], template: str) -> Any:
    resp = await client.post("/v1/team/hire", json={"template_id": template}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_templates_and_one_tap_hire(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    t = await make_tenant(client)
    templates = (await client.get("/v1/team/templates", headers=t["headers"])).json()
    assert {x["id"] for x in templates} == {"real_estate", "clinic", "coaching"}
    assert next(x for x in templates if x["recommended"])["id"] == "clinic"

    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    denied = await client.post(
        "/v1/team/hire",
        json={"template_id": "clinic"},
        headers=staff.headers(t["business"]["id"]),
    )
    assert denied.status_code == 403

    data = await hire(client, t["headers"], "clinic")
    team = data["teams"][0]
    roles = [m["team_role"] for m in team["members"]]
    assert roles == ["receptionist", "reminder_caller", "follow_up_caller", "report_sender"]
    # The receptionist hired in onboarding joins the team instead of a duplicate.
    assert team["members"][0]["employee_id"] == t["employee"]["id"]
    assert [m["status"] for m in team["members"][1:]] == ["training"] * 3
    assert len(team["rules"]) == 5
    assert data["others"] == []

    again = await client.post("/v1/team/hire", json={"template_id": "clinic"}, headers=t["headers"])
    assert again.status_code == 409

    active = await client.post(f"/v1/team/{team['id']}/activate", headers=t["headers"])
    assert {m["status"] for m in active.json()["teams"][0]["members"]} == {"working"}

    # Another business sees none of it (RLS + explicit filters).
    other = await make_tenant(client, name="Other Clinic")
    assert (await client.get("/v1/team", headers=other["headers"])).json()["teams"] == []
    rule_id = team["rules"][0]["id"]
    resp = await client.delete(f"/v1/team/rules/{rule_id}", headers=other["headers"])
    assert resp.status_code == 404


async def test_rule_editor(client: httpx.AsyncClient) -> None:
    t = await make_tenant(client)
    members = (await hire(client, t["headers"], "real_estate"))["teams"][0]["members"]
    first, second = members[0]["employee_id"], members[1]["employee_id"]
    body = {
        "from_employee_id": first,
        "when_result": "interested",
        "to_employee_id": second,
        "task": "book_visit",
        "channel": "call",
        "delay_minutes": 5,
        "condition": {"field": "budget", "op": "present"},
    }
    resp = await client.post("/v1/team/rules", json=body, headers=t["headers"])
    assert resp.status_code == 201, resp.text
    rule = resp.json()
    assert rule["version"] == 1
    assert rule["condition"]["field"] == "budget"

    bad = await client.post(
        "/v1/team/rules", json=body | {"to_employee_id": None}, headers=t["headers"]
    )
    assert bad.status_code == 422
    brief = await client.post(
        "/v1/team/rules",
        json=body | {"to_employee_id": None, "task": "brief_staff", "channel": "whatsapp"},
        headers=t["headers"],
    )
    assert brief.status_code == 201
    stranger = await client.post(
        "/v1/team/rules", json=body | {"to_employee_id": str(uuid.uuid4())}, headers=t["headers"]
    )
    assert stranger.status_code == 422

    patched = await client.patch(
        f"/v1/team/rules/{rule['id']}",
        json={"delay_minutes": 30, "condition": None},
        headers=t["headers"],
    )
    assert patched.json()["version"] == 2
    assert patched.json()["condition"] == {}
    gone = await client.delete(f"/v1/team/rules/{rule['id']}", headers=t["headers"])
    assert gone.status_code == 204


def test_rule_matching() -> None:
    rule = HandoffRule(when_result="interested", condition={}, enabled=True)
    assert rule_matches(rule, "interested", {})
    assert not rule_matches(rule, "booked", {})
    rule.condition = {"field": "budget", "op": "present"}
    assert not rule_matches(rule, "interested", {"area": "Kondapur"})
    assert rule_matches(rule, "interested", {"budget": "60 lakh"})
    rule.condition = {"field": "area", "op": "contains", "value": "kondapur"}
    assert rule_matches(rule, "interested", {"area": "Near Kondapur X roads"})
    rule.enabled = False
    assert not rule_matches(rule, "interested", {"area": "Kondapur"})


async def test_booked_call_hands_off_with_shared_memory(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, outbox: list[dict[str, Any]]
) -> None:
    configure_service()
    t = await make_tenant(client)
    await hire(client, t["headers"], "clinic")
    resp = await client.post(
        "/v1/team/staff",
        json={"name": "Dr. Rao", "phone_e164": "+919800000001", "role_label": "Doctor"},
        headers=t["headers"],
    )
    assert resp.status_code == 201

    call_id = await booked_call(client, t)

    tasks = (await client.get("/v1/team/tasks", headers=t["headers"])).json()
    by_task = {x["task"]: x for x in tasks}
    remind = by_task["remind_appointment"]
    assert remind["status"] == "queued"
    assert remind["customer_name"] == "Ravi Kumar"
    assert remind["source_call_id"] == call_id
    assert by_task["brief_staff"]["status"] == "sent"
    brief = next(m for m in outbox if m["kind"] == "team_handoff")
    assert brief["to"] == "+919800000001"
    assert "Ravi Kumar" in brief["text"]
    assert "Appointment" in brief["text"]

    async with admin_engine.connect() as conn:
        job = (
            await conn.execute(
                text("SELECT source, dedupe_key, variables FROM outbound_job WHERE source='team'")
            )
        ).one()
        packet = (
            await conn.execute(
                text("SELECT context FROM follow_up_task WHERE task = 'remind_appointment'")
            )
        ).scalar_one()
    assert job.dedupe_key == f"task:{remind['id']}"
    assert job.variables["customer_name"] == "Ravi Kumar"
    assert packet["memory"]
    assert packet["promises"]
    assert packet["fields"]["appointment"].startswith("Wed 21 Oct")

    # Map counts: the reminder caller received one hand-off.
    data = (await client.get("/v1/team", headers=t["headers"])).json()
    reminder = data["teams"][0]["members"][1]
    assert reminder["received_7d"] == 1
    assert reminder["waiting"] == 1
    assert sum(r["handoffs_7d"] for r in data["teams"][0]["rules"]) == 2


async def test_handoff_without_a_number_is_kept_visible(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)
    await hire(client, t["headers"], "clinic")
    resp = await start(client, t["employee"]["id"])
    assert resp.status_code == 201, resp.text
    async with admin_engine.begin() as conn:  # e.g. erased, or a pre-encryption contact
        await conn.execute(text("UPDATE contact SET phone_enc = NULL"))
    resp = await end(client, resp.json()["id"], t["employee"]["id"])
    assert resp.status_code == 200, resp.text
    tasks = (await client.get("/v1/team/tasks", headers=t["headers"])).json()
    remind = next(x for x in tasks if x["task"] == "remind_appointment")
    assert remind["status"] == "no_phone"


async def test_escalation_goes_to_owners_once(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, outbox: list[dict[str, Any]]
) -> None:
    """TEAM-05 via the manager's owner alerts: every owner/manager, one message per call."""
    configure_service()
    t = await make_tenant(client)
    manager = await add_member(admin_engine, t["business"]["id"], MemberRole.MANAGER, "Asha")
    from tests.test_calls import end, start

    async def escalate(urgency: str) -> str:
        call_id: str = (await start(client, t["employee"]["id"])).json()["id"]
        actions = [
            {
                "name": "alert_staff",
                "args": {"reason": "chest pain", "urgency": urgency},
                "result": {"status": "alerted"},
            }
        ]
        await end(client, call_id, t["employee"]["id"], actions=actions, fields={"name": "Ravi"})
        return call_id

    async def bodies(call_id: str) -> list[tuple[str, str]]:
        async with admin_engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT phone_last4, body FROM wa_message WHERE direction = 'out' "
                    "AND (dedupe_key LIKE :k OR ref->>'call_id' = :c) ORDER BY created_at"
                ),
                {"k": f"%call:{call_id}", "c": call_id},
            )
            return [(r.phone_last4, r.body) for r in rows]

    normal = await bodies(await escalate("normal"))
    assert {last4 for last4, _ in normal} == {t["owner"].phone[-4:], manager.phone[-4:]}
    assert all("needs a person: chest pain" in body for _, body in normal)

    urgent = await bodies(await escalate("emergency"))
    owner_msgs = [body for last4, body in urgent if last4 == t["owner"].phone[-4:]]
    assert len(owner_msgs) == 1  # the manager's call alert and our escalation are one message
    assert "urgent" in owner_msgs[0].lower()
    assert "Knows: name: Ravi" in owner_msgs[0]  # full picture: what the caller told us
    assert not [m for m in outbox if m["kind"] == "team_escalation"]  # no ladder fallback


async def test_escalation_falls_back_to_ladder_without_owners(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, outbox: list[dict[str, Any]]
) -> None:
    configure_service()
    t = await make_tenant(client)
    await client.post(
        "/v1/team/staff",
        json={"name": "Ram", "phone_e164": "+919800000001", "ladder_position": 1},
        headers=t["headers"],
    )
    async with admin_engine.begin() as conn:  # nobody left to alert in the app
        await conn.execute(
            text("DELETE FROM membership WHERE business_id = :b"), {"b": t["business"]["id"]}
        )
    from mitra_core.db import tenant_session
    from mitra_core.models import FollowUpTask
    from mitra_core.team.dispatch import dispatch_task
    from mitra_core.tenancy import TenantContext

    business_id = uuid.UUID(t["business"]["id"])
    async with tenant_session(TenantContext(business_id=business_id)) as session:
        task = FollowUpTask(
            business_id=business_id,
            kind="escalation",
            task="brief_staff",
            channel="whatsapp",
            due_at=datetime.now(UTC),
            status="pending",
            context={"reason": "wants the doctor", "urgency": "urgent"},
        )
        session.add(task)
        await session.flush()
        await dispatch_task(session, task)
        assert task.status == "sent"
        assert task.outcome["fallback"] == "ladder"
    msgs = [m for m in outbox if m["kind"] == "team_escalation"]
    assert [m["to"] for m in msgs] == ["+919800000001"]
    assert msgs[0]["text"].startswith("URGENT:")


async def test_staff_ladder_and_handoff_card(
    client: httpx.AsyncClient, outbox: list[dict[str, Any]]
) -> None:
    configure_service()
    t = await make_tenant(client)
    for name, phone, pos in (("Sita", "+919800000002", 2), ("Ram", "+919800000001", 1)):
        resp = await client.post(
            "/v1/team/staff",
            json={"name": name, "phone_e164": phone, "ladder_position": pos, "ring_timeout_s": 15},
            headers=t["headers"],
        )
        assert resp.status_code == 201, resp.text
    bad = await client.post(
        "/v1/team/staff", json={"name": "X", "phone_e164": "98000"}, headers=t["headers"]
    )
    assert bad.status_code == 422

    emp = t["employee"]["id"]
    ladder = await client.get(f"/internal/v1/team/ladder?employee_id={emp}", headers=bearer(TOKEN))
    assert ladder.status_code == 200, ladder.text
    steps = ladder.json()["steps"]
    assert [s["name"] for s in steps[:2]] == ["Ram", "Sita"]
    assert steps[-1]["is_owner"]
    assert steps[-1]["phone_e164"] == t["owner"].phone
    assert ladder.json()["callback_day"] in {"today", "tomorrow"}

    card = await client.post(
        "/internal/v1/team/handoff-cards",
        json={
            "employee_id": emp,
            "call_id": str(uuid.uuid4()),
            "caller_phone": PHONE,
            "reason": "wants to talk to the doctor",
            "message": "Please call about my mother's report",
            "attempts": [{"name": "Ram", "outcome": "no_answer"}],
        },
        headers=bearer(TOKEN),
    )
    assert card.status_code == 201, card.text
    assert [m["to"] for m in outbox if m["kind"] == "handoff_card"][:2] == [
        "+919800000001",
        "+919800000002",
    ]
    cards = (await client.get("/v1/team/handoff-cards", headers=t["headers"])).json()
    assert cards[0]["caller_last4"] == PHONE[-4:]
    assert "mother's report" in cards[0]["message"]
    done = await client.post(f"/v1/team/handoff-cards/{cards[0]['id']}/done", headers=t["headers"])
    assert done.json()["status"] == "done"
    assert (await client.get("/v1/team/handoff-cards", headers=t["headers"])).json() == []

    other = new_actor()
    assert (
        await client.get("/v1/team/staff", headers=other.headers(t["business"]["id"]))
    ).status_code == 403


def test_callback_promise() -> None:
    tz = "Asia/Kolkata"
    # 11:00 IST -> by 13:00 today; 18:30 IST -> tomorrow 10:00; 07:00 IST -> 12:00 today.
    _, local, day = callback_promise(datetime(2026, 11, 2, 5, 30, tzinfo=UTC), tz)
    assert (local, day) == ("13:00", "today")
    _, local, day = callback_promise(datetime(2026, 11, 2, 13, 0, tzinfo=UTC), tz)
    assert (local, day) == ("10:00", "tomorrow")
    _, local, day = callback_promise(datetime(2026, 11, 2, 1, 30, tzinfo=UTC), tz)
    assert (local, day) == ("12:00", "today")


async def test_ring_order_is_unique_and_shown_as_it_rings(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)

    async def add(name: str, phone: str, pos: int | None, **extra: Any) -> httpx.Response:
        body = {"name": name, "phone_e164": phone, "ladder_position": pos, **extra}
        return await client.post("/v1/team/staff", json=body, headers=t["headers"])

    assert (await add("Owner Lata", "+919800000009", 1, is_owner=True)).status_code == 201
    assert (await add("Sita", "+919800000002", 2)).status_code == 201
    taken = await add("Ravi", "+919800000003", 2)
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "position_taken"
    assert (await add("Ram", "+919800000001", 1)).status_code == 409  # the owner holds #1
    assert (await add("Ram", "+919800000001", 3)).status_code == 201
    assert (await add("Desk", "+919800000004", None)).status_code == 201  # briefs only

    staff = (await client.get("/v1/team/staff", headers=t["headers"])).json()
    # Staff by position, the owner last whatever number they picked, briefs-only unnumbered.
    assert [(s["name"], s["ring_order"]) for s in staff] == [
        ("Sita", 1),
        ("Ram", 2),
        ("Owner Lata", 3),
        ("Desk", None),
    ]
    ram = next(s for s in staff if s["name"] == "Ram")
    moved = await client.patch(
        f"/v1/team/staff/{ram['id']}", json={"ladder_position": 2}, headers=t["headers"]
    )
    assert moved.status_code == 409

    # Rows from before the check may share a position: who was added first rings first, and
    # the internal ladder (what actually rings) agrees with the list the owner sees.
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE staff_member SET ladder_position = 2 WHERE name = 'Ram'"))
    staff = (await client.get("/v1/team/staff", headers=t["headers"])).json()
    shown = [s["name"] for s in staff if s["ring_order"]]
    assert shown == ["Sita", "Ram", "Owner Lata"]
    ladder = await client.get(
        f"/internal/v1/team/ladder?employee_id={t['employee']['id']}", headers=bearer(TOKEN)
    )
    assert [s["name"] for s in ladder.json()["steps"]] == shown
