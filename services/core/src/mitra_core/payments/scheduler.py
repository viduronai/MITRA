"""The payment reminder tick: overdue and expiring links, and expiry itself (ACT-11).

``payments_due_work(now)`` (SECURITY DEFINER, migration 0006_payments) lists ``(business_id,
id)`` of open requests whose ``remind_at`` (the next step, see ``reminders.next_step_at``) has
passed; each is handled in its own transaction with that business bound as the RLS tenant,
row-locked with ``SKIP LOCKED``.

Steps, each at most once per link:

* the morning after the due date: a WhatsApp with the link, then ``payment.overdue`` starts the
  business's "Payment reminder" routine (one call, a day later, through the dialer's gate);
* two days before the link expires (default 15 days after sending): one WhatsApp;
* at expiry: the request becomes ``expired`` and any queued reminder call is cancelled.

Customers who said "don't call me" (any opt-out) get no reminders.

Run with ``POST /internal/v1/payments/tick`` or ``uv run python -m mitra_core.payments.scheduler``.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.db import get_sessionmaker, tenant_session
from mitra_core.logging import get_logger
from mitra_core.models import Business, Contact, OptOut, PaymentRequest
from mitra_core.models.payments import OPEN_STATUSES
from mitra_core.payments import reminders, service
from mitra_core.payments.settings import get_settings_row
from mitra_core.tenancy import TenantContext

log = get_logger(__name__)
_DUE = text("SELECT business_id, id FROM payments_due_work(:now) LIMIT :limit")
TICK_LIMIT = 200


@dataclass
class TickResult:
    reminded: int = 0
    skipped: int = 0
    failed: int = 0


async def opted_out(session: AsyncSession, req: PaymentRequest) -> bool:
    if req.contact_id is None:
        return True
    phone_hash = await session.scalar(
        select(Contact.phone_hash).where(Contact.id == req.contact_id)
    )
    if phone_hash is None:
        return True
    found = await session.scalar(
        select(OptOut.id).where(
            OptOut.business_id == req.business_id, OptOut.phone_hash == phone_hash
        )
    )
    return found is not None


async def remind(session: AsyncSession, req: PaymentRequest, *, now: datetime) -> bool:
    """Run whatever is due for one locked request. True when the customer was messaged."""
    req.remind_at = None
    if req.status not in OPEN_STATUSES:
        return False
    if req.expires_at is not None and req.expires_at <= now:
        await service.mark_expired(session, req, now=now)  # also stops reminder calls
        return False
    settings = await get_settings_row(session, req.business_id)
    tz = await session.scalar(select(Business.timezone).where(Business.id == req.business_id))
    tz = tz or "Asia/Kolkata"
    done = False
    overdue = reminders.overdue_at(req.due_date, tz)
    notice = reminders.expiry_notice_at(req)
    if settings.reminders_enabled and await opted_out(session, req):
        # Nothing more for someone who asked not to be contacted; only the expiry remains.
        req.reminder_stage = 1
        req.reminders = {**req.reminders, "skipped": "opted_out", reminders.EXPIRY_SENT: "skipped"}
    elif settings.reminders_enabled and req.reminder_stage == 0 and overdue and overdue <= now:
        req.reminder_stage = 1
        sent = await service.deliver(
            session, req, "reminder", dedupe_key=f"payment:{req.id}:reminder"
        )
        await reminders.fire(session, req, "payment.overdue", now=now)
        req.reminders = {**req.reminders, "whatsapp_at": now.isoformat(), "whatsapp_sent": sent}
        done = True
    elif settings.reminders_enabled and notice and notice <= now and req.expires_at:
        last_day = req.expires_at.astimezone(ZoneInfo(tz)).date()
        await service.deliver(
            session, req, "expiry", dedupe_key=f"payment:{req.id}:expiry", due=last_day
        )
        req.reminders = {**req.reminders, reminders.EXPIRY_SENT: now.isoformat()}
        done = True
    req.remind_at = reminders.next_step_at(req, reminders_enabled=settings.reminders_enabled, tz=tz)
    return done


async def _one(business_id: uuid.UUID, request_id: uuid.UUID, now: datetime) -> bool:
    async with tenant_session(TenantContext(business_id=business_id)) as session:
        req = await session.scalar(
            select(PaymentRequest)
            .where(PaymentRequest.id == request_id, PaymentRequest.business_id == business_id)
            .with_for_update(skip_locked=True)
        )
        if req is None or req.remind_at is None or req.remind_at > now:
            return False
        done = await remind(session, req, now=now)
        await session.commit()
        return done


async def tick(now: datetime | None = None) -> TickResult:
    now = now or utcnow()
    async with get_sessionmaker()() as session:
        due = (await session.execute(_DUE, {"now": now, "limit": TICK_LIMIT})).all()
    result = TickResult()
    for business_id, request_id in due:
        try:
            if await _one(business_id, request_id, now):
                result.reminded += 1
            else:
                result.skipped += 1
        except Exception as exc:
            result.failed += 1
            log.error(
                "payments.tick_failed", business_id=str(business_id), exc_type=type(exc).__name__
            )
    if due:
        log.info("payments.tick", reminded=result.reminded, failed=result.failed)
    return result


def main() -> None:  # pragma: no cover - process entry point
    parser = argparse.ArgumentParser(description="Mitra payment reminders")
    parser.add_argument("--interval", type=float, default=60.0, help="seconds between ticks")
    parser.add_argument("--once", action="store_true", help="run a single tick and exit")
    args = parser.parse_args()

    async def loop() -> None:
        while True:
            await tick()
            await asyncio.sleep(args.interval)

    asyncio.run(tick() if args.once else loop())


if __name__ == "__main__":  # pragma: no cover
    main()
