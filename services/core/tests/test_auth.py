"""Phone OTP login, switch-business and the lockdown of the pre-auth table."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import Settings, get_settings
from mitra_core.main import app
from tests.helpers import FIXED_CODE, bearer, login, new_actor

PHONE = "+919876543210"


async def _request(client: httpx.AsyncClient, phone: str = PHONE) -> httpx.Response:
    return await client.post("/v1/auth/otp/request", json={"phone": phone})


async def _verify(client: httpx.AsyncClient, request_id: str, code: str) -> httpx.Response:
    return await client.post("/v1/auth/otp/verify", json={"request_id": request_id, "code": code})


async def test_request_returns_metadata_without_code_outside_local(
    client: httpx.AsyncClient,
) -> None:
    resp = await _request(client)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert set(body) == {"request_id", "expires_in", "resend_in"}
    assert (body["expires_in"], body["resend_in"]) == (300, 30)
    uuid.UUID(body["request_id"])


async def test_dev_code_only_in_local_env(client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(env="local")
    resp = await _request(client)
    code = resp.json()["dev_code"]
    assert len(code) == 6
    assert code.isdigit()
    verified = await _verify(client, resp.json()["request_id"], code)
    assert verified.status_code == 200, verified.text


async def test_new_user_login_is_unscoped(client: httpx.AsyncClient, fixed_code: str) -> None:
    session = await login(client, PHONE, name="Ravi")
    assert session["token_type"] == "bearer"
    assert session["expires_in"] > 0
    assert session["business_id"] is None
    assert session["memberships"] == []
    assert session["user"]["phone_last4"] == "3210"
    assert session["user"]["name"] == "Ravi"
    assert "phone" not in session["user"]

    me = await client.get("/v1/me", headers=bearer(session["access_token"]))
    assert me.status_code == 200
    assert me.json()["user"]["id"] == session["user"]["id"]


async def test_token_from_business_creation_and_relogin_are_scoped(
    client: httpx.AsyncClient, fixed_code: str
) -> None:
    first = await login(client, PHONE)
    created = await client.post(
        "/v1/businesses",
        json={"name": "Sunrise Clinic", "industry": "clinic"},
        headers=bearer(first["access_token"]),
    )
    assert created.status_code == 201, created.text
    scoped = bearer(created.json()["access_token"])
    current = await client.get("/v1/businesses/current", headers=scoped)
    assert current.status_code == 200
    business_id = created.json()["business"]["id"]

    again = await login(client, PHONE, name="Ignored For Existing Name")
    assert again["user"]["id"] == first["user"]["id"]
    assert again["business_id"] == business_id
    assert again["memberships"] == [
        {"business_id": business_id, "business_name": "Sunrise Clinic", "role": "owner"}
    ]
    resp = await client.get("/v1/employees", headers=bearer(again["access_token"]))
    assert resp.status_code == 200


async def test_name_is_set_once(client: httpx.AsyncClient, fixed_code: str) -> None:
    assert (await login(client, PHONE))["user"]["name"] is None
    assert (await login(client, PHONE, name="Ravi"))["user"]["name"] == "Ravi"
    assert (await login(client, PHONE, name="Someone"))["user"]["name"] == "Ravi"


async def test_existing_dev_token_user_can_log_in_by_phone(
    client: httpx.AsyncClient, fixed_code: str
) -> None:
    actor = new_actor("Lakshmi")
    assert (await client.get("/v1/me", headers=actor.headers())).status_code == 200
    session = await login(client, actor.phone)
    assert session["user"]["id"] == str(actor.user_id)


async def test_wrong_code_counts_attempts_then_locks(
    client: httpx.AsyncClient, fixed_code: str
) -> None:
    request_id = (await _request(client)).json()["request_id"]
    for left in (4, 3, 2, 1):
        resp = await _verify(client, request_id, "000000")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "otp_invalid"
        assert resp.json()["error"]["details"] == {"attempts_left": left}
    fifth = await _verify(client, request_id, "000000")
    assert fifth.status_code == 429
    assert fifth.json()["error"]["code"] == "otp_attempts_exceeded"
    # Even the right code is refused once locked.
    resp = await _verify(client, request_id, FIXED_CODE)
    assert resp.status_code == 429


async def test_code_is_single_use(client: httpx.AsyncClient, fixed_code: str) -> None:
    request_id = (await _request(client)).json()["request_id"]
    assert (await _verify(client, request_id, FIXED_CODE)).status_code == 200
    again = await _verify(client, request_id, FIXED_CODE)
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "otp_expired"


async def test_expired_code_is_rejected(
    client: httpx.AsyncClient, fixed_code: str, admin_engine: AsyncEngine
) -> None:
    request_id = (await _request(client)).json()["request_id"]
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE otp_request SET expires_at = now() - interval '1 second' WHERE id = :i"),
            {"i": uuid.UUID(request_id)},
        )
    resp = await _verify(client, request_id, FIXED_CODE)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "otp_expired"


async def test_unknown_request_id_is_invalid(client: httpx.AsyncClient) -> None:
    resp = await _verify(client, str(uuid.uuid4()), "123456")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "otp_invalid"


async def test_requests_are_rate_limited_per_phone(client: httpx.AsyncClient) -> None:
    for _ in range(3):
        assert (await _request(client)).status_code == 202
    resp = await _request(client)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    retry_after = int(resp.headers["retry-after"])
    assert 0 < retry_after <= 600
    assert resp.json()["error"]["details"] == {"retry_after": retry_after}
    # Other numbers are unaffected.
    assert (await _request(client, "+919876500000")).status_code == 202


async def test_rate_limit_window_slides(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    for _ in range(3):
        assert (await _request(client)).status_code == 202
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE otp_request SET created_at = now() - interval '11 min'"))
    assert (await _request(client)).status_code == 202


@pytest.mark.parametrize(
    "body",
    [
        {"phone": "9876543210"},
        {"phone": "+14155550100"},
        {"phone": "+914023456789"},  # landline, not a mobile
        {"phone": "+91987654321"},
        {"phone": PHONE, "extra": 1},
    ],
)
async def test_request_validation(client: httpx.AsyncClient, body: dict[str, object]) -> None:
    resp = await client.post("/v1/auth/otp/request", json=body)
    assert resp.status_code == 422
    assert "input" not in resp.json()["error"]["details"][0]


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", ""])
async def test_verify_validation(client: httpx.AsyncClient, code: str) -> None:
    resp = await _verify(client, str(uuid.uuid4()), code)
    assert resp.status_code == 422


async def test_switch_business(client: httpx.AsyncClient, fixed_code: str) -> None:
    session = await login(client, PHONE)
    token = bearer(session["access_token"])
    ids = []
    for name in ("Alpha Clinic", "Beta Homes"):
        resp = await client.post(
            "/v1/businesses", json={"name": name, "industry": "clinic"}, headers=token
        )
        ids.append(resp.json()["business"]["id"])

    resp = await client.post(
        "/v1/auth/switch-business", json={"business_id": ids[1]}, headers=token
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["business_id"] == ids[1]
    assert [m["business_id"] for m in body["memberships"]] == ids
    current = await client.get("/v1/businesses/current", headers=bearer(body["access_token"]))
    assert current.json()["name"] == "Beta Homes"

    outsider = await login(client, "+919000000001")
    resp = await client.post(
        "/v1/auth/switch-business",
        json={"business_id": ids[0]},
        headers=bearer(outsider["access_token"]),
    )
    assert resp.status_code == 403
    resp = await client.post("/v1/auth/switch-business", json={"business_id": ids[0]})
    assert resp.status_code == 401


async def test_codes_are_stored_hashed(
    client: httpx.AsyncClient, fixed_code: str, admin_engine: AsyncEngine
) -> None:
    await _request(client)
    async with admin_engine.connect() as conn:
        row = (await conn.execute(text("SELECT code_hash, phone_hash FROM otp_request"))).one()
    assert FIXED_CODE not in row.code_hash
    assert len(row.code_hash) == 64
    assert PHONE not in row.phone_hash


async def test_app_role_cannot_touch_otp_table_directly(
    client: httpx.AsyncClient, app_engine: AsyncEngine
) -> None:
    await _request(client)
    for sql in (
        "SELECT * FROM otp_request",
        "UPDATE otp_request SET attempts = 0",
        "DELETE FROM otp_request",
        "INSERT INTO otp_request (id, phone_e164, phone_hash, code_hash, expires_at) "
        "VALUES (gen_random_uuid(), '+919999999999', 'h', 'c', now())",
    ):
        async with app_engine.connect() as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(sql))


async def test_app_role_still_cannot_look_up_users_by_phone(
    client: httpx.AsyncClient, fixed_code: str, app_engine: AsyncEngine
) -> None:
    await login(client, PHONE)
    async with app_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT id FROM app_user WHERE phone_e164 = :p"), {"p": PHONE}
        )
        assert rows.all() == []


async def test_otp_functions_are_not_public(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT p.proname, p.prosecdef, p.proconfig, "
                    "  has_function_privilege('mitra_app', p.oid, 'EXECUTE'), "
                    "  EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0) "
                    "FROM pg_proc p WHERE p.proname LIKE 'auth_otp_%' ORDER BY 1"
                )
            )
        ).all()
    assert [r[0] for r in rows] == ["auth_otp_issue", "auth_otp_verify"]
    for name, definer, config, app_can_execute, public_can_execute in rows:
        assert definer, name
        assert config == ["search_path=pg_catalog, public"], name
        assert app_can_execute, name
        assert not public_can_execute, name
