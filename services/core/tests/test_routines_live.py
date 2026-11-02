"""Routines (builder, library, dry run, approval, history, events, scheduler) and live calls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from mitra_core.pii import hash_phone
from mitra_core.team import scheduler
from mitra_core.team.routines.spec import RoutineSpec, next_run, sentence
from tests.helpers import FakeClock, add_member, bearer
from tests.test_calls import PHONE, TOKEN, booked_call, configure_service, make_tenant, start
from tests.test_team import outbox  # noqa: F401  (fixture)

# 2026-10-20 10:30 IST: the booked appointment (Wed 21 Oct, 6:15 pm) is "tomorrow".
TUESDAY_MORNING = datetime(2026, 10, 20, 5, 0, tzinfo=UTC)


def schedule_spec(employee_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "trigger": {"type": "schedule", "days": ["sun", "mon", "tue"], "time": "18:00"},
        "audience": "tomorrows_appointments",
        "action": {"verb": "call", "employee_id": employee_id, "goal": "confirm"},
        **extra,
    }


def test_spec_next_run_and_sentence() -> None:
    spec = RoutineSpec.model_validate(schedule_spec("6f1d8a52-6a4e-4c2b-9b0a-111111111111"))
    assert spec.trigger.days == ["mon", "tue", "sun"]  # type: ignore[union-attr]
    # Tuesday 10:30 IST -> Tuesday 18:00 IST; Tuesday 19:00 IST -> Sunday 18:00 IST.
    assert next_run(spec, TUESDAY_MORNING, "Asia/Kolkata") == datetime(
        2026, 10, 20, 12, 30, tzinfo=UTC
    )
    later = datetime(2026, 10, 20, 13, 30, tzinfo=UTC)
    assert next_run(spec, later, "Asia/Kolkata") == datetime(2026, 10, 25, 12, 30, tzinfo=UTC)
    assert sentence(spec, "Lakshmi") == (
        "Every Mon, Tue, Sun at 18:00, Lakshmi calls tomorrow's appointments to confirm."
    )


async def test_builder_validation_and_library(client: httpx.AsyncClient) -> None:
    t = await make_tenant(client)
    emp = t["employee"]["id"]
    no_audience = schedule_spec(emp)
    no_audience.pop("audience")
    resp = await client.post(
        "/v1/routines", json={"name": "x", "spec": no_audience}, headers=t["headers"]
    )
    assert resp.status_code == 422
    bad_time = schedule_spec(emp) | {
        "trigger": {"type": "schedule", "days": ["mon"], "time": "25:00"}
    }
    resp = await client.post(
        "/v1/routines", json={"name": "x", "spec": bad_time}, headers=t["headers"]
    )
    assert resp.status_code == 422

    lead_call = {
        "trigger": {"type": "event", "event": "lead.created"},
        "action": {"verb": "call", "employee_id": emp, "goal": "follow_up"},
    }
    resp = await client.post(
        "/v1/routines", json={"name": "x", "spec": lead_call}, headers=t["headers"]
    )
    assert resp.status_code == 422
    lead_wa = lead_call | {"action": {"verb": "whatsapp", "employee_id": emp, "goal": "confirm"}}
    resp = await client.post(
        "/v1/routines", json={"name": "Welcome", "spec": lead_wa}, headers=t["headers"]
    )
    assert resp.status_code == 201

    library = (await client.get("/v1/routines/library", headers=t["headers"])).json()
    ids = {r["id"] for r in library}
    assert {"confirm_tomorrow", "missed_call_rescue"} <= ids
    assert "visit_reminder" not in ids
    assert all(r["employee_id"] == emp for r in library)
    resp = await client.post(
        "/v1/routines/from-library",
        json={"library_id": "confirm_tomorrow", "enabled": True},
        headers=t["headers"],
    )
    assert resp.status_code == 201, resp.text
    routine = resp.json()
    assert routine["sentence"].startswith("Every day at 18:00, Priya calls tomorrow's")
    assert routine["next_run_at"] is not None

    off = await client.patch(
        f"/v1/routines/{routine['id']}", json={"enabled": False}, headers=t["headers"]
    )
    assert off.json()["next_run_at"] is None


async def test_dry_run_approval_run_and_history(
    client: httpx.AsyncClient,
    admin_engine: AsyncEngine,
    clock: FakeClock,
    outbox: list[dict[str, Any]],  # noqa: F811
) -> None:
    configure_service()
    t = await make_tenant(client)
    await booked_call(client, t)
    await booked_call(client, t, phone="+919811111111")
    async with admin_engine.begin() as conn:  # the second customer said "don't call me"
        await conn.execute(
            text("INSERT INTO opt_out (business_id, phone_hash, source) VALUES (:b, :h, 'voice')"),
            {"b": t["business"]["id"], "h": hash_phone("+919811111111")},
        )
    clock.now = TUESDAY_MORNING
    emp = t["employee"]["id"]
    spec = schedule_spec(emp, approval_over=0)

    dry = await client.post("/v1/routines/dry-run", json={"spec": spec}, headers=t["headers"])
    assert dry.status_code == 200, dry.text
    body = dry.json()
    assert [p["name"] for p in body["would_contact"]] == ["Ravi Kumar"]
    assert [p["skip"] for p in body["skipped"]] == ["opted_out"]
    assert "phone" not in body["would_contact"][0]
    assert body["needs_approval"] is True

    routine = (
        await client.post(
            "/v1/routines", json={"name": "Confirm", "spec": spec}, headers=t["headers"]
        )
    ).json()
    run = (await client.post(f"/v1/routines/{routine['id']}/run", headers=t["headers"])).json()
    assert run["status"] == "awaiting_approval"
    assert run["audience_count"] == 2
    assert run["skipped"] == {"opted_out": 1}

    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    denied = await client.post(
        f"/v1/routines/runs/{run['id']}/decision",
        json={"approved": True},
        headers=staff.headers(t["business"]["id"]),
    )
    assert denied.status_code == 403
    decided = await client.post(
        f"/v1/routines/runs/{run['id']}/decision", json={"approved": True}, headers=t["headers"]
    )
    assert decided.json()["status"] == "done"
    assert decided.json()["contacted_count"] == 1
    twice = await client.post(
        f"/v1/routines/runs/{run['id']}/decision", json={"approved": True}, headers=t["headers"]
    )
    assert twice.status_code == 409

    history = (await client.get(f"/v1/routines/{routine['id']}/runs", headers=t["headers"])).json()
    statuses = {c["last4"]: c["status"] for c in history[0]["contacts"]}
    assert statuses == {PHONE[-4:]: "queued", "1111": "opted_out"}  # job waits in the dialer


async def test_scheduler_runs_due_routines(
    client: httpx.AsyncClient,
    admin_engine: AsyncEngine,
    clock: FakeClock,
    outbox: list[dict[str, Any]],  # noqa: F811
) -> None:
    configure_service()
    t = await make_tenant(client)
    await booked_call(client, t)
    clock.now = TUESDAY_MORNING
    routine = (
        await client.post(
            "/v1/routines",
            json={"name": "Confirm", "spec": schedule_spec(t["employee"]["id"]), "enabled": True},
            headers=t["headers"],
        )
    ).json()
    due = datetime.fromisoformat(routine["next_run_at"])
    assert await scheduler.tick(due - timedelta(minutes=1)) == scheduler.TickResult()
    result = await scheduler.tick(due + timedelta(seconds=5))
    assert result.routines == 1
    assert result.failed == 0
    assert (await scheduler.tick(due + timedelta(seconds=6))).routines == 0  # moved forward

    runs = (await client.get(f"/v1/routines/{routine['id']}/runs", headers=t["headers"])).json()
    assert runs[0]["trigger"] == "schedule"
    assert runs[0]["contacted_count"] == 1
    listed = (await client.get("/v1/routines", headers=t["headers"])).json()[0]
    assert datetime.fromisoformat(listed["next_run_at"]) > due

    tick = await client.post("/internal/v1/team/tick", headers=bearer(TOKEN))
    assert tick.status_code == 200


async def test_event_routine_for_missed_call(
    client: httpx.AsyncClient,
    outbox: list[dict[str, Any]],  # noqa: F811
) -> None:
    configure_service()
    t = await make_tenant(client)
    await client.post(
        "/v1/routines/from-library",
        json={"library_id": "missed_call_rescue", "enabled": True},
        headers=t["headers"],
    )
    await booked_call(client, t)
    customer = (await client.get("/v1/customers", headers=t["headers"])).json()["items"][0]
    runs = await client.post(
        "/v1/routines/events",
        json={"event": "call.missed", "contact_id": customer["id"]},
        headers=t["headers"],
    )
    assert runs.status_code == 200, runs.text
    assert len(runs.json()) == 1
    assert runs.json()[0]["trigger"] == "event"
    assert runs.json()[0]["contacted_count"] == 1
    routine_id = runs.json()[0]["routine_id"]
    manual = await client.post(f"/v1/routines/{routine_id}/run", headers=t["headers"])
    assert manual.status_code == 422


async def test_live_view_whisper_and_takeover(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)
    emp = t["employee"]["id"]
    call_id = (await start(client, emp, started_at=datetime.now(UTC))).json()["id"]

    async def turn(role: str, said: str) -> list[dict[str, Any]]:
        resp = await client.post(
            f"/internal/v1/team/live/{call_id}/turns",
            json={"employee_id": emp, "role": role, "text": said},
            headers=bearer(TOKEN),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["instructions"]  # type: ignore[no-any-return]

    assert await turn("assistant", "Namaskaram, Sunrise Clinic nunchi Priya, AI assistant.") == []
    assert await turn("user", "Fees entha?") == []

    live = (await client.get("/v1/live-calls", headers=t["headers"])).json()
    assert [c["id"] for c in live] == [call_id]
    detail = (await client.get(f"/v1/live-calls/{call_id}?after=1", headers=t["headers"])).json()
    assert [x["text"] for x in detail["turns"]] == ["Fees entha?"]

    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    assert (
        await client.get("/v1/live-calls", headers=staff.headers(t["business"]["id"]))
    ).status_code == 403

    resp = await client.post(
        f"/v1/live-calls/{call_id}/whisper",
        json={"text": "Offer the Saturday 10 am slot first"},
        headers=t["headers"],
    )
    assert resp.status_code == 202
    got = await turn("assistant", "Fee ₹500 andi.")
    assert [(i["kind"], i["text"]) for i in got] == [
        ("whisper", "Offer the Saturday 10 am slot first")
    ]
    assert await turn("user", "ok") == []  # delivered once

    taken = await client.post(f"/v1/live-calls/{call_id}/takeover", headers=t["headers"])
    assert taken.json()["to_last4"] == t["owner"].phone[-4:]
    polled = await client.get(
        f"/internal/v1/team/live/{call_id}/instructions?employee_id={emp}", headers=bearer(TOKEN)
    )
    assert polled.json()["instructions"][0]["phone_e164"] == t["owner"].phone

    async with admin_engine.connect() as conn:
        kinds = (
            (
                await conn.execute(
                    text(
                        "SELECT kind FROM supervisor_action WHERE call_id = :c ORDER BY created_at"
                    ),
                    {"c": call_id},
                )
            )
            .scalars()
            .all()
        )
    assert kinds == ["listen", "whisper", "takeover"]

    from tests.test_calls import end

    await end(client, call_id, emp)
    assert (await client.get("/v1/live-calls", headers=t["headers"])).json() == []
    late = await client.post(
        f"/v1/live-calls/{call_id}/whisper", json={"text": "hi"}, headers=t["headers"]
    )
    assert late.status_code == 409
    assert PHONE  # the caller's number never appears in live payloads
    assert PHONE not in str(detail)


async def test_large_run_waits_for_whatsapp_approval(
    client: httpx.AsyncClient,
    clock: FakeClock,
    outbox: list[dict[str, Any]],  # noqa: F811
) -> None:
    import uuid

    from mitra_core.approvals import decide
    from mitra_core.db import tenant_session
    from mitra_core.models import Approval, RoutineRun
    from mitra_core.tenancy import TenantContext

    configure_service()
    t = await make_tenant(client)
    await booked_call(client, t)
    clock.now = TUESDAY_MORNING
    spec = schedule_spec(t["employee"]["id"], approval_over=0)
    routine = (
        await client.post(
            "/v1/routines", json={"name": "Confirm", "spec": spec}, headers=t["headers"]
        )
    ).json()
    run = (await client.post(f"/v1/routines/{routine['id']}/run", headers=t["headers"])).json()
    assert run["status"] == "awaiting_approval"

    business_id = uuid.UUID(t["business"]["id"])
    async with tenant_session(TenantContext(business_id=business_id)) as session:
        stored = await session.get(RoutineRun, uuid.UUID(run["id"]))
        assert stored is not None
        assert stored.approval_ref is not None
        approval = await session.get(Approval, uuid.UUID(stored.approval_ref))
        assert approval is not None
        assert approval.kind == "routine_run"
        await decide(
            session,
            business_id,
            approval.id,
            action="approve",
            version=approval.version,
            actor_user_id=t["owner"].user_id,
            via="whatsapp",
        )
        await session.commit()

    history = (await client.get(f"/v1/routines/{routine['id']}/runs", headers=t["headers"])).json()
    assert history[0]["status"] == "done"
    assert history[0]["contacted_count"] == 1
