"""UPI collections: settings, links, the Razorpay webhook, the simulator, UPI-ID mode, timeline."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from mitra_core.payments.messages import rupees, upi_uri
from tests.helpers import FakeClock, add_member
from tests.payments_helpers import (
    CUSTOMER,
    HOOK_SECRET,
    KEY_SECRET,
    connect_razorpay,
    create_link,
    customer_messages,
    owner_messages,
    signed,
    webhook_token,
)
from tests.test_calls import make_tenant


def test_rupees_and_upi_uri() -> None:
    assert rupees(200_000) == "₹2,000"
    assert rupees(150_000_000) == "₹15,00,000"
    assert rupees(10_050) == "₹100.50"
    uri = upi_uri(
        vpa="sunrise@okhdfc", payee="Sunrise Clinic", amount_paise=50_050, note="Fee", ref="r1"
    )
    assert uri.startswith("upi://pay?pa=sunrise@okhdfc&pn=Sunrise%20Clinic&am=500.50&cu=INR")


async def test_settings_are_write_only_and_owner_only(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    t = await make_tenant(client)
    res = await client.get("/v1/payments/settings", headers=t["headers"])
    assert res.status_code == 200
    assert res.json()["mode"] == "none"
    out = await connect_razorpay(client, t["headers"])
    assert out["mode"] == "razorpay"
    assert out["razorpay_key_id"] == "rzp_test_••••3456"
    assert out["has_key_secret"]
    assert out["has_webhook_secret"]
    assert out["auto_confirm"]
    assert out["simulated"] is True
    assert KEY_SECRET not in json.dumps(out)
    assert HOOK_SECRET not in json.dumps(out)
    async with admin_engine.connect() as conn:
        sealed = (
            await conn.execute(text("SELECT razorpay_key_secret_sealed FROM collection_settings"))
        ).scalar_one()
    assert sealed.startswith("v2:")
    assert KEY_SECRET not in sealed

    # Same key id: secrets may be omitted and stay stored.
    res = await client.put(
        "/v1/payments/settings",
        json={"mode": "razorpay", "razorpay_key_id": "rzp_test_AbCdEf123456"},
        headers=t["headers"],
    )
    assert res.status_code == 200
    assert res.json()["has_key_secret"]
    # A new key id needs its secrets.
    res = await client.put(
        "/v1/payments/settings",
        json={"mode": "razorpay", "razorpay_key_id": "rzp_live_Zz9999999999"},
        headers=t["headers"],
    )
    assert res.status_code == 422

    res = await client.put(
        "/v1/payments/settings", json={"mode": "upi", "upi_vpa": "not a vpa"}, headers=t["headers"]
    )
    assert res.status_code == 422
    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    res = await client.get("/v1/payments", headers=staff.headers(t["business"]["id"]))
    assert res.status_code == 403
    manager = await add_member(admin_engine, t["business"]["id"], MemberRole.MANAGER)
    res = await client.put(
        "/v1/payments/settings",
        json={"mode": "none"},
        headers=manager.headers(t["business"]["id"]),
    )
    assert res.status_code == 403


async def test_link_needs_collection_set_up(client: httpx.AsyncClient) -> None:
    t = await make_tenant(client)
    res = await client.post(
        "/v1/payments",
        json={"phone": CUSTOMER, "amount_paise": 50_000, "purpose": "Fee"},
        headers=t["headers"],
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "collections_not_connected"


async def test_link_is_whatsapped_then_paid_via_simulator(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    bid = t["business"]["id"]
    await connect_razorpay(client, t["headers"])
    hook = await client.post(
        "/v1/webhooks",
        json={"url": "https://crm.example.com/hook", "events": ["payment.paid", "payment.failed"]},
        headers=t["headers"],
    )
    assert hook.status_code == 201, hook.text

    req = await create_link(client, t["headers"], client_ref="owner-1")
    assert req["status"] == "sent"
    assert req["provider"] == "sim"
    assert req["source"] == "owner"
    assert req["phone_last4"] == "3210"
    assert req["send_error"] is None
    assert req["short_url"].endswith(f"/v1/payments/sim/{req['short_url'].rsplit('/', 1)[-1]}")
    again = await create_link(client, t["headers"], client_ref="owner-1")
    assert again["id"] == req["id"]  # idempotent by client_ref

    sent = await customer_messages(admin_engine, bid)
    assert len(sent) == 1
    # Outside the customer's 24-hour window: the approved template with a Pay-now button.
    assert sent[0]["template"] == "payment_link"
    assert sent[0]["status"] == "sent"
    assert "2,000" in sent[0]["body"]
    assert CUSTOMER not in json.dumps(sent, default=str)

    link_path = req["short_url"].split("/v1/", 1)[1]
    page = await client.get(f"/v1/{link_path}")
    assert page.status_code == 200
    assert "Pay with UPI" in page.text
    res = await client.post(f"/v1/{link_path}/pay")
    assert res.status_code == 200
    assert "Payment received" in res.text

    paid = (await client.get(f"/v1/payments/{req['id']}", headers=t["headers"])).json()
    assert paid["status"] == "paid"
    assert paid["paid_via"] == "webhook"
    sent = await customer_messages(admin_engine, bid)
    assert len(sent) == 2
    assert sent[1]["template"] == "payment_received"
    listing = (await client.get("/v1/payments", headers=t["headers"])).json()
    assert listing["totals"]["collected_this_month_paise"] == 200_000
    assert listing["totals"]["pending_count"] == 0
    async with admin_engine.connect() as conn:
        events = (
            await conn.execute(
                text("SELECT event FROM webhook_delivery WHERE business_id = :b"),
                {"b": uuid.UUID(bid)},
            )
        ).scalars()
        assert list(events) == ["payment.paid"]

    # The customer page shows it on the timeline.
    detail = (await client.get(f"/v1/customers/{paid['contact_id']}", headers=t["headers"])).json()
    titles = [e["title"] for e in detail["timeline"] if e["kind"] == "payment"]
    assert titles == ["Payment received", "Payment link sent"]


async def test_webhook_signature_idempotency_and_failure_alert(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    bid = t["business"]["id"]
    settings = await connect_razorpay(client, t["headers"])
    token = webhook_token(settings)
    req = await create_link(client, t["headers"])
    link_id = req["short_url"].rsplit("/", 1)[-1]
    failed: dict[str, Any] = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "amount": 200_000,
                    "notes": {"mitra_request_id": req["id"]},
                    "error_description": "Bank declined",
                }
            }
        },
    }
    body = json.dumps(failed).encode()
    url = f"/v1/payments/webhooks/razorpay/{token}"
    res = await client.post(url, content=body, headers=signed(body, "wrong-secret"))
    assert res.status_code == 400
    res = await client.post(
        "/v1/payments/webhooks/razorpay/nope", content=body, headers=signed(body)
    )
    assert res.status_code == 404
    headers = signed(body) | {"X-Razorpay-Event-Id": "evt_1"}
    res = await client.post(url, content=body, headers=headers)
    assert res.json() == {"status": "failed"}
    res = await client.post(url, content=body, headers=headers)
    assert res.json() == {"status": "duplicate"}

    row = (await client.get(f"/v1/payments/{req['id']}", headers=t["headers"])).json()
    assert row["status"] == "failed"
    assert row["failure_reason"] == "Bank declined"
    alerts = [m for m in await owner_messages(admin_engine, bid) if "Payment failed" in m["body"]]
    assert len(alerts) == 1

    # A wrong amount never marks the bill paid.
    paid = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": link_id, "amount_paid": 100}},
            "payment": {"entity": {"id": "pay_2", "amount": 100}},
        },
    }
    body = json.dumps(paid).encode()
    res = await client.post(url, content=body, headers=signed(body) | {"X-Razorpay-Event-Id": "e2"})
    assert res.json() == {"status": "amount_mismatch"}
    paid["payload"]["payment_link"]["entity"]["amount_paid"] = 200_000  # type: ignore[index]
    body = json.dumps(paid).encode()
    res = await client.post(url, content=body, headers=signed(body) | {"X-Razorpay-Event-Id": "e3"})
    assert res.json() == {"status": "paid"}  # a failed attempt can still be paid later


async def test_upi_id_mode_is_marked_paid_by_hand(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    res = await client.put(
        "/v1/payments/settings",
        json={"mode": "upi", "upi_vpa": "sunrise@okhdfcbank", "payee_name": "Sunrise Clinic"},
        headers=t["headers"],
    )
    assert res.status_code == 200
    assert res.json()["auto_confirm"] is False
    req = await create_link(client, t["headers"], amount_paise=50_000)
    assert req["mode"] == "upi"
    assert req["short_url"].startswith("upi://pay?pa=sunrise@okhdfcbank")
    msg = (await customer_messages(admin_engine, t["business"]["id"]))[0]
    # Outside the 24-hour window: the UPI request template, naming the UPI ID.
    assert msg["template"] == "payment_upi_request"
    assert "sunrise@okhdfcbank" in msg["body"]
    assert "500" in msg["body"]
    assert msg["status"] == "sent"
    assert req["send_error"] is None
    res = await client.post(f"/v1/payments/{req['id']}/mark-paid", headers=t["headers"])
    assert res.status_code == 200
    assert res.json()["paid_via"] == "manual"
    res = await client.post(f"/v1/payments/{req['id']}/mark-paid", headers=t["headers"])
    assert res.status_code == 409


async def test_resend_and_cancel(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    await connect_razorpay(client, t["headers"])
    req = await create_link(client, t["headers"])
    clock.advance(120)
    res = await client.post(f"/v1/payments/{req['id']}/resend", headers=t["headers"])
    assert res.status_code == 200
    assert len(await customer_messages(admin_engine, t["business"]["id"])) == 2
    res = await client.post(f"/v1/payments/{req['id']}/cancel", headers=t["headers"])
    assert res.json()["status"] == "cancelled"
    res = await client.post(f"/v1/payments/{req['id']}/resend", headers=t["headers"])
    assert res.status_code == 409
    link_path = req["short_url"].split("/v1/", 1)[1]
    page = await client.get(f"/v1/{link_path}")
    assert "Pay with UPI" not in page.text  # nothing to pay on a cancelled link


async def test_payments_are_isolated_per_business(client: httpx.AsyncClient) -> None:
    a = await make_tenant(client, "Clinic A")
    b = await make_tenant(client, "Clinic B")
    await connect_razorpay(client, a["headers"])
    req = await create_link(client, a["headers"])
    res = await client.get(f"/v1/payments/{req['id']}", headers=b["headers"])
    assert res.status_code == 404
    assert (await client.get("/v1/payments", headers=b["headers"])).json()["items"] == []
