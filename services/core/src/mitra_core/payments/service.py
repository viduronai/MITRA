"""Payment requests: create, approve, send, mark paid / failed / expired, cancel (ACT-05/11).

All functions take a session bound to the business (RLS) and never commit; the caller owns the
transaction. Money is integer paise. This is the business's money: nothing here touches
Mitra's wallet.

Who may create a request and what needs the owner first (APPR-01):

* the owner in the app, or the owner's confirmed manager command: sent at once;
* an AI employee (during or after a call): asks first (approval kind ``payment_link``) when the
  link carries a discount the ``discount`` rule covers, or the amount is above the
  ``payment_link`` rule's threshold. The owner may lower the amount before approving.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.errors import AppError, not_found
from mitra_core.logging import get_logger
from mitra_core.models import Business, CollectionSettings, Contact, PaymentRequest
from mitra_core.models.payments import OPEN_STATUSES
from mitra_core.payments import messages, reminders
from mitra_core.payments.settings import get_settings_row, razorpay_for

log = get_logger(__name__)

Source = Literal["owner", "employee", "manager"]
APPROVAL_KIND = "payment_link"
SmsSender = Callable[[AsyncSession, uuid.UUID, str, str], Awaitable[bool]]

_sms_sender: SmsSender | None = None


def register_sms_sender(fn: SmsSender | None) -> None:
    """Optional SMS fallback when WhatsApp can't deliver: ``fn(session, business, phone, text)``."""
    global _sms_sender
    _sms_sender = fn


@dataclass(slots=True)
class NewRequest:
    amount_paise: int
    purpose: str
    source: Source
    contact_id: uuid.UUID | None = None
    phone_e164: str | None = None  # the owner typed a number that may not be a customer yet
    customer_name: str | None = None
    due_date: date | None = None
    created_by: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    call_id: uuid.UUID | None = None
    client_ref: str | None = None
    discount_percent: int = 0


async def _business(session: AsyncSession, business_id: uuid.UUID) -> Business:
    business = await session.get(Business, business_id)
    if business is None:
        raise not_found("Business")
    return business


async def _contact(session: AsyncSession, business_id: uuid.UUID, new: NewRequest) -> Contact:
    if new.contact_id is not None:
        contact = await session.scalar(
            select(Contact).where(Contact.business_id == business_id, Contact.id == new.contact_id)
        )
        if contact is None:
            raise not_found("Customer")
        return contact
    if new.phone_e164:
        from mitra_core.calls.service import upsert_contact

        contact = await upsert_contact(session, business_id, new.phone_e164)
        if new.customer_name and not contact.name:
            contact.name = new.customer_name.strip()[:120]
        return contact
    raise AppError(422, "customer_required", "Choose a customer or enter a phone number")


async def create_request(
    session: AsyncSession, business_id: uuid.UUID, new: NewRequest, *, now: datetime
) -> PaymentRequest:
    """Create (and usually send) one payment request. Idempotent by ``client_ref``."""
    if not 100 <= new.amount_paise <= 100_000_000:
        raise AppError(422, "invalid_amount", "Amount must be between ₹1 and ₹10,00,000")
    if not 0 <= new.discount_percent <= 100:
        raise AppError(422, "invalid_discount", "Discount must be 0-100%")
    purpose = " ".join(new.purpose.split())[:200]
    if not purpose:
        raise AppError(422, "purpose_required", "Say what the payment is for")
    if new.client_ref:
        existing = await session.scalar(
            select(PaymentRequest).where(
                PaymentRequest.business_id == business_id,
                PaymentRequest.client_ref == new.client_ref,
            )
        )
        if existing is not None:
            return existing
    settings = await get_settings_row(session, business_id)
    if settings.mode == "none":
        raise AppError(409, "collections_not_connected", "Set up how you collect payments first")
    contact = await _contact(session, business_id, new)
    req = PaymentRequest(
        id=uuid.uuid4(),
        business_id=business_id,
        contact_id=contact.id,
        customer_name=(new.customer_name or contact.name or "").strip()[:120] or None,
        phone_last4=contact.phone_last4,
        amount_paise=new.amount_paise,
        purpose=purpose,
        due_date=new.due_date,
        status="awaiting_approval",
        mode=settings.mode,
        source=new.source,
        client_ref=new.client_ref,
        created_by=new.created_by,
        employee_id=new.employee_id,
        call_id=new.call_id,
        discount_percent=new.discount_percent,
        reminders={},
    )
    session.add(req)
    await session.flush()
    if new.source == "employee" and await _ask_first(session, req):
        return req
    await issue(session, req, settings, now=now)
    return req


async def _ask_first(session: AsyncSession, req: PaymentRequest) -> bool:
    """Request owner approval when the rules say so; True when the request now waits."""
    from mitra_core.approvals import needs_approval, request_approval

    # One approval kind for every link; a discount is judged by the owner's discount rule.
    discounted = req.discount_percent > 0 and await needs_approval(
        session, req.business_id, "discount", amount=req.discount_percent
    )
    if not discounted and not await needs_approval(
        session, req.business_id, APPROVAL_KIND, amount=req.amount_paise / 100
    ):
        return False
    who = req.customer_name or (f"…{req.phone_last4}" if req.phone_last4 else "a customer")
    off = f" ({req.discount_percent}% off)" if req.discount_percent else ""
    approval = await request_approval(
        session,
        req.business_id,
        kind=APPROVAL_KIND,
        summary=f"Send {who} a payment link: {messages.rupees(req.amount_paise)}{off} "
        f"for {req.purpose}",
        payload={
            "payment_request_id": str(req.id),
            "amount_paise": req.amount_paise,
            "discount_percent": req.discount_percent,
            "purpose": req.purpose,
            "customer": who,
        },
        requested_by=f"employee:{req.employee_id}" if req.employee_id else "employee",
    )
    req.approval_id = approval.id
    return True


async def issue(
    session: AsyncSession,
    req: PaymentRequest,
    settings: CollectionSettings | None = None,
    *,
    now: datetime,
) -> None:
    """Create the link (Razorpay or UPI intent) and WhatsApp it. Status becomes ``sent``."""
    settings = settings or await get_settings_row(session, req.business_id)
    business = await _business(session, req.business_id)
    req.expires_at = now + timedelta(days=settings.link_expiry_days)
    if req.mode == "razorpay":
        razorpay = razorpay_for(settings)
        link = await razorpay.provider.create_link(
            amount_paise=req.amount_paise,
            description=req.purpose,
            reference_id=str(req.id),
            customer_name=req.customer_name,
            expire_by=int(req.expires_at.timestamp()),
            notes={"mitra_request_id": str(req.id)},
        )
        req.provider, req.provider_link_id, req.short_url = (
            razorpay.provider.name,
            link.link_id,
            link.short_url,
        )
    else:
        if not settings.upi_vpa:
            raise AppError(409, "collections_not_connected", "Add your UPI ID first")
        req.short_url = messages.upi_uri(
            vpa=settings.upi_vpa,
            payee=settings.payee_name or business.name,
            amount_paise=req.amount_paise,
            note=req.purpose,
            ref=req.id.hex[:20],
        )
    req.status = "sent"
    req.sent_at = now
    req.remind_at = reminders.next_step_at(
        req, reminders_enabled=settings.reminders_enabled, tz=business.timezone
    )
    await deliver(session, req, "link", settings=settings, dedupe_key=f"payment:{req.id}:link")


async def deliver(
    session: AsyncSession,
    req: PaymentRequest,
    key: str,
    *,
    settings: CollectionSettings | None = None,
    dedupe_key: str | None = None,
    due: date | None = None,
) -> bool:
    """WhatsApp one of the customer texts (link / reminder / expiry / thanks).

    ``due``: the date the text names (defaults to the due date for the link). False if not
    delivered.
    """
    from mitra_core.phones import reveal_phone
    from mitra_core.whatsapp import deliver as wa_deliver
    from mitra_core.whatsapp import send_customer_message

    if req.contact_id is None:
        req.send_error = "no_customer"
        return False
    phone = await reveal_phone(
        session, req.business_id, req.contact_id, purpose=f"payment_{key}", actor="payments"
    )
    if phone is None:
        req.send_error = "no_phone"
        return False
    settings = settings or await get_settings_row(session, req.business_id)
    business = await _business(session, req.business_id)
    language = await session.scalar(select(Contact.language).where(Contact.id == req.contact_id))
    text = messages.render(
        key,
        messages.lang_of(language),
        name=req.customer_name,
        business=business.name,
        amount_paise=req.amount_paise,
        purpose=req.purpose,
        link=req.short_url or "",
        vpa=settings.upi_vpa if req.mode == "upi" else None,
        due=due or (req.due_date if key == "link" else None),
    )
    ref: dict[str, Any] = {"kind": f"payment_{key}", "payment_request_id": str(req.id)}
    vpa = settings.upi_vpa if req.mode == "upi" else None
    template = _template(req, key, due, vpa)
    if template is None:  # no approved template fits: free text, inside the 24-hour window only
        msg = await wa_deliver(
            session,
            req.business_id,
            to_phone=phone,
            purpose="customer",
            text=text,
            ref=ref,
            dedupe_key=dedupe_key,
        )
    else:
        name, params, suffix, buttons = template
        msg = await send_customer_message(
            session,
            req.business_id,
            to_phone=phone,
            template=name,
            params=params,
            text=text,  # used instead while the customer's 24-hour window is open
            url_suffix=suffix,
            buttons=buttons,
            ref=ref,
            dedupe_key=dedupe_key,
        )
    # None: already sent earlier (dedupe). "blocked" (opted out / window closed) and "failed"
    # were not delivered.
    delivered = msg is None or msg.status == "sent"
    if not delivered and _sms_sender is not None:
        delivered = await _sms_sender(session, req.business_id, phone, text)
    req.send_error = None if delivered else "whatsapp_failed"
    return delivered


RZP_SHORT = "https://rzp.io/"
Template = tuple[str, dict[str, object], str | None, list[tuple[str, str]] | None]


def _link_suffix(req: PaymentRequest) -> str | None:
    """The Pay-now button's ``https://rzp.io/{suffix}`` part (the simulator uses its link id)."""
    if req.short_url and req.short_url.startswith(RZP_SHORT):
        return req.short_url.removeprefix(RZP_SHORT)[:64] or None
    return req.provider_link_id if req.provider == "sim" else None


def _template(
    req: PaymentRequest, key: str, due: date | None = None, vpa: str | None = None
) -> Template | None:
    """Approved template (docs/whatsapp-templates.md) for messages outside the 24-hour window."""
    amount = f"{req.amount_paise // 100:,}"  # the templates already say ₹{{amount}}
    params: dict[str, object] = {"amount": amount, "purpose": req.purpose}
    if key == "thanks":
        return "payment_received", params | {"name": req.customer_name or ""}, None, None
    if vpa:  # UPI-ID mode: no Pay-now button, the template names the UPI ID ("reply PAID")
        upi = {"name": req.customer_name or "", "upi_id": vpa}
        return "payment_upi_request", params | upi, None, None
    suffix = _link_suffix(req)
    if suffix is None:
        return None
    if key in ("reminder", "expiry"):  # an expiry notice names the last day to pay
        day = due or req.due_date
        buttons = [(f"paid:{req.id}", "Already paid")]
        return "payment_reminder", params | {"due": f"{day:%d %b}" if day else ""}, suffix, buttons
    return "payment_link", params | {"name": req.customer_name or ""}, suffix, None


async def mark_paid(
    session: AsyncSession,
    req: PaymentRequest,
    *,
    via: Literal["webhook", "manual"],
    now: datetime,
    payment_id: str | None = None,
) -> bool:
    """Paid: thank the customer, stop reminders, emit ``payment.paid``. False if already paid.

    Accepted from any other status: money that arrived is a fact even on a cancelled link.
    """
    if req.status == "paid":
        return False
    req.status = "paid"
    req.paid_at = now
    req.paid_via = via
    req.provider_payment_id = payment_id
    req.failure_reason = None
    await reminders.stop(session, req, reason="paid")
    await deliver(session, req, "thanks", dedupe_key=f"payment:{req.id}:thanks")
    await _emit(session, req, "payment.paid", now)
    log.info("payments.paid", business_id=str(req.business_id), via=via)
    return True


async def mark_failed(
    session: AsyncSession, req: PaymentRequest, *, reason: str, now: datetime
) -> bool:
    """A payment attempt failed: alert the owner, emit ``payment.failed``, start routines.

    The link stays payable (a later success still marks it paid).
    """
    from mitra_core.manager.alerts import send_alert

    if req.status not in OPEN_STATUSES:
        return False
    first = req.status != "failed"
    req.status = "failed"
    req.failure_reason = reason[:200] or "payment failed"
    await _emit(session, req, "payment.failed", now)
    if first:
        who = req.customer_name or (f"…{req.phone_last4}" if req.phone_last4 else "A customer")
        await send_alert(
            session,
            req.business_id,
            "payment_failed",
            detail=f"{who}: {messages.rupees(req.amount_paise)} for {req.purpose}. "
            f"{req.failure_reason}",
            link="/payments",
            ref={"payment_request_id": str(req.id)},
            dedupe_key=f"payment:{req.id}",
        )
        await reminders.fire(session, req, "payment.failed", now=now)
    return True


async def mark_expired(session: AsyncSession, req: PaymentRequest, *, now: datetime) -> bool:
    if req.status not in (*OPEN_STATUSES, "awaiting_approval"):
        return False
    req.status = "expired"
    await reminders.stop(session, req, reason="expired")
    return True


async def cancel(session: AsyncSession, req: PaymentRequest, *, now: datetime) -> None:
    """The owner withdraws the request: cancel the link, any approval and reminders."""
    from mitra_core.approvals import cancel as cancel_approval

    if req.status not in (*OPEN_STATUSES, "awaiting_approval"):
        raise AppError(409, "not_cancellable", "This payment can no longer be cancelled")
    if req.status == "awaiting_approval" and req.approval_id is not None:
        await cancel_approval(session, req.business_id, req.approval_id, reason="cancelled")
    if req.provider_link_id and req.mode == "razorpay":
        try:
            settings = await get_settings_row(session, req.business_id)
            await razorpay_for(settings).provider.cancel_link(req.provider_link_id)
        except AppError as exc:  # the request still closes; a later payment still counts
            log.warning("payments.cancel_link_failed", code=exc.code)
    req.status = "cancelled"
    req.cancelled_at = now
    await reminders.stop(session, req, reason="cancelled")


async def resend(session: AsyncSession, req: PaymentRequest, *, now: datetime) -> bool:
    if req.status not in OPEN_STATUSES:
        raise AppError(409, "not_open", "Only an unpaid link can be sent again")
    # One resend per minute at most: the dedupe key changes with the minute.
    return await deliver(session, req, "link", dedupe_key=f"payment:{req.id}:{now:%Y%m%d%H%M}")


async def _emit(session: AsyncSession, req: PaymentRequest, event: str, now: datetime) -> None:
    from mitra_core.webhooks.service import emit_event

    await emit_event(session, req.business_id, event, payload(req), now=now)


def payload(req: PaymentRequest) -> dict[str, Any]:
    """Outgoing webhook data: ids, amounts and the last 4 digits only."""
    return {
        "payment_request_id": str(req.id),
        "contact_id": str(req.contact_id) if req.contact_id else None,
        "customer_name": req.customer_name,
        "phone_last4": req.phone_last4,
        "amount_paise": req.amount_paise,
        "currency": "INR",
        "purpose": req.purpose,
        "status": req.status,
        "mode": req.mode,
        "provider_link_id": req.provider_link_id,
        "provider_payment_id": req.provider_payment_id,
        "paid_at": req.paid_at.isoformat() if req.paid_at else None,
        "paid_via": req.paid_via,
        "failure_reason": req.failure_reason,
        "due_date": req.due_date.isoformat() if req.due_date else None,
    }
