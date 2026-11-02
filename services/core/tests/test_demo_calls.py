"""Public demo calls: validation, consent, per-phone and per-IP rate limits, table lockdown."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.main import app

PHONE = "+919876543210"
BODY = {"phone": PHONE, "language": "te", "industry": "clinic", "consent": True}


def _client_from(ip: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 50000))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def visitor() -> AsyncIterator[httpx.AsyncClient]:
    async with _client_from("203.0.113.10") as c:
        yield c


async def _post(client: httpx.AsyncClient, **fields: object) -> httpx.Response:
    return await client.post("/v1/demo-calls", json=BODY | fields)


async def test_accepts_a_consented_request_without_auth(visitor: httpx.AsyncClient) -> None:
    resp = await _post(visitor)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert set(body) == {"id", "status", "phone_last4", "eta_seconds", "simulated"}
    assert body["status"] == "queued"
    assert body["simulated"] is True
    assert body["phone_last4"] == "3210"
    assert body["eta_seconds"] == 30
    uuid.UUID(body["id"])


async def test_defaults_language_and_industry(visitor: httpx.AsyncClient) -> None:
    resp = await visitor.post("/v1/demo-calls", json={"phone": PHONE, "consent": True})
    assert resp.status_code == 202, resp.text


async def test_stores_only_hashes(visitor: httpx.AsyncClient, admin_engine: AsyncEngine) -> None:
    await _post(visitor, industry="real_estate", language="hi")
    async with admin_engine.connect() as conn:
        row = (await conn.execute(text("SELECT * FROM demo_call"))).mappings().one()
    assert row["phone_last4"] == "3210"
    assert len(row["phone_hash"]) == 64
    assert len(row["ip_hash"]) == 64
    flat = " ".join(str(v) for v in row.values())
    assert "9876543210" not in flat
    assert "203.0.113.10" not in flat
    assert (row["language"], row["industry"]) == ("hi", "real_estate")
    assert row["simulated"] is True
    assert row["status"] == "queued"
    assert row["consented_at"] is not None


@pytest.mark.parametrize(
    "fields",
    [
        {"consent": False},
        {"consent": None},
        {"consent": "yes"},
    ],
)
async def test_consent_is_required(visitor: httpx.AsyncClient, fields: dict[str, object]) -> None:
    resp = await _post(visitor, **fields)
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["loc"] == ["body", "consent"]


async def test_missing_consent_is_rejected(visitor: httpx.AsyncClient) -> None:
    resp = await visitor.post("/v1/demo-calls", json={"phone": PHONE})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "fields",
    [
        {"phone": "9876543210"},  # no country code
        {"phone": "+915876543210"},  # mobiles start 6-9
        {"phone": "+914023456789"},  # landline
        {"phone": "+91987654321"},  # 9 digits
        {"phone": "+9198765432100"},  # 11 digits
        {"phone": "+14155550100"},  # not India
        {"phone": ""},
        {"language": "ta"},
        {"industry": "bank"},
        {"extra": 1},
    ],
)
async def test_validation(visitor: httpx.AsyncClient, fields: dict[str, object]) -> None:
    resp = await _post(visitor, **fields)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    # Never echo the submitted number back.
    assert "input" not in body["error"]["details"][0]
    assert "98765" not in resp.text


async def test_rate_limited_per_phone_across_ips(visitor: httpx.AsyncClient) -> None:
    assert (await _post(visitor)).status_code == 202
    async with _client_from("198.51.100.7") as other:
        assert (await _post(other)).status_code == 202
        resp = await _post(other)
    assert resp.status_code == 429
    retry_after = int(resp.headers["retry-after"])
    assert 0 < retry_after <= 24 * 3600
    err = resp.json()["error"]
    assert err["code"] == "rate_limited"
    assert err["details"] == {"reason": "phone_limited", "retry_after": retry_after}
    # Another number from the same network is fine.
    assert (await _post(visitor, phone="+919000000001")).status_code == 202


async def test_rate_limited_per_ip(visitor: httpx.AsyncClient) -> None:
    for i in range(5):
        assert (await _post(visitor, phone=f"+91900000000{i}")).status_code == 202
    resp = await _post(visitor, phone="+919000000009")
    assert resp.status_code == 429
    assert resp.json()["error"]["details"]["reason"] == "ip_limited"
    assert 0 < int(resp.headers["retry-after"]) <= 3600
    async with _client_from("198.51.100.7") as other:
        assert (await _post(other, phone="+919000000009")).status_code == 202


async def test_limited_requests_are_not_stored(
    visitor: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    for _ in range(4):
        await _post(visitor)
    async with admin_engine.connect() as conn:
        assert (await conn.scalar(text("SELECT count(*) FROM demo_call"))) == 2


async def test_phone_window_slides(visitor: httpx.AsyncClient, admin_engine: AsyncEngine) -> None:
    for _ in range(2):
        assert (await _post(visitor)).status_code == 202
    assert (await _post(visitor)).status_code == 429
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE demo_call SET created_at = now() - interval '25 hours'"))
    assert (await _post(visitor)).status_code == 202


async def test_old_requests_are_purged(
    visitor: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    await _post(visitor)
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE demo_call SET created_at = now() - interval '31 days'"))
    await _post(visitor, phone="+919000000001")
    async with admin_engine.connect() as conn:
        assert (await conn.scalar(text("SELECT count(*) FROM demo_call"))) == 1


async def test_app_role_cannot_touch_demo_table_directly(
    visitor: httpx.AsyncClient, app_engine: AsyncEngine
) -> None:
    await _post(visitor)
    for sql in (
        "SELECT * FROM demo_call",
        "UPDATE demo_call SET status = 'x'",
        "DELETE FROM demo_call",
        "INSERT INTO demo_call (id, phone_hash, phone_last4, ip_hash, language, industry, "
        "consented_at) VALUES (gen_random_uuid(), 'h', '0000', 'i', 'en', 'clinic', now())",
    ):
        async with app_engine.connect() as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(sql))
