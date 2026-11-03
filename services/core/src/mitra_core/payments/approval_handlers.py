"""The owner's answer to an employee's payment link ("Ask me first", APPR-01/06).

Approved: the link is created and sent at the (possibly lowered) approved amount. Declined or
timed out: the request is cancelled and the customer gets nothing. Imported by
``api.v1.payments`` so the handler is registered when the app starts.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.approvals import register_handler
from mitra_core.clock import utcnow
from mitra_core.models import PaymentRequest
from mitra_core.payments import service


async def on_payment_link_decided(session: AsyncSession, approval: Any) -> None:
    ref = (approval.payload or {}).get("payment_request_id")
    if not ref:
        return
    req = await session.scalar(
        select(PaymentRequest)
        .where(
            PaymentRequest.id == uuid.UUID(str(ref)),
            PaymentRequest.business_id == approval.business_id,
        )
        .with_for_update()
    )
    if req is None or req.status != "awaiting_approval":
        return
    now = utcnow()
    if approval.status != "approved":
        req.status, req.cancelled_at = "cancelled", now
        return
    amount = int(approval.payload.get("amount_paise") or req.amount_paise)
    if not 100 <= amount <= req.amount_paise:
        raise ValueError("approved amount must be at least ₹1 and not more than requested")
    req.amount_paise = amount
    await service.issue(session, req, now=now)


register_handler(service.APPROVAL_KIND, on_payment_link_decided)
