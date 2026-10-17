from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from tests.helpers import add_member, create_business, new_actor


async def test_create_business_makes_caller_owner(client: httpx.AsyncClient) -> None:
    owner = new_actor("Owner")
    resp = await client.post(
        "/v1/businesses",
        json={"name": "  Sunrise Clinic ", "industry": "clinic", "languages": ["te", "en"]},
        headers=owner.headers(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    business = body["business"]
    assert business["name"] == "Sunrise Clinic"
    assert business["timezone"] == "Asia/Kolkata"
    assert business["languages"] == ["te", "en"]
    assert business["agency_id"] is None
    assert body["membership"] == {
        "business_id": business["id"],
        "business_name": "Sunrise Clinic",
        "role": "owner",
    }

    me = (await client.get("/v1/me", headers=owner.headers())).json()
    assert me["memberships"] == [body["membership"]]


async def test_get_and_patch_current_business(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    headers = owner.headers(business["id"])

    resp = await client.get("/v1/businesses/current", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == business["id"]

    resp = await client.patch(
        "/v1/businesses/current",
        json={"name": "Sunrise Dental", "city": None, "timezone": "Asia/Calcutta"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["name"] == "Sunrise Dental"
    assert updated["city"] is None
    assert updated["timezone"] == "Asia/Calcutta"
    assert updated["industry"] == "clinic"  # untouched


async def test_patch_rejects_null_for_required_fields(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    resp = await client.patch(
        "/v1/businesses/current", json={"name": None}, headers=owner.headers(business["id"])
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_create_business_validation(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    cases = [
        {"name": "X", "industry": "bakery"},
        {"name": "x" * 121, "industry": "clinic"},
        {"name": "   ", "industry": "clinic"},
        {"name": "X", "industry": "clinic", "timezone": "Mars/Olympus"},
        {"name": "X", "industry": "clinic", "languages": ["te", "te"]},
        {"name": "X", "industry": "clinic", "languages": ["fr"]},
        {"name": "X", "industry": "clinic", "unexpected": 1},
    ]
    for body in cases:
        resp = await client.post("/v1/businesses", json=body, headers=owner.headers())
        assert resp.status_code == 422, body
        error = resp.json()["error"]
        assert error["code"] == "validation_error"
        assert error["details"], body
        assert "input" not in error["details"][0]


async def test_current_business_requires_business_scope(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    await create_business(client, owner)
    resp = await client.get("/v1/businesses/current", headers=owner.headers())
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "business_required"


async def test_non_member_cannot_act_in_business(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    outsider = new_actor()
    resp = await client.get("/v1/businesses/current", headers=outsider.headers(business["id"]))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_staff_cannot_patch_business(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    staff = await add_member(admin_engine, business["id"], MemberRole.STAFF)
    resp = await client.patch(
        "/v1/businesses/current", json={"name": "Hacked"}, headers=staff.headers(business["id"])
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["details"]["role"] == "staff"

    manager = await add_member(admin_engine, business["id"], MemberRole.MANAGER)
    resp = await client.patch(
        "/v1/businesses/current",
        json={"city": "Vijayawada"},
        headers=manager.headers(business["id"]),
    )
    assert resp.status_code == 200
