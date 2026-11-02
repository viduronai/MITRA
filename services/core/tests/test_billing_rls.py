"""Billing tenant isolation (API + raw app role) and append-only ledger grants."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.billing_helpers import configure, summary, tenant, topup, usage
from tests.helpers import FakeClock

SET_TENANT = text("SELECT set_config('app.business_id', :b, true)")
TABLES = ("wallet", "wallet_txn", "usage_event", "topup_order", "invoice")


async def _exec_as(
    engine: AsyncEngine, business_id: str, sql: str, params: dict[str, Any] | None = None
) -> None:
    async with engine.begin() as conn:
        await conn.execute(SET_TENANT, {"b": business_id})
        await conn.execute(text(sql), params or {})


async def _two(client: httpx.AsyncClient) -> tuple[dict, dict]:  # type: ignore[type-arg]
    configure()
    a = await tenant(client, name="Clinic A")
    b = await tenant(client, name="Realty B")
    for t in (a, b):
        assert (await topup(client, t["headers"], 500)).status_code == 201
        assert (
            await usage(client, t["employee"]["id"], f"call-{t['business']['id']}", 30)
        ).status_code == 200
    return a, b


async def test_api_isolation(client: httpx.AsyncClient, clock: FakeClock) -> None:
    a, b = await _two(client)
    inv_b = (await client.get("/v1/billing/invoices", headers=b["headers"])).json()["items"][0]
    resp = await client.get(f"/v1/billing/invoices/{inv_b['id']}", headers=a["headers"])
    assert resp.status_code == 404
    txns_a = (await client.get("/v1/billing/transactions", headers=a["headers"])).json()["items"]
    txns_b = (await client.get("/v1/billing/transactions", headers=b["headers"])).json()["items"]
    assert not {x["id"] for x in txns_a} & {x["id"] for x in txns_b}
    topup_b = next(x for x in txns_b if x["kind"] == "topup")
    assert topup_b["id"] not in {x["id"] for x in txns_a}
    report = (await client.get("/v1/billing/usage", headers=a["headers"])).json()
    assert [e["employee_id"] for e in report["by_employee"]] == [a["employee"]["id"]]
    # Same call id in another tenant is a different call (unique per business).
    same = await usage(client, a["employee"]["id"], f"call-{b['business']['id']}", 30)
    assert same.json()["replayed"] is False
    assert (await summary(client, b["headers"]))["month_usage_paise"] == 225


async def test_app_role_sees_only_bound_tenant(
    client: httpx.AsyncClient, clock: FakeClock, app_engine: AsyncEngine
) -> None:
    a, _ = await _two(client)
    async with app_engine.connect() as conn:
        for table in TABLES:
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, table
        # Reference rates are readable without a tenant.
        assert (await conn.execute(text("SELECT count(*) FROM rate_card"))).scalar_one() == 6
    async with app_engine.begin() as conn:
        await conn.execute(SET_TENANT, {"b": a["business"]["id"]})
        for table in TABLES:
            ids = await conn.execute(text(f"SELECT DISTINCT business_id::text FROM {table}"))
            assert ids.scalars().all() == [a["business"]["id"]], table


async def test_app_role_cannot_write_other_tenant(
    client: httpx.AsyncClient, clock: FakeClock, app_engine: AsyncEngine
) -> None:
    a, b = await _two(client)
    async with app_engine.begin() as conn:
        await conn.execute(SET_TENANT, {"b": a["business"]["id"]})
        updated = await conn.execute(
            text("UPDATE wallet SET balance_paise = 1000000000 WHERE business_id = :b"),
            {"b": uuid.UUID(b["business"]["id"])},
        )
        assert updated.rowcount == 0
    insert = (
        "INSERT INTO wallet_txn (business_id, kind, paid_delta_paise, bonus_delta_paise, "
        "balance_after_paise, bonus_after_paise, description, created_at) "
        "VALUES (:b, 'topup', 1, 0, 1, 0, 'x', now())"
    )
    with pytest.raises(DBAPIError, match="row-level security"):
        await _exec_as(
            app_engine, a["business"]["id"], insert, {"b": uuid.UUID(b["business"]["id"])}
        )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE wallet_txn SET paid_delta_paise = 0",
        "DELETE FROM wallet_txn",
        "UPDATE usage_event SET amount_paise = 0",
        "DELETE FROM usage_event",
        "UPDATE invoice SET total_paise = 0",
        "DELETE FROM wallet",
        "UPDATE rate_card SET paise_per_min = 1",
        "SELECT * FROM invoice_counter",
    ],
)
async def test_ledger_is_append_only_for_app_role(
    client: httpx.AsyncClient, clock: FakeClock, app_engine: AsyncEngine, statement: str
) -> None:
    a, _ = await _two(client)
    with pytest.raises(DBAPIError, match="permission denied"):
        await _exec_as(app_engine, a["business"]["id"], statement)


async def test_order_lookup_function_reveals_only_business_id(
    client: httpx.AsyncClient, clock: FakeClock, app_engine: AsyncEngine
) -> None:
    await _two(client)
    async with app_engine.connect() as conn:
        assert (await conn.execute(text("SELECT billing_topup_business('nope')"))).scalar() is None
        # Without a tenant the app role still cannot read the orders themselves.
        assert (await conn.execute(text("SELECT count(*) FROM topup_order"))).scalar_one() == 0
