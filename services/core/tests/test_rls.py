"""Tenant isolation: through the API and directly against Postgres as the app role."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import get_settings
from tests.helpers import create_business, create_employee, new_actor

SET_TENANT = text("SELECT set_config('app.business_id', :b, true)")


async def _two_tenants(client: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, Any]]:
    """Two businesses with one employee each, created through the API."""
    tenants = []
    for name, industry in (("Clinic A", "clinic"), ("Realty B", "real_estate")):
        owner = new_actor(name)
        business = await create_business(client, owner, name=name, industry=industry)
        employee = await create_employee(client, owner, business["id"], name=f"Emp {name}")
        tenants.append({"actor": owner, "business": business, "employee": employee})
    return tenants[0], tenants[1]


async def test_api_cannot_cross_tenants(client: httpx.AsyncClient) -> None:
    a, b = await _two_tenants(client)
    headers_a = a["actor"].headers(a["business"]["id"])
    emp_b_id = b["employee"]["id"]

    assert (await client.get(f"/v1/employees/{emp_b_id}", headers=headers_a)).status_code == 404
    resp = await client.patch(
        f"/v1/employees/{emp_b_id}", json={"status": "paused"}, headers=headers_a
    )
    assert resp.status_code == 404

    listed = (await client.get("/v1/employees", headers=headers_a)).json()["items"]
    assert [e["id"] for e in listed] == [a["employee"]["id"]]

    # B's employee is untouched.
    headers_b = b["actor"].headers(b["business"]["id"])
    resp = await client.get(f"/v1/employees/{emp_b_id}", headers=headers_b)
    assert resp.json()["status"] == "training"

    # Owner of A presenting a token scoped to B is rejected outright.
    resp = await client.get("/v1/employees", headers=a["actor"].headers(b["business"]["id"]))
    assert resp.status_code == 403


async def test_app_role_without_tenant_sees_nothing(
    client: httpx.AsyncClient, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    await _two_tenants(client)
    tables = ("business", "membership", "employee", "app_user")
    async with admin_engine.connect() as conn:
        for table in tables:
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count >= 2, f"setup: expected rows in {table}"
    async with app_engine.connect() as conn:
        assert (await conn.execute(text("SELECT current_user"))).scalar_one() == "mitra_app"
        for table in (*tables, "idempotency_record", "contact", "branch", "agency"):
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, table


async def test_app_role_with_tenant_sees_only_that_tenant(
    client: httpx.AsyncClient, app_engine: AsyncEngine
) -> None:
    a, _ = await _two_tenants(client)
    biz_a = a["business"]
    async with app_engine.begin() as conn:
        await conn.execute(SET_TENANT, {"b": biz_a["id"]})
        rows = (await conn.execute(text("SELECT id::text FROM employee"))).scalars().all()
        assert rows == [a["employee"]["id"]]
        businesses = (await conn.execute(text("SELECT id::text FROM business"))).scalars().all()
        assert businesses == [biz_a["id"]]


async def test_tenant_setting_does_not_leak_across_transactions(
    client: httpx.AsyncClient, app_engine: AsyncEngine
) -> None:
    """set_config(..., true) is transaction-local; a reused connection starts empty again."""
    a, _ = await _two_tenants(client)
    biz_a = a["business"]
    async with app_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(SET_TENANT, {"b": biz_a["id"]})
            assert (await conn.execute(text("SELECT count(*) FROM employee"))).scalar_one() == 1
        # Same connection, new transaction: setting reads back as '' -> no rows (and no error).
        async with conn.begin():
            assert (await conn.execute(text("SELECT count(*) FROM employee"))).scalar_one() == 0


async def test_app_role_cannot_write_into_another_tenant(
    client: httpx.AsyncClient, app_engine: AsyncEngine
) -> None:
    a, b = await _two_tenants(client)
    biz_a, biz_b = a["business"], b["business"]
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(SET_TENANT, {"b": biz_a["id"]})
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(
                text(
                    "INSERT INTO employee (business_id, name, role_template) "
                    "VALUES (:b, 'Mole', 'receptionist')"
                ),
                {"b": biz_b["id"]},
            )
        await trans.rollback()

        async with conn.begin():
            await conn.execute(SET_TENANT, {"b": biz_a["id"]})
            result = await conn.execute(
                text("UPDATE employee SET name = 'Owned' WHERE business_id = :b"),
                {"b": biz_b["id"]},
            )
            assert result.rowcount == 0


async def test_every_tenant_table_has_forced_rls(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                    "  EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid "
                    "          AND a.attname = 'business_id' AND NOT a.attisdropped), "
                    "  (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                    "  AND c.relname <> 'alembic_version'"
                )
            )
        ).all()
    assert rows
    for name, rls, forced, has_business_id, policies in rows:
        assert rls, f"{name}: RLS must be enabled"
        assert forced, f"{name}: RLS must be forced"
        if has_business_id or name == "business":
            assert policies > 0, f"{name}: tenant table without a policy"


async def test_app_role_is_not_privileged(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"),
                {"r": get_settings().app_db_role},
            )
        ).one()
    assert tuple(row) == (False, False)


async def test_unknown_business_in_token_is_forbidden(client: httpx.AsyncClient) -> None:
    actor = new_actor()
    resp = await client.get("/v1/employees", headers=actor.headers(uuid.uuid4()))
    assert resp.status_code == 403
