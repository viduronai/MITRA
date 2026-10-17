from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from scripts.dev_token import mint
from tests.helpers import add_member, create_business, create_employee, new_actor

WORKING_HOURS = {"mon": [{"start": "09:00", "end": "13:00"}, {"start": "14:00", "end": "19:00"}]}


async def test_employee_crud(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    headers = owner.headers(business["id"])

    created = await create_employee(
        client, owner, business["id"], name="Priya", working_hours=WORKING_HOURS
    )
    assert created["business_id"] == business["id"]
    assert created["status"] == "training"
    assert created["voice_tier"] == "natural"
    assert created["working_hours"]["mon"][1] == {"start": "14:00", "end": "19:00"}
    assert created["working_hours"]["tue"] is None

    second = await create_employee(
        client, owner, business["id"], name="Arjun", role_template="lead_caller"
    )

    listed = (await client.get("/v1/employees", headers=headers)).json()["items"]
    assert [e["id"] for e in listed] == [created["id"], second["id"]]

    resp = await client.get(f"/v1/employees/{created['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == created

    resp = await client.patch(
        f"/v1/employees/{created['id']}",
        json={"status": "paused", "voice_tier": "signature", "name": "Priya S"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert (patched["status"], patched["voice_tier"], patched["name"]) == (
        "paused",
        "signature",
        "Priya S",
    )
    assert patched["role_template"] == "receptionist"

    resp = await client.patch(
        f"/v1/employees/{created['id']}",
        json={"status": "working", "working_hours": None},
        headers=headers,
    )
    assert resp.json()["status"] == "working"
    assert resp.json()["working_hours"] is None


async def test_missing_employee_is_404(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    resp = await client.get(f"/v1/employees/{uuid.uuid4()}", headers=owner.headers(business["id"]))
    assert resp.status_code == 404
    assert resp.json()["error"] == {
        "code": "not_found",
        "message": "Employee not found",
        "details": None,
    }


async def test_staff_can_read_but_not_write_employees(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    employee = await create_employee(client, owner, business["id"])
    staff = await add_member(admin_engine, business["id"], MemberRole.STAFF)
    headers = staff.headers(business["id"])

    assert (await client.get("/v1/employees", headers=headers)).status_code == 200
    assert (await client.get(f"/v1/employees/{employee['id']}", headers=headers)).status_code == 200

    resp = await client.post(
        "/v1/employees",
        json={"name": "Sneaky", "role_template": "receptionist", "languages": ["en"]},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"

    resp = await client.patch(
        f"/v1/employees/{employee['id']}", json={"status": "paused"}, headers=headers
    )
    assert resp.status_code == 403


async def test_role_comes_from_membership_not_token_claim(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    """A staff member holding a token that claims 'owner' is still staff."""
    owner = new_actor()
    business = await create_business(client, owner)
    staff = await add_member(admin_engine, business["id"], MemberRole.STAFF)
    token = mint(staff.user_id, business_id=uuid.UUID(business["id"]), role=MemberRole.OWNER)
    resp = await client.post(
        "/v1/employees",
        json={"name": "Sneaky", "role_template": "receptionist", "languages": ["en"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_employee_validation_errors(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    headers = owner.headers(business["id"])
    base = {"name": "Priya", "role_template": "receptionist", "languages": ["te"]}
    cases = [
        base | {"role_template": "astrologer"},
        base | {"voice_tier": "ultra"},
        base | {"name": "x" * 61},
        base | {"name": ""},
        base | {"languages": []},
        base | {"status": "working"},  # status is not settable on create
        base | {"working_hours": {"mon": [{"start": "19:00", "end": "09:00"}]}},
        base | {"working_hours": {"mon": [{"start": "9am", "end": "17:00"}]}},
        base | {"working_hours": {"funday": []}},
    ]
    for body in cases:
        resp = await client.post("/v1/employees", json=body, headers=headers)
        assert resp.status_code == 422, body
        error = resp.json()["error"]
        assert error["code"] == "validation_error"
        assert isinstance(error["details"], list)
        assert error["details"], body

    employee = await create_employee(client, owner, business["id"])
    for patch in ({"status": "fired"}, {"name": None}, {"role_template": "lead_caller"}):
        resp = await client.patch(f"/v1/employees/{employee['id']}", json=patch, headers=headers)
        assert resp.status_code == 422, patch

    resp = await client.get("/v1/employees/not-a-uuid", headers=headers)
    assert resp.status_code == 422
