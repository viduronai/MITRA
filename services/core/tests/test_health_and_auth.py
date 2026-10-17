from __future__ import annotations

import uuid
from datetime import timedelta

import httpx

from scripts.dev_token import mint
from tests.helpers import new_actor


async def test_liveness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["x-request-id"]


async def test_readiness_checks_database(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_request_id_is_propagated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["x-request-id"] == "abc-123"


async def test_unknown_route_uses_error_shape(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_openapi_is_served(client: httpx.AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert {"/v1/me", "/v1/businesses", "/v1/employees", "/v1/employees/{employee_id}"} <= set(
        paths
    )


async def test_missing_token_is_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "unauthenticated"
    assert set(body["error"]) == {"code", "message", "details"}
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_bad_and_expired_tokens_are_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401

    expired = mint(uuid.uuid4(), phone="+919800000001", ttl=timedelta(seconds=-5))
    resp = await client.get("/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == "Token expired"


async def test_token_with_invalid_phone_claim_is_rejected(client: httpx.AsyncClient) -> None:
    token = mint(uuid.uuid4(), phone="9876543210")  # not E.164
    resp = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_unknown_user_without_phone_is_401(client: httpx.AsyncClient) -> None:
    token = mint(uuid.uuid4())
    resp = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_me_provisions_user_on_first_request(client: httpx.AsyncClient) -> None:
    actor = new_actor("Ravi")
    resp = await client.get("/v1/me", headers=actor.headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["id"] == str(actor.user_id)
    assert body["user"]["name"] == "Ravi"
    assert body["user"]["preferred_locale"] == "en"
    assert body["memberships"] == []

    again = await client.get("/v1/me", headers=actor.headers())
    assert again.json()["user"] == body["user"]


async def test_phone_already_used_by_another_user_is_409(client: httpx.AsyncClient) -> None:
    first = new_actor()
    assert (await client.get("/v1/me", headers=first.headers())).status_code == 200
    impostor = new_actor()
    impostor.phone = first.phone
    resp = await client.get("/v1/me", headers=impostor.headers())
    assert resp.status_code == 409
