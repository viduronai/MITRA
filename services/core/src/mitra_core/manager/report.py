"""Morning report (MGR-01) and the Manager's periodic tick (reports + approval timeouts).

``tick(now)`` is safe to call every few minutes from anything (cron hitting the internal
endpoint, a Temporal schedule later): each business gets at most one report per local day,
sent at or after its configured time, and overdue approvals get their default (APPR-04).
TODO(temporal): replace the polling tick with per-business schedules.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.approvals import expire_due
from mitra_core.config import get_settings
from mitra_core.db import get_sessionmaker, tenant_session
from mitra_core.logging import get_logger
from mitra_core.manager import tools
from mitra_core.manager.answers import attention_lines, summary_lines
from mitra_core.manager.intents import Lang
from mitra_core.models import Business
from mitra_core.tenancy import TenantContext
from mitra_core.whatsapp import manager_settings, notify_owner

log = get_logger(__name__)

HEAD = {"en": "☀️ {name} · {day}", "hi": "☀️ {name} · {day}", "te": "☀️ {name} · {day}"}
TOMORROW = {"en": "Bookings today: {n}", "hi": "आज की बुकिंग: {n}", "te": "ఈ రోజు బుకింగ్స్: {n}"}


@dataclass(frozen=True, slots=True)
class TickResult:
    reports: int
    expired: int


async def build_report(
    session: AsyncSession, business_id: uuid.UUID, lang: Lang, now: datetime
) -> str:
    """≤ 6 lines: header, yesterday's numbers, today's bookings, what needs the owner, link."""
    name = await session.scalar(select(Business.name).where(Business.id == business_id)) or ""
    today = await tools.local_date(session, business_id, now)
    lines = [HEAD[lang].format(name=name, day=f"{today:%a %d %b}")]
    lines += (await summary_lines(session, business_id, "yesterday", lang, now))[:2]
    bookings = await tools.bookings_on(session, business_id, today)
    if bookings:
        lines.append(TOMORROW[lang].format(n=len(bookings)))
    attention, _ = await attention_lines(session, business_id, lang, now)
    lines.append(attention[0])
    lines.append(get_settings().app_base_url.rstrip("/") + "/")
    return "\n".join(lines[:6])


async def send_report_if_due(
    session: AsyncSession, business_id: uuid.UUID, tz: ZoneInfo, now: datetime
) -> bool:
    settings = await manager_settings(session, business_id)
    local = now.astimezone(tz)
    if not settings.report_enabled or settings.last_report_on == local.date():
        return False
    if local.time() < settings.report_time:
        return False
    lang: Lang = settings.language.value if settings.language else "en"
    body = await build_report(session, business_id, lang, now)
    stats = await tools.call_stats(session, business_id, "yesterday", now)
    attention = await tools.needs_attention(session, business_id, now)
    await notify_owner(
        session,
        business_id,
        "daily_report",
        body,
        dedupe_key=local.date().isoformat(),
        # Outside the owner's 24-hour window (the usual case at 8 am): the approved template.
        template="daily_report",
        params={
            "calls": str(stats.total),
            "booked": str(stats.by_result.get("booked", 0)),
            "attention": str(len(attention)),
        },
    )
    settings.last_report_on = local.date()
    return True


async def tick(now: datetime) -> TickResult:
    """Reports + approval timeouts for every business (each in its own tenant transaction)."""
    async with get_sessionmaker()() as session:
        rows = list(
            await session.execute(
                text("SELECT business_id, timezone FROM manager_due_businesses()")
            )
        )
    reports = expired = 0
    for business_id, tz_name in rows:
        try:
            tz = ZoneInfo(tz_name or "Asia/Kolkata")
        except (KeyError, ValueError):
            tz = ZoneInfo("Asia/Kolkata")
        try:
            async with tenant_session(TenantContext(business_id=business_id)) as session:
                expired += await expire_due(session, business_id, now)
                reports += await send_report_if_due(session, business_id, tz, now)
                await session.commit()
        except Exception as exc:
            log.error("manager.tick_failed", business_id=str(business_id), error=type(exc).__name__)
    return TickResult(reports=reports, expired=expired)
