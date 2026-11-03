"""The customer says they paid ("Already paid" button or a "PAID" reply on WhatsApp).

A claim is never proof: the request is only flagged (``customer_says_paid_at``) and the owner is
asked to confirm with "Mark paid". Queued reminder calls are withdrawn so the customer is not
chased while the owner checks; the link stays payable and still expires on its date.
Registered with the manager's WhatsApp button hook; imported by ``api.v1.payments``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.logging import get_logger
from mitra_core.manager.buttons import PaidClaim, register_paid_claim_handler
from mitra_core.models import Contact, PaymentRequest
from mitra_core.models.payments import OPEN_STATUSES
from mitra_core.payments import reminders
from mitra_core.payments.messages import rupees

log = get_logger(__name__)


async def _request_for(session: AsyncSession, claim: PaidClaim) -> PaymentRequest | None:
    """The claimed request, only if it belongs to the number that sent the claim."""
    stmt = (
        select(PaymentRequest)
        .join(Contact, Contact.id == PaymentRequest.contact_id)
        .where(PaymentRequest.business_id == claim.business_id)
        .where(Contact.phone_hash == claim.phone_hash)
        .where(PaymentRequest.status.in_(OPEN_STATUSES))
    )
    if claim.request_id is not None:
        stmt = stmt.where(PaymentRequest.id == claim.request_id)
    else:  # a bare "PAID" reply: their most recent open link
        stmt = stmt.order_by(PaymentRequest.created_at.desc()).limit(1)
    return await session.scalar(stmt.with_for_update(of=PaymentRequest))


async def on_paid_claim(session: AsyncSession, claim: PaidClaim) -> None:
    from mitra_core.whatsapp import notify_owner

    req = await _request_for(session, claim)
    if req is None or req.customer_says_paid_at is not None:
        return
    req.customer_says_paid_at = utcnow()
    await reminders.stop(session, req, reason="customer_says_paid")
    req.reminder_stage = 1  # no more reminders of any kind ...
    req.reminders = {**req.reminders, reminders.EXPIRY_SENT: "skipped"}
    req.remind_at = req.expires_at  # ... but the link still expires on its date
    who = req.customer_name or (f"…{req.phone_last4}" if req.phone_last4 else "A customer")
    await notify_owner(
        session,
        req.business_id,
        "payment_claimed",
        f"{who} says they paid {rupees(req.amount_paise)} for {req.purpose}. "
        "Check your account, then tap “Mark paid” in Payments.",
        ref={"payment_request_id": str(req.id)},
        dedupe_key=f"payment:{req.id}:claim",
    )
    log.info("payments.customer_says_paid", business_id=str(req.business_id), via=claim.via)


register_paid_claim_handler(on_paid_claim)
