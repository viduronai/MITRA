"""Public billing API: wallet summary, mock top-ups, bonus, invoices, settings, ledger, roles."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from tests.billing_helpers import configure, summary, tenant, topup, usage
from tests.helpers import FakeClock, add_member

TRIAL = 45_000


async def test_new_wallet_gets_trial_credit(client: httpx.AsyncClient, clock: FakeClock) -> None:
    t = await tenant(client)
    s = await summary(client, t["headers"])
    assert (s["balance_paise"], s["bonus_paise"], s["available_paise"]) == (0, TRIAL, TRIAL)
    minutes = {r["tier"]: r["minutes_left"] for r in s["rates"]}
    assert minutes == {"smart": 150, "natural": 100, "signature": 75}
    assert {r["tier"]: r["paise_per_min"] for r in s["rates"]} == {
        "smart": 300,
        "natural": 450,
        "signature": 600,
    }
    assert s["outbound_paused"] is False
    assert s["month"] == "2026-10-01"
    assert s["topup_rules"]["min_paise"] == 50_000
    assert [b["pct"] for b in s["topup_rules"]["bonus_slabs"]] == [5, 10, 15]
    assert s["credits_expire_at"].startswith("2027-10-18")
    # A second read does not grant the trial again.
    assert (await summary(client, t["headers"]))["available_paise"] == TRIAL

    txns = (await client.get("/v1/billing/transactions", headers=t["headers"])).json()["items"]
    assert [(x["kind"], x["bonus_delta_paise"]) for x in txns] == [("bonus", TRIAL)]


async def test_mock_topup_credits_with_bonus_gst_and_invoice(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    t = await tenant(client)
    resp = await topup(client, t["headers"], 10_000)
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "paid"
    assert order["provider"] == "mock"
    assert (order["amount_paise"], order["bonus_paise"]) == (1_000_000, 50_000)
    assert (order["gst_paise"], order["total_paise"]) == (180_000, 1_180_000)
    assert order["checkout"] is None

    s = await summary(client, t["headers"])
    assert s["balance_paise"] == 1_000_000
    assert s["bonus_paise"] == TRIAL + 50_000

    invoices = (await client.get("/v1/billing/invoices", headers=t["headers"])).json()["items"]
    assert len(invoices) == 1
    assert invoices[0]["id"] == order["invoice_id"]
    inv = await client.get(f"/v1/billing/invoices/{order['invoice_id']}", headers=t["headers"])
    data = inv.json()
    assert data["number"].startswith("MIT/26-27/")
    assert len(data["number"]) <= 16
    assert data["buyer"]["name"] == "Sunrise Clinic"
    assert data["intra_state"] is True
    assert (data["cgst_paise"], data["sgst_paise"], data["igst_paise"]) == (90_000, 90_000, 0)
    assert data["taxable_paise"] + 180_000 == data["total_paise"]
    assert data["gst_rate_pct"] == 18

    kinds = [
        x["kind"]
        for x in (await client.get("/v1/billing/transactions", headers=t["headers"])).json()[
            "items"
        ]
    ]
    assert sorted(kinds) == ["bonus", "bonus", "topup"]


async def test_inter_state_invoice_uses_igst_and_profile(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    t = await tenant(client)
    resp = await client.patch(
        "/v1/billing/settings",
        json={
            "billing_name": "Sunrise Health Pvt Ltd",
            "gstin": "29abcde1234f1z5",
            "state_code": "29",
        },
        headers=t["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["profile"]["gstin"] == "29ABCDE1234F1Z5"
    order = (await topup(client, t["headers"], 500)).json()
    assert order["total_paise"] == 59_000
    inv = (
        await client.get(f"/v1/billing/invoices/{order['invoice_id']}", headers=t["headers"])
    ).json()
    assert (inv["igst_paise"], inv["cgst_paise"]) == (9_000, 0)
    assert inv["buyer"] == {
        "name": "Sunrise Health Pvt Ltd",
        "gstin": "29ABCDE1234F1Z5",
        "state_code": "29",
        "address": None,
    }


async def test_topup_validation(client: httpx.AsyncClient, clock: FakeClock) -> None:
    t = await tenant(client)
    for rupees in (0, 499):
        resp = await topup(client, t["headers"], rupees)
        assert resp.status_code == 422
    resp = await client.post(
        "/v1/billing/topups", json={"amount_paise": 50_050}, headers=t["headers"]
    )
    assert resp.json()["error"]["code"] == "invalid_topup"


async def test_topup_idempotency_key_replays(client: httpx.AsyncClient, clock: FakeClock) -> None:
    t = await tenant(client)
    first = await topup(client, t["headers"], 1000, **{"Idempotency-Key": "k1"})
    again = await topup(client, t["headers"], 1000, **{"Idempotency-Key": "k1"})
    assert again.headers.get("Idempotent-Replayed") == "true"
    assert again.json()["id"] == first.json()["id"]
    assert (await summary(client, t["headers"]))["balance_paise"] == 100_000


async def test_settings_cap_and_autopay(client: httpx.AsyncClient, clock: FakeClock) -> None:
    t = await tenant(client)
    resp = await client.patch(
        "/v1/billing/settings",
        json={"monthly_cap_paise": 0, "autopay_enabled": True, "autopay_amount_paise": 200_000},
        headers=t["headers"],
    )
    s = resp.json()
    assert (s["monthly_cap_paise"], s["cap_remaining_paise"]) == (0, 0)
    assert s["outbound_paused"] is True
    assert s["pause_reason"] == "spend_cap"
    assert (s["autopay_enabled"], s["autopay_amount_paise"]) == (True, 200_000)

    s = (
        await client.patch(
            "/v1/billing/settings", json={"monthly_cap_paise": None}, headers=t["headers"]
        )
    ).json()
    assert s["monthly_cap_paise"] is None
    assert s["outbound_paused"] is False

    bad = await client.patch(
        "/v1/billing/settings", json={"autopay_enabled": None}, headers=t["headers"]
    )
    assert bad.status_code == 422
    bad = await client.patch("/v1/billing/settings", json={"gstin": "nope"}, headers=t["headers"])
    assert bad.status_code == 422


async def test_staff_cannot_see_money(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await tenant(client)
    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    headers = staff.headers(t["business"]["id"])
    for path in ("/v1/billing/summary", "/v1/billing/transactions", "/v1/billing/invoices"):
        assert (await client.get(path, headers=headers)).status_code == 403
    assert (await topup(client, headers, 500)).status_code == 403
    manager = await add_member(admin_engine, t["business"]["id"], MemberRole.MANAGER)
    assert (await summary(client, manager.headers(t["business"]["id"])))["available_paise"] > 0


async def test_unauthenticated(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/billing/summary")).status_code == 401


async def test_usage_report_by_day_and_employee(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure()
    t = await tenant(client)
    emp = t["employee"]["id"]
    assert (await usage(client, emp, "c1", 61)).status_code == 200
    assert (await usage(client, emp, "c2", 9)).status_code == 200
    assert (await usage(client, emp, "c3", 0, outcome="unanswered")).status_code == 200
    clock.advance(86_400)
    next_day = clock.now
    resp = await usage(client, emp, "c4", 120, direction="inbound", started_at=next_day)
    assert resp.status_code == 200

    report = (await client.get("/v1/billing/usage?days=7", headers=t["headers"])).json()
    assert [(d["day"], d["calls"], d["amount_paise"]) for d in report["by_day"]] == [
        ("2026-10-18", 3, 458 + 75),
        ("2026-10-19", 1, 900),
    ]
    [row] = report["by_employee"]
    assert (row["employee_name"], row["tier"], row["calls"]) == ("Priya", "natural", 4)
    assert row["billable_seconds"] == 61 + 10 + 120
    s = await summary(client, t["headers"])
    assert s["month_usage_paise"] == 458 + 75 + 900
    assert s["number_rental"]["remaining_to_waive_paise"] == 300_000 - (458 + 75 + 900)
