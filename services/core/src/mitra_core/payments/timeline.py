"""Payment requests as customer-timeline events (MEM-03): link sent, paid, failed, ..."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import PaymentRequest
from mitra_core.payments.messages import rupees
from mitra_core.schemas.customer import TimelineEvent

TITLES = {
    "awaiting_approval": "Payment link waiting for your OK",
    "sent": "Payment link sent",
    "paid": "Payment received",
    "failed": "Payment failed",
    "expired": "Payment link expired",
    "cancelled": "Payment link cancelled",
}


async def payment_events(session: AsyncSession, contact_id: uuid.UUID) -> list[TimelineEvent]:
    rows = await session.scalars(
        select(PaymentRequest)
        .where(PaymentRequest.contact_id == contact_id)
        .order_by(PaymentRequest.created_at.desc())
        .limit(50)
    )
    events: list[TimelineEvent] = []
    for req in rows:
        detail = f"{rupees(req.amount_paise)} · {req.purpose}"
        events.append(
            TimelineEvent(
                kind="payment",
                at=req.sent_at or req.created_at,
                title="Payment link sent"
                if req.status != "awaiting_approval"
                else TITLES[req.status],
                detail=detail,
                call_id=req.call_id,
                payment_request_id=req.id,
                payment_status="sent" if req.status != "awaiting_approval" else req.status,
            )
        )
        if req.status in ("paid", "failed", "expired", "cancelled"):
            at = req.paid_at or req.cancelled_at or req.updated_at
            events.append(
                TimelineEvent(
                    kind="payment",
                    at=at,
                    title=TITLES[req.status],
                    detail=detail,
                    payment_request_id=req.id,
                    payment_status=req.status,
                )
            )
    return events
