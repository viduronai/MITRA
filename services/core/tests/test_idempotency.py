from __future__ import annotations

import httpx

from tests.helpers import create_business, new_actor

EMPLOYEE = {"name": "Priya", "role_template": "receptionist", "languages": ["te"]}


async def test_employee_post_replays_with_same_key(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    headers = owner.headers(business["id"], **{"Idempotency-Key": "hire-priya-1"})

    first = await client.post("/v1/employees", json=EMPLOYEE, headers=headers)
    second = await client.post("/v1/employees", json=EMPLOYEE, headers=headers)
    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second.headers.get("idempotent-replayed") == "true"
    assert "idempotent-replayed" not in first.headers

    listed = await client.get("/v1/employees", headers=owner.headers(business["id"]))
    assert len(listed.json()["items"]) == 1

    # A different key creates a new employee.
    other = owner.headers(business["id"], **{"Idempotency-Key": "hire-priya-2"})
    third = await client.post("/v1/employees", json=EMPLOYEE, headers=other)
    assert third.json()["id"] != first.json()["id"]


async def test_reusing_key_with_different_body_is_rejected(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    headers = owner.headers(business["id"], **{"Idempotency-Key": "k1"})
    assert (await client.post("/v1/employees", json=EMPLOYEE, headers=headers)).status_code == 201
    resp = await client.post(
        "/v1/employees", json=EMPLOYEE | {"name": "Someone Else"}, headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "idempotency_key_reused"


async def test_keys_are_scoped_per_business(client: httpx.AsyncClient) -> None:
    a, b = new_actor(), new_actor()
    biz_a = await create_business(client, a, name="A")
    biz_b = await create_business(client, b, name="B")
    key = {"Idempotency-Key": "same-key"}
    resp_a = await client.post(
        "/v1/employees", json=EMPLOYEE, headers=a.headers(biz_a["id"], **key)
    )
    resp_b = await client.post(
        "/v1/employees", json=EMPLOYEE, headers=b.headers(biz_b["id"], **key)
    )
    assert resp_a.status_code == resp_b.status_code == 201
    assert resp_a.json()["id"] != resp_b.json()["id"]
    assert "idempotent-replayed" not in resp_b.headers


async def test_business_post_replays_with_same_key(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    body = {"name": "Sunrise Homes", "industry": "real_estate"}
    headers = owner.headers(**{"Idempotency-Key": "onboard-1"})
    first = await client.post("/v1/businesses", json=body, headers=headers)
    second = await client.post("/v1/businesses", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    # The token is minted per response (never stored), so compare everything else.
    replayed, original = second.json(), first.json()
    assert replayed.pop("access_token")
    assert original.pop("access_token")
    assert replayed == original
    assert second.headers.get("idempotent-replayed") == "true"

    me = (await client.get("/v1/me", headers=owner.headers())).json()
    assert len(me["memberships"]) == 1


async def test_invalid_idempotency_key_is_422(client: httpx.AsyncClient) -> None:
    owner = new_actor()
    resp = await client.post(
        "/v1/businesses",
        json={"name": "X", "industry": "other"},
        headers=owner.headers(**{"Idempotency-Key": "x" * 256}),
    )
    assert resp.status_code == 422
