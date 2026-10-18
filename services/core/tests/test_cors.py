from __future__ import annotations

from typing import Literal

import httpx
import pytest

from mitra_core.config import Settings
from mitra_core.main import create_app

Env = Literal["local", "test", "dev", "staging", "prod"]
PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
}


async def _preflight(env: Env, origin: str) -> httpx.Response:
    app = create_app(Settings(env=env))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.options("/v1/auth/otp/request", headers=PREFLIGHT | {"Origin": origin})


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://localhost:3100"])
async def test_local_allows_dev_origins(origin: str) -> None:
    resp = await _preflight("local", origin)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin
    assert "idempotency-key" in resp.headers["access-control-allow-headers"].lower()


async def test_local_rejects_other_origins() -> None:
    resp = await _preflight("local", "https://evil.example")
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.parametrize("env", ["test", "dev"])
async def test_no_cors_outside_local(env: Env) -> None:
    resp = await _preflight(env, "http://localhost:3000")
    assert "access-control-allow-origin" not in resp.headers
