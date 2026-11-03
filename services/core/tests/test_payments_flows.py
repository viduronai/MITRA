"""UPI collections end to end: employee links + approvals, reminders, manager command."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.payments import scheduler
from tests.helpers import FakeClock, bearer
from tests.manager_helpers import ask
from tests.payments_helpers import (
    CUSTOMER,
    connect_razorpay,
    create_link,
    customer_messages,
)
from tests.test_calls import TOKEN, configure_service, make_tenant


async def _employee_link(
    client: httpx.AsyncClient, employee_id: str, **fields: Any
) -> httpx.Response:
    body = {
        "employee_id": employee_id,
        "contact_phone": CUSTOMER,
        "amount_paise": 50_000,
        "purpose": "Consultation fee",
        "client_ref": f"call:{uuid.uuid4()}:1",
    } | fields
    return await client.post("/internal/v1/payments/links", json=body, headers=bearer(TOKEN))


async def test_employee_link_small_amount_goes_straight_out(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    configure_service()
    t = await make_tenant(client)
    await connect_razorpay(client, t["headers"])
    res = await _employee_link(client, t["employee"]["id"])
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "sent"
    assert res.json()["needs_approval"] is False
    assert len(await customer_messages(admin_engine, t["business"]["id"])) == 1
    res = await client.post("/internal/v1/payments/links", json={}, headers=bearer("wrong"))
    assert res.status_code == 401


async def test_big_amount_and_discount_ask_the_owner_first(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    configure_service()
    t = await make_tenant(client)
    bid = t["business"]["id"]
    await connect_razorpay(client, t["headers"])
    res = await _employee_link(client, t["employee"]["id"], amount_paise=2_500_000)  # ₹25,000
    body = res.json()
    assert body["status"] == "awaiting_approval"
    assert body["needs_approval"] is True
    assert await customer_messages(admin_engine, bid) == []  # nothing goes out before the OK

    approvals = (await client.get("/v1/approvals", headers=t["headers"])).json()["items"]
    card = next(a for a in approvals if a["kind"] == "payment_link")
    # The owner lowers the amount, then approves.
    res = await client.patch(
        f"/v1/approvals/{card['id']}",
        json={"payload": card["payload"] | {"amount_paise": 2_000_000}, "version": card["version"]},
        headers=t["headers"],
    )
    assert res.status_code == 200, res.text
    res = await client.post(
        f"/v1/approvals/{card['id']}/decide",
        json={"action": "approve", "version": card["version"] + 1},
        headers=t["headers"],
    )
    assert res.status_code == 200, res.text
    req = (
        await client.get(f"/v1/payments/{body['payment_request_id']}", headers=t["headers"])
    ).json()
    assert req["status"] == "sent"
    assert req["amount_paise"] == 2_000_000
    assert "₹20,000" in (await customer_messages(admin_engine, bid))[0]["body"]

    # Any discount asks first (default discount rule: above 0%); declining cancels it.
    res = await _employee_link(client, t["employee"]["id"], discount_percent=10)
    assert res.json()["status"] == "awaiting_approval"
    approvals = (await client.get("/v1/approvals", headers=t["headers"])).json()["items"]
    card = next(a for a in approvals if a["status"] == "pending")
    assert "10% off" in card["summary"]
    await client.post(
        f"/v1/approvals/{card['id']}/decide",
        json={"action": "decline", "version": card["version"]},
        headers=t["headers"],
    )
    req = (
        await client.get(f"/v1/payments/{res.json()['payment_request_id']}", headers=t["headers"])
    ).json()
    assert req["status"] == "cancelled"


async def _jobs(admin: AsyncEngine, business_id: str) -> list[dict[str, Any]]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text("SELECT status, variables FROM outbound_job WHERE business_id = :b"),
            {"b": uuid.UUID(business_id)},
        )
        return [dict(r._mapping) for r in rows]


async def test_overdue_link_reminds_then_stops_when_paid(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    bid = t["business"]["id"]
    await connect_razorpay(client, t["headers"])
    library = (await client.get("/v1/routines/library", headers=t["headers"])).json()
    assert any(r["id"] == "payment_reminder" for r in library)
    res = await client.post(
        "/v1/routines/from-library",
        json={"library_id": "payment_reminder", "enabled": True},
        headers=t["headers"],
    )
    assert res.status_code == 201, res.text

    due = date(2026, 10, 18)
    req = await create_link(client, t["headers"], due_date=due.isoformat())
    # Morning after the due date, 10:00 IST.
    assert req["remind_at"].startswith("2026-10-19T04:30")
    assert (await scheduler.tick(datetime(2026, 10, 19, 4, 0, tzinfo=UTC))).reminded == 0

    result = await scheduler.tick(datetime(2026, 10, 19, 4, 31, tzinfo=UTC))
    assert result.reminded == 1
    sent = await customer_messages(admin_engine, bid)
    assert len(sent) == 2
    assert sent[1]["template"] == "payment_reminder"
    assert "Already paid" in {b["title"] for b in sent[1]["buttons"]}
    jobs = await _jobs(admin_engine, bid)
    assert len(jobs) == 1
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["variables"]["payment_amount"] == "₹2,000"
    # Nothing repeats: the step ran once.
    assert (await scheduler.tick(datetime(2026, 10, 22, tzinfo=UTC))).reminded == 0

    link_path = req["short_url"].split("/v1/", 1)[1]
    await client.post(f"/v1/{link_path}/pay")
    jobs = await _jobs(admin_engine, bid)
    assert jobs[0]["status"] == "cancelled"
    async with admin_engine.connect() as conn:
        status = (
            await conn.execute(
                text("SELECT status FROM follow_up_task WHERE business_id = :b"),
                {"b": uuid.UUID(bid)},
            )
        ).scalar_one()
    assert status == "cancelled"


async def test_opted_out_customer_gets_no_reminder(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    bid = t["business"]["id"]
    await connect_razorpay(client, t["headers"])
    req = await create_link(client, t["headers"], due_date="2026-10-18")
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO opt_out (business_id, phone_hash, source)"
                " SELECT business_id, phone_hash, 'voice' FROM contact WHERE id = :c"
            ),
            {"c": uuid.UUID(req["contact_id"])},
        )
    await scheduler.tick(datetime(2026, 10, 20, tzinfo=UTC))
    assert len(await customer_messages(admin_engine, bid)) == 1  # only the original link


async def test_manager_command_sends_a_link_after_confirm(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    bid = t["business"]["id"]
    reply = await ask(client, t["owner"], bid, "Send Ramesh a payment link for ₹2,000")
    assert "payment collection" in reply["text"].lower()  # not set up yet

    await connect_razorpay(client, t["headers"])
    first = await create_link(client, t["headers"], amount_paise=10_000)  # makes Ramesh known
    reply = await ask(client, t["owner"], bid, "Send Ramesh a payment link for ₹2,000 for MRI scan")
    card = reply["card"]
    assert card["status"] == "pending"
    assert "₹2,000" in reply["text"]
    res = await client.post(
        f"/v1/approvals/{card['approval_id']}/decide",
        json={"action": "approve", "version": card["version"]},
        headers=t["headers"],
    )
    assert res.status_code == 200, res.text
    items = (
        await client.get(f"/v1/payments?contact_id={first['contact_id']}", headers=t["headers"])
    ).json()["items"]
    newest = items[0]
    assert newest["source"] == "manager"
    assert newest["amount_paise"] == 200_000
    assert newest["purpose"] == "MRI scan"
    assert newest["status"] == "sent"
    assert len(await customer_messages(admin_engine, bid)) == 2


async def test_tick_endpoint(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure_service()
    clock.now = datetime.now(UTC) + timedelta(days=1)
    res = await client.post("/internal/v1/payments/tick", headers=bearer(TOKEN))
    assert res.status_code == 200
    assert set(res.json()) == {"reminded", "skipped", "failed"}
