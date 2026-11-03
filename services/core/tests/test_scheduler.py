"""The background-job scheduler: every job hits a real internal route, failures never stop it."""

from __future__ import annotations

import httpx

from mitra_core.config import Settings
from mitra_core.main import app
from mitra_core.scheduler import JOBS, make_client, run_once


async def test_every_job_targets_a_registered_post_route() -> None:
    # Without a token every real internal route refuses (401/403/503); 404/405 = wrong path.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        codes = {job.path: (await client.post(job.path)).status_code for job in JOBS}
    assert {path: code for path, code in codes.items() if code in {404, 405}} == {}


async def test_run_once_sends_token_and_survives_failures() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("authorization")))
        if request.url.path.endswith("/payments/tick"):
            return httpx.Response(500)
        if request.url.path.endswith("/leads/pull"):
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={})

    settings = Settings(service_token="s" * 40)
    async with make_client(settings, httpx.MockTransport(handler)) as client:
        results = await run_once(client)

    assert results["payments"] is False
    assert results["leads_pull"] is False
    assert all(ok for name, ok in results.items() if name not in {"payments", "leads_pull"})
    assert {path for path, _ in seen} == {job.path for job in JOBS}
    assert {auth for _, auth in seen} == {"Bearer " + "s" * 40}
