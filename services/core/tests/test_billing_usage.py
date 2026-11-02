"""Internal metering API: usage recording, idempotency, allowance, cap, grace, extras, expiry."""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import Settings, get_settings
from mitra_core.main import app
from tests.billing_helpers import TOKEN, configure, summary, tenant, topup, usage
from tests.helpers import FakeClock, bearer

TRIAL = 45_000


async def _drain(
    admin_engine: AsyncEngine, business_id: str, paid: int = 0, bonus: int = 0
) -> None:
    """Set balances directly (test setup only; the API never rewrites them like this)."""
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE wallet SET balance_paise = :p, bonus_paise = :b WHERE business_id = :id"),
            {"p": paid, "b": bonus, "id": uuid.UUID(business_id)},
        )


async def _allowance(client: httpx.AsyncClient, employee_id: str, direction: str) -> dict:  # type: ignore[type-arg]
    resp = await client.get(
        f"/internal/v1/billing/allowance?employee_id={employee_id}&direction={direction}",
        headers=bearer(TOKEN),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def test_requires_service_token(client: httpx.AsyncClient, clock: FakeClock) -> None:
    t = await tenant(client)
    resp = await usage(client, t["employee"]["id"], "c1", 30)
    assert resp.status_code == 503  # no token configured outside env=local
    configure()
    body = {"call_id": "c1", "employee_id": t["employee"]["id"], "direction": "inbound",
            "outcome": "connected", "connected_seconds": 30,
            "started_at": "2026-10-18T09:00:00Z"}  # fmt: skip
    assert (await client.post("/internal/v1/usage", json=body)).status_code == 401
    user = await client.post("/internal/v1/usage", json=body, headers=t["headers"])
    assert user.status_code == 401


async def test_records_and_rates_calls(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    t = await tenant(client)
    emp = t["employee"]["id"]

    nine = (await usage(client, emp, "call-9s", 9)).json()
    assert (nine["billable_seconds"], nine["amount_paise"], nine["tier"]) == (10, 75, "natural")
    assert nine["rate_paise_per_min"] == 450
    assert nine["bonus_paise"] == TRIAL - 75  # trial is bonus credit

    sixty_one = (await usage(client, emp, "call-61s", 61)).json()
    assert (sixty_one["billable_seconds"], sixty_one["amount_paise"]) == (61, 458)

    missed = (await usage(client, emp, "call-missed", 0, outcome="unanswered")).json()
    assert (missed["billable_seconds"], missed["amount_paise"]) == (0, 0)
    blocked = (await usage(client, emp, "call-blocked", 40, outcome="blocked")).json()
    assert blocked["amount_paise"] == 0

    s = await summary(client, t["headers"])
    assert s["available_paise"] == TRIAL - 75 - 458
    assert s["month_usage_paise"] == 75 + 458
    usage_lines = (
        await client.get("/v1/billing/transactions?kind=usage", headers=t["headers"])
    ).json()["items"]
    assert len(usage_lines) == 2  # free calls post no ledger line


async def test_tier_follows_employee_voice_tier(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure()
    t = await tenant(client, voice_tier="signature")
    out = (await usage(client, t["employee"]["id"], "c1", 60)).json()
    assert (out["tier"], out["amount_paise"]) == ("signature", 600)
    resp = await client.patch(
        f"/v1/employees/{t['employee']['id']}", json={"voice_tier": "smart"}, headers=t["headers"]
    )
    assert resp.status_code == 200
    out = (await usage(client, t["employee"]["id"], "c2", 60)).json()
    assert (out["tier"], out["amount_paise"]) == ("smart", 300)


async def test_usage_is_idempotent_by_call_id(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    t = await tenant(client)
    emp = t["employee"]["id"]
    first = (await usage(client, emp, "dup", 30)).json()
    again = (await usage(client, emp, "dup", 30)).json()
    assert again["replayed"] is True
    assert again["usage_event_id"] == first["usage_event_id"]
    assert (await summary(client, t["headers"]))["month_usage_paise"] == 225
    conflict = await usage(client, emp, "dup", 31)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "usage_conflict"


async def test_unknown_employee(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    assert (await usage(client, str(uuid.uuid4()), "c1", 30)).status_code == 404


async def test_zero_balance_pauses_outbound_and_inbound_gets_grace(
    client: httpx.AsyncClient, clock: FakeClock, admin_engine: AsyncEngine
) -> None:
    configure()
    t = await tenant(client)
    emp = t["employee"]["id"]
    await summary(client, t["headers"])  # create the wallet
    await _drain(admin_engine, t["business"]["id"], paid=450)  # one Natural minute

    allow = await _allowance(client, emp, "outbound")
    assert (allow["allowed"], allow["max_seconds"]) == (True, 60)
    out = (await usage(client, emp, "c1", 60)).json()
    assert (out["amount_paise"], out["outbound_paused"], out["pause_reason"]) == (
        450,
        True,
        "zero_balance",
    )
    allow = await _allowance(client, emp, "outbound")
    assert (allow["allowed"], allow["reason"]) == (False, "zero_balance")

    # Inbound keeps working on 3 free grace minutes per day.
    allow = await _allowance(client, emp, "inbound")
    assert (allow["allowed"], allow["max_seconds"]) == (True, 180)
    inbound = (await usage(client, emp, "c2", 100, direction="inbound")).json()
    assert (inbound["grace_seconds"], inbound["amount_paise"]) == (100, 0)
    assert (await summary(client, t["headers"]))["grace_seconds_left_today"] == 80
    over = (await usage(client, emp, "c3", 100, direction="inbound")).json()
    assert over["grace_seconds"] == 80
    assert over["amount_paise"] == 150  # 20 s beyond grace becomes a small debt
    assert over["balance_paise"] == -150
    assert (await _allowance(client, emp, "inbound"))["allowed"] is False

    # Grace resets the next day (IST); a top-up settles the debt first.
    clock.advance(86_400)
    assert (await _allowance(client, emp, "inbound"))["max_seconds"] == 180
    await topup(client, t["headers"], 500)
    s = await summary(client, t["headers"])
    assert s["balance_paise"] == 50_000 - 150
    assert s["outbound_paused"] is False


async def test_spend_cap_reached_mid_call(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    t = await tenant(client)
    emp = t["employee"]["id"]
    await client.patch(
        "/v1/billing/settings", json={"monthly_cap_paise": 1000}, headers=t["headers"]
    )
    allow = await _allowance(client, emp, "outbound")
    assert allow["max_seconds"] == 133  # ₹10 at ₹4.5/min, not the whole wallet
    first = (await usage(client, emp, "c1", 120)).json()
    assert (first["amount_paise"], first["outbound_paused"]) == (900, False)
    # Crosses the cap mid-call: billed in full, then outbound pauses.
    second = (await usage(client, emp, "c2", 60)).json()
    assert second["amount_paise"] == 450
    assert (second["outbound_paused"], second["pause_reason"]) == (True, "spend_cap")
    assert (await _allowance(client, emp, "outbound"))["reason"] == "spend_cap"
    assert (await _allowance(client, emp, "inbound"))["allowed"] is True  # inbound continues
    s = await summary(client, t["headers"])
    assert (s["cap_remaining_paise"], s["pause_reason"]) == (0, "spend_cap")

    # A new month resets the cap.
    clock.advance(14 * 86_400)
    assert (await _allowance(client, emp, "outbound"))["allowed"] is True


async def test_low_balance_alert_fires_once_and_autopay_tops_up(
    client: httpx.AsyncClient, clock: FakeClock, admin_engine: AsyncEngine
) -> None:
    configure()
    t = await tenant(client)
    emp = t["employee"]["id"]
    await summary(client, t["headers"])
    await _drain(admin_engine, t["business"]["id"], paid=20_450)
    first = (await usage(client, emp, "c1", 30)).json()  # 225 → 20,225 (still ≥ ₹200)
    assert (first["low_balance"], first["low_balance_alert"]) == (False, False)
    second = (await usage(client, emp, "c2", 60)).json()  # → 19,775
    assert (second["low_balance"], second["low_balance_alert"]) == (True, True)
    third = (await usage(client, emp, "c3", 60)).json()
    assert (third["low_balance"], third["low_balance_alert"]) == (True, False)

    await client.patch(
        "/v1/billing/settings",
        json={"autopay_enabled": True, "autopay_amount_paise": 100_000},
        headers=t["headers"],
    )
    await topup(client, t["headers"], 500)  # back above threshold re-arms the alert
    await _drain(admin_engine, t["business"]["id"], paid=20_100)
    fired = (await usage(client, emp, "c4", 60)).json()
    assert fired["low_balance_alert"] is True
    assert fired["autopay_topup_id"] is not None
    assert fired["balance_paise"] == 20_100 - 450 + 100_000  # mock autopay paid at once
    topup_status = await client.get(
        f"/v1/billing/topups/{fired['autopay_topup_id']}", headers=t["headers"]
    )
    assert (topup_status.json()["source"], topup_status.json()["status"]) == ("autopay", "paid")


async def test_passthrough_extras_and_number_rental_waiver(
    client: httpx.AsyncClient, clock: FakeClock, admin_engine: AsyncEngine
) -> None:
    configure()
    t = await tenant(client)
    biz = t["business"]["id"]
    body = {
        "business_id": biz,
        "category": "whatsapp",
        "amount_paise": 88,
        "ref": "wa-msg-1",
        "description": "WhatsApp template (Meta rate)",
    }
    first = await client.post("/internal/v1/billing/passthrough", json=body, headers=bearer(TOKEN))
    again = await client.post("/internal/v1/billing/passthrough", json=body, headers=bearer(TOKEN))
    assert (first.json()["created"], again.json()["created"]) == (True, False)
    assert (await summary(client, t["headers"]))["month_extras_paise"] == 88

    rent = {"business_id": biz, "month": "2026-10", "numbers": 1}
    resp = await client.post("/internal/v1/billing/number-rental", json=rent, headers=bearer(TOKEN))
    assert resp.json() | {"txn_id": None} == {
        "month": "2026-10",
        "usage_paise": 0,
        "amount_paise": 49_900,
        "waived": False,
        "txn_id": None,
    }
    repeat = await client.post(
        "/internal/v1/billing/number-rental", json=rent, headers=bearer(TOKEN)
    )
    assert repeat.json()["txn_id"] == resp.json()["txn_id"]  # charged once
    extras = (
        await client.get("/v1/billing/transactions?kind=passthrough", headers=t["headers"])
    ).json()["items"]
    assert sorted(x["category"] for x in extras) == ["number_rental", "whatsapp"]

    # Another business with ≥ ₹3,000 of usage that month: the rental is waived.
    busy = await tenant(client, name="Busy Realty")
    await summary(client, busy["headers"])
    await _drain(admin_engine, busy["business"]["id"], paid=10_00_000)
    await usage(client, busy["employee"]["id"], "long", 40_000)  # 40,000 s x 7.5 p = ₹3,000
    waived = await client.post(
        "/internal/v1/billing/number-rental",
        json=rent | {"business_id": busy["business"]["id"]},
        headers=bearer(TOKEN),
    )
    body_out = waived.json()
    assert (body_out["usage_paise"], body_out["waived"], body_out["amount_paise"]) == (
        300_000,
        True,
        0,
    )
    assert body_out["txn_id"] is None


async def test_credits_expire_twelve_months_after_last_topup(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    t = await tenant(client)
    await topup(client, t["headers"], 500)
    clock.advance(200 * 86_400)
    await topup(client, t["headers"], 500)  # extends validity
    clock.advance(200 * 86_400)
    assert (await summary(client, t["headers"]))["available_paise"] == TRIAL + 100_000
    clock.advance(170 * 86_400)  # > 12 months after the last top-up
    s = await summary(client, t["headers"])
    assert (s["balance_paise"], s["bonus_paise"]) == (0, 0)
    expiry = (
        await client.get("/v1/billing/transactions?kind=expiry", headers=t["headers"])
    ).json()["items"]
    assert len(expiry) == 1
    assert (expiry[0]["paid_delta_paise"], expiry[0]["bonus_delta_paise"]) == (-100_000, -TRIAL)


async def test_local_env_dev_token(client: httpx.AsyncClient, clock: FakeClock) -> None:
    from mitra_core.config import _DEV_SERVICE_TOKEN

    app.dependency_overrides[get_settings] = lambda: Settings(env="local")
    t = await tenant(client)
    body = {"call_id": "c1", "employee_id": t["employee"]["id"], "direction": "outbound",
            "outcome": "connected", "connected_seconds": 12.2,
            "started_at": "2026-10-18T09:00:00Z"}  # fmt: skip
    resp = await client.post("/internal/v1/usage", json=body, headers=bearer(_DEV_SERVICE_TOKEN))
    assert resp.status_code == 200
    assert resp.json()["billable_seconds"] == 13
