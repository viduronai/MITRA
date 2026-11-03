"""One process that runs every background job by calling the API's internal tick routes.

Run next to the API: ``uv run python -m mitra_core.scheduler`` (``--once`` runs every job one
time and exits, handy for testing locally). Each job has its own loop, so a slow or failing job
never delays the others; every tick route is safe to call concurrently and repeatedly (rows are
claimed with ``FOR UPDATE SKIP LOCKED`` and each step is recorded at most once).

Auth is the service token (``MITRA_SERVICE_TOKEN``). The process holds no database connection,
so it stays small; the API does the work under each business's RLS tenant.
TODO(temporal): replace the polling loops with Temporal Schedules (TRD section 9).
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

import httpx

from mitra_core.config import Settings, get_settings
from mitra_core.logging import configure_logging, get_logger

log = get_logger("mitra_core.scheduler")


@dataclass(frozen=True, slots=True)
class Job:
    name: str
    path: str
    interval_s: float


JOBS: tuple[Job, ...] = (
    Job("dialer", "/internal/v1/dialer/tick", 5),
    Job("team", "/internal/v1/team/tick", 30),
    Job("webhooks", "/internal/v1/webhooks/run", 30),
    Job("manager", "/internal/v1/manager/tick", 60),
    Job("payments", "/internal/v1/payments/tick", 60),
    Job("leads_pull", "/internal/v1/leads/pull", 300),
    Job("number_health", "/internal/v1/telephony/health/run", 6 * 3600),
)
TIMEOUT_S = 120.0


def make_client(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    token = settings.effective_service_token
    if not token:
        raise SystemExit("MITRA_SERVICE_TOKEN is not set; the internal API is disabled")
    return httpx.AsyncClient(
        base_url=settings.scheduler_api_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT_S,
        transport=transport,
    )


async def run_job(client: httpx.AsyncClient, job: Job) -> bool:
    """One tick. Never raises: a failure is logged and the loop carries on."""
    try:
        resp = await client.post(job.path)
    except httpx.HTTPError as exc:
        log.warning("scheduler.unreachable", job=job.name, error=type(exc).__name__)
        return False
    if resp.status_code >= 400:
        log.error("scheduler.job_failed", job=job.name, status=resp.status_code)
        return False
    log.debug("scheduler.job_ok", job=job.name)
    return True


async def run_once(client: httpx.AsyncClient, jobs: tuple[Job, ...] = JOBS) -> dict[str, bool]:
    results = await asyncio.gather(*(run_job(client, job) for job in jobs))
    return {job.name: ok for job, ok in zip(jobs, results, strict=True)}


async def _loop(client: httpx.AsyncClient, job: Job) -> None:
    while True:
        await run_job(client, job)
        await asyncio.sleep(job.interval_s)


async def run_forever(client: httpx.AsyncClient, jobs: tuple[Job, ...] = JOBS) -> None:
    await asyncio.gather(*(_loop(client, job) for job in jobs))


async def _main(once: bool) -> None:  # pragma: no cover - process entry point
    settings = get_settings()
    configure_logging(settings.log_level)
    async with make_client(settings) as client:
        if once:
            for name, ok in (await run_once(client)).items():
                print(f"{name:14} {'ok' if ok else 'FAILED'}")
            return
        log.info("scheduler.started", api=settings.scheduler_api_url, jobs=len(JOBS))
        await run_forever(client)


def main() -> None:  # pragma: no cover - process entry point
    parser = argparse.ArgumentParser(description="Mitra background jobs")
    parser.add_argument("--once", action="store_true", help="run every job once and exit")
    asyncio.run(_main(parser.parse_args().once))


if __name__ == "__main__":  # pragma: no cover
    main()
