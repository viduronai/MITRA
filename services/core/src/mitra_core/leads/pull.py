"""IndiaMART pull (INT-14): fetch enquiries since the last pull and ingest each one.

IndiaMART allows windows of at most 7 days and one call every 5 minutes per key; the job runs
from ``POST /internal/v1/leads/pull`` (every 5-10 min) and from "Fetch now" in the app.
Already-seen enquiries are skipped by their ``UNIQUE_QUERY_ID``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.leads.adapters import AdapterError, parse_indiamart_record
from mitra_core.leads.providers import IndiaMartProvider, ProviderError
from mitra_core.leads.service import IntakeDeps, check_rate, ingest
from mitra_core.models import Business, LeadIntake, LeadSource
from mitra_core.schemas.leads import PullOut

FIRST_WINDOW = timedelta(hours=24)
MAX_WINDOW = timedelta(days=7)
MIN_INTERVAL = timedelta(minutes=5)
IST = ZoneInfo("Asia/Kolkata")


async def pull_indiamart(
    session: AsyncSession,
    business: Business,
    intake: LeadIntake,
    source: LeadSource,
    provider: IndiaMartProvider,
    *,
    now: datetime,
    deps: IntakeDeps,
) -> PullOut:
    """Caller binds the tenant and commits."""
    if not source.credential:
        return PullOut(fetched=0, created=0, duplicates=0, error="IndiaMART key is not set")
    if source.last_pulled_at and now - source.last_pulled_at < MIN_INTERVAL:
        return PullOut(fetched=0, created=0, duplicates=0, error="Fetched recently, try again soon")
    start = max(source.last_pulled_at or now - FIRST_WINDOW, now - MAX_WINDOW)
    try:
        records = await provider.fetch(
            source.credential, start.astimezone(IST), now.astimezone(IST)
        )
    except ProviderError as exc:
        source.last_error = str(exc)[:300]
        return PullOut(fetched=0, created=0, duplicates=0, error=source.last_error)
    created = duplicates = 0
    for record in records:
        try:
            data = parse_indiamart_record(record)
        except AdapterError:
            continue
        await check_rate(session, business.id, now, deps.settings)
        result = await ingest(session, business, intake, source, data, now=now, deps=deps)
        if result.duplicate:
            duplicates += 1
        else:
            created += 1
    source.last_pulled_at = now
    source.last_error = None
    return PullOut(fetched=len(records), created=created, duplicates=duplicates)
