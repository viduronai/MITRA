"""Run the dialer worker in a loop: ``uv run python -m mitra_core.dialer.run``.

Each tick serves every business with due work (see ``worker.tick``). Safe to run more than one
copy: jobs are claimed with ``FOR UPDATE SKIP LOCKED``.
"""

from __future__ import annotations

import asyncio

from mitra_core.clock import utcnow
from mitra_core.config import get_settings
from mitra_core.db import dispose_engine, get_sessionmaker
from mitra_core.dialer.settings import get_dialer_settings
from mitra_core.dialer.voice import make_voice_dialer
from mitra_core.dialer.worker import WorkerDeps, tick
from mitra_core.logging import configure_logging, get_logger
from mitra_core.telephony.dnd import make_dnd_provider

log = get_logger("mitra_core.dialer")


async def main() -> None:
    settings, dialer = get_settings(), get_dialer_settings()
    configure_logging(settings.log_level)
    deps = WorkerDeps(
        settings=settings,
        dialer=dialer,
        dnd=make_dnd_provider(settings),
        voice=make_voice_dialer(dialer),
    )
    log.info("dialer.started", mode=dialer.mode, interval_s=dialer.interval_s)
    try:
        while True:
            report = await tick(get_sessionmaker(), deps, utcnow())
            if report.dialed or report.finished or report.blocked:
                log.info("dialer.tick", **report.__dict__)
            await asyncio.sleep(dialer.interval_s)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
