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


NEW_TENANT_TABLES = ("knowledge_source", "fact", "test_call")


async def _tenant_with_knowledge(client: httpx.AsyncClient, name: str) -> dict[str, Any]:
    owner = new_actor(name)
    business = await create_business(client, owner, name=name)
    employee = await create_employee(client, owner, business["id"])
    headers = owner.headers(business["id"])
    source = await client.post(
        "/v1/knowledge/sources", json={"type": "text", "text": "Fee: 500"}, headers=headers
    )
    call = await client.post(
        "/v1/test-calls", json={"employee_id": employee["id"]}, headers=headers
    )
    facts = (await client.get("/v1/knowledge/facts", headers=headers)).json()
    return {
        "headers": headers,
        "business": business,
        "ids": {
            "knowledge_source": source.json()["id"],
            "fact": facts[0]["id"],
            "test_call": call.json()["id"],
        },
    }


async def test_new_tables_are_isolated_per_tenant(
    client: httpx.AsyncClient, app_engine: AsyncEngine
) -> None:
    a = await _tenant_with_knowledge(client, "Clinic A")
    b = await _tenant_with_knowledge(client, "Clinic B")
    async with app_engine.connect() as conn:
        for table in NEW_TENANT_TABLES:
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, f"{table}: visible without a tenant"
    async with app_engine.begin() as conn:
        await conn.execute(SET_TENANT, {"b": a["business"]["id"]})
        for table in NEW_TENANT_TABLES:
            rows = (await conn.execute(text(f"SELECT id::text FROM {table}"))).scalars().all()
            assert rows == [a["ids"][table]], table
            result = await conn.execute(
                text(f"UPDATE {table} SET business_id = business_id WHERE id = :i"),
                {"i": uuid.UUID(b["ids"][table])},
            )
            assert result.rowcount == 0, table


async def test_app_role_cannot_insert_knowledge_into_another_tenant(
    client: httpx.AsyncClient, app_engine: AsyncEngine
) -> None:
    a = await _tenant_with_knowledge(client, "Clinic A")
    b = await _tenant_with_knowledge(client, "Clinic B")
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(SET_TENANT, {"b": a["business"]["id"]})
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(
                text(
                    "INSERT INTO fact (business_id, category, key, value, status) "
                    "VALUES (:b, 'faq', 'k', 'v', 'confirmed')"
                ),
                {"b": b["business"]["id"]},
            )
        await trans.rollback()


async def test_api_cannot_reach_other_tenants_knowledge_or_calls(
    client: httpx.AsyncClient,
) -> None:
    a = await _tenant_with_knowledge(client, "Clinic A")
    b = await _tenant_with_knowledge(client, "Clinic B")
    h = a["headers"]
    fact_b, call_b = b["ids"]["fact"], b["ids"]["test_call"]
    assert (
        await client.patch(f"/v1/knowledge/facts/{fact_b}", json={"value": "x"}, headers=h)
    ).status_code == 404
    assert (await client.delete(f"/v1/knowledge/facts/{fact_b}", headers=h)).status_code == 404
    assert (await client.get(f"/v1/test-calls/{call_b}", headers=h)).status_code == 404
    resp = await client.post(
        f"/v1/test-calls/{call_b}/corrections", json={"text": "Fee is ₹1"}, headers=h
    )
    assert resp.status_code == 404
    facts = (await client.get("/v1/knowledge/facts", headers=h)).json()
    assert [f["id"] for f in facts] == [a["ids"]["fact"]]
    sources = (await client.get("/v1/knowledge/sources", headers=h)).json()
    assert [s["id"] for s in sources] == [a["ids"]["knowledge_source"]]
    # B's fact is untouched.
    b_facts = (await client.get("/v1/knowledge/facts", headers=b["headers"])).json()
    assert b_facts[0]["value"] == "500"
