"""Tenant isolation for the call and customer-memory tables (API and raw app-role SQL)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_calls import booked_call, configure_service, end, make_tenant, start

TABLES = ("call", "call_action", "interaction_summary", "memory_fact", "commitment")
SET_TENANT = text("SELECT set_config('app.business_id', :b, true)")


async def _two(client: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, Any]]:
    configure_service()
    a = await make_tenant(client, "Clinic A")
    b = await make_tenant(client, "Clinic B")
    a["call"] = await booked_call(client, a)
    b["call"] = await booked_call(client, b)
    return a, b


@pytest.mark.parametrize("table", TABLES)
async def test_app_role_sees_only_its_tenant(
    client: httpx.AsyncClient,
    app_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    table: str,
) -> None:
    a, b = await _two(client)
    async with admin_engine.connect() as conn:
        total = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
        assert total >= 2, f"setup: expected rows in {table}"
    async with app_engine.connect() as conn:
        assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
    async with app_engine.begin() as conn:
        await conn.execute(SET_TENANT, {"b": a["business"]["id"]})
        rows = await conn.execute(text(f"SELECT DISTINCT business_id::text FROM {table}"))
        assert rows.scalars().all() == [a["business"]["id"]]
    # Writing a row for another tenant is rejected by WITH CHECK.
    async with app_engine.begin() as conn:
        await conn.execute(SET_TENANT, {"b": a["business"]["id"]})
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(f"UPDATE {table} SET business_id = :other"),
                {"other": b["business"]["id"]},
            )


async def test_api_cannot_cross_tenants(client: httpx.AsyncClient) -> None:
    a, b = await _two(client)
    ha = a["headers"]
    b_call = b["call"]
    assert (await client.get(f"/v1/calls/{b_call}", headers=ha)).status_code == 404
    resp = await client.post(f"/v1/calls/{b_call}/rating", json={"rating": "up"}, headers=ha)
    assert resp.status_code == 404
    listed = (await client.get("/v1/calls", headers=ha)).json()["items"]
    assert [c["id"] for c in listed] == [a["call"]]

    hb = b["headers"]
    b_contact = (await client.get(f"/v1/calls/{b_call}", headers=hb)).json()["contact_id"]
    assert (await client.get(f"/v1/customers/{b_contact}", headers=ha)).status_code == 404
    forget = await client.post(f"/v1/customers/{b_contact}/forget", headers=ha)
    assert forget.status_code == 404
    assert (await client.get(f"/v1/customers/{b_contact}", headers=hb)).status_code == 200
    customers = (await client.get("/v1/customers", headers=ha)).json()
    assert customers["total"] == 1  # same phone, but a separate contact per business


async def test_internal_ingest_cannot_cross_tenants(client: httpx.AsyncClient) -> None:
    a, b = await _two(client)
    a_emp = a["employee"]["id"]
    # Ending B's call while presenting A's employee: invisible -> 404.
    assert (await end(client, b["call"], a_emp)).status_code == 404
    # Reusing B's call id under A: refused, B's call untouched.
    resp = await start(client, a_emp, call_id=b["call"])
    assert resp.status_code == 409
    resp = await start(client, a_emp, call_id=str(uuid.uuid4()))
    assert resp.status_code == 201
