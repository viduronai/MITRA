"""Razorpay Payment Links webhooks for a business's own account (auto-matching, ACT-11).

The URL carries the business's random ``webhook_token``; the SECURITY DEFINER
``payments_webhook_business`` maps it to the business, whose own sealed webhook secret then
verifies ``X-Razorpay-Signature`` over the raw body. Each event id is applied once
(``payment_event``); status changes are idempotent on top of that.

Events: ``payment_link.paid`` -> paid; ``payment.failed`` -> failed (owner alert);
``payment_link.expired`` / ``payment_link.cancelled`` -> expired / cancelled. The request is
found by the link id, else by the ``mitra_request_id`` note copied onto the payment.
TODO(razorpay): confirm with real test keys that ``payment.failed`` for a Payment Link carries
that note (or the link id); until then failures may arrive as ``unknown_link``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.billing.providers import hmac_hex, verify_hmac
from mitra_core.errors import AppError
from mitra_core.logging import get_logger
from mitra_core.models import PaymentEvent, PaymentRequest
from mitra_core.payments import reminders, service
from mitra_core.payments.settings import get_settings_row, webhook_secret_for
from mitra_core.tenancy import TenantContext, set_tenant

log = get_logger(__name__)
_LOOKUP = text("SELECT payments_webhook_business(:token)")
HANDLED = ("payment_link.paid", "payment.failed", "payment_link.expired", "payment_link.cancelled")


@dataclass(frozen=True, slots=True)
class Parsed:
    event: str
    link_id: str | None
    request_ref: str | None
    payment_id: str | None
    amount_paise: int | None
    reason: str | None


def _entity(event: dict[str, Any], name: str) -> dict[str, Any]:
    value = (event.get("payload") or {}).get(name) or {}
    entity = value.get("entity") if isinstance(value, dict) else None
    return entity if isinstance(entity, dict) else {}


def parse(raw: bytes) -> Parsed:
    try:
        event = json.loads(raw)
        name = str(event.get("event", ""))
        link = _entity(event, "payment_link")
        payment = _entity(event, "payment")
        notes = payment.get("notes") or link.get("notes") or {}
        ref = notes.get("mitra_request_id") if isinstance(notes, dict) else None
        amount = link.get("amount_paid") if link else None
        if amount is None:
            amount = payment.get("amount")
        reason = payment.get("error_description") or payment.get("error_reason")
        return Parsed(
            event=name,
            link_id=str(link["id"]) if link.get("id") else None,
            request_ref=str(ref) if ref else None,
            payment_id=str(payment["id"]) if payment.get("id") else None,
            amount_paise=int(amount) if amount is not None else None,
            reason=str(reason)[:200] if reason else None,
        )
    except (ValueError, AttributeError, TypeError, KeyError) as exc:
        raise AppError(400, "bad_request", "Malformed webhook payload") from exc


async def _find(
    session: AsyncSession, business_id: uuid.UUID, parsed: Parsed
) -> PaymentRequest | None:
    stmt = select(PaymentRequest).where(PaymentRequest.business_id == business_id)
    if parsed.link_id:
        found = await session.scalar(
            stmt.where(PaymentRequest.provider_link_id == parsed.link_id).with_for_update()
        )
        if found is not None:
            return found
    if parsed.request_ref:
        try:
            ref = uuid.UUID(parsed.request_ref)
        except ValueError:
            return None
        return await session.scalar(stmt.where(PaymentRequest.id == ref).with_for_update())
    return None


async def handle(
    session: AsyncSession,
    *,
    token: str,
    raw: bytes,
    signature: str,
    event_id: str | None,
    now: datetime,
) -> str:
    """Verify and apply one webhook. Returns the outcome; the caller commits."""
    business_id = (await session.execute(_LOOKUP, {"token": token[:64]})).scalar()
    if business_id is None:
        raise AppError(404, "not_found", "Unknown webhook address")
    await set_tenant(session, TenantContext(business_id=business_id))
    settings = await get_settings_row(session, business_id)
    secret = webhook_secret_for(settings)
    if not secret:
        raise AppError(409, "collections_not_connected", "Razorpay is not connected")
    if not verify_hmac(secret, raw, signature):
        raise AppError(400, "invalid_signature", "Webhook signature could not be verified")
    parsed = parse(raw)
    if parsed.event not in HANDLED:
        return "ignored"
    key = (event_id or "").strip()[:80] or "body:" + hashlib.sha256(raw).hexdigest()[:60]
    inserted = await session.scalar(
        insert(PaymentEvent)
        .values(business_id=business_id, event_id=key, event=parsed.event[:40], outcome="received")
        .on_conflict_do_nothing(index_elements=["business_id", "event_id"])
        .returning(PaymentEvent.id)
    )
    if inserted is None:
        return "duplicate"
    req = await _find(session, business_id, parsed)
    outcome = "unknown_link" if req is None else await _apply(session, req, parsed, now)
    row = await session.get(PaymentEvent, inserted)
    if row is not None:
        row.outcome = outcome
        row.payment_request_id = req.id if req else None
    log.info(
        "payments.webhook",
        business_id=str(business_id),
        webhook_event=parsed.event,
        outcome=outcome,
    )
    return outcome


async def _apply(session: AsyncSession, req: PaymentRequest, parsed: Parsed, now: datetime) -> str:
    if parsed.event == "payment_link.paid":
        if parsed.amount_paise is not None and parsed.amount_paise != req.amount_paise:
            log.error("payments.amount_mismatch", payment_request_id=str(req.id))
            return "amount_mismatch"
        changed = await service.mark_paid(
            session, req, via="webhook", now=now, payment_id=parsed.payment_id
        )
        return "paid" if changed else "already_paid"
    if parsed.event == "payment.failed":
        changed = await service.mark_failed(
            session, req, reason=parsed.reason or "Payment failed", now=now
        )
        return "failed" if changed else "ignored"
    if parsed.event == "payment_link.expired":
        return "expired" if await service.mark_expired(session, req, now=now) else "ignored"
    # payment_link.cancelled: someone cancelled it in the Razorpay dashboard.
    if req.status in ("sent", "failed"):
        req.status, req.cancelled_at = "cancelled", now
        await reminders.stop(session, req, reason="cancelled")
        return "cancelled"
    return "ignored"


def simulated_event(
    req: PaymentRequest, outcome: str, *, secret: str, now: datetime
) -> tuple[bytes, str, str]:
    """A Razorpay-shaped webhook for the simulator: (raw body, signature, event id)."""
    pay_id = f"pay_sim_{uuid.uuid4().hex[:14]}"
    notes = {"mitra_request_id": str(req.id)}
    payment: dict[str, Any] = {
        "id": pay_id,
        "amount": req.amount_paise,
        "currency": "INR",
        "method": "upi",
        "notes": notes,
        "status": "captured" if outcome == "pay" else "failed",
    }
    payload: dict[str, Any] = {"payment": {"entity": payment}}
    if outcome == "pay":
        event = "payment_link.paid"
        payload["payment_link"] = {
            "entity": {
                "id": req.provider_link_id,
                "amount": req.amount_paise,
                "amount_paid": req.amount_paise,
                "status": "paid",
                "reference_id": str(req.id),
                "notes": notes,
            }
        }
    else:
        event = "payment.failed"
        payment["error_reason"] = "payment_failed"
        payment["error_description"] = "The UPI app declined the payment (simulated)"
    body = {
        "entity": "event",
        "event": event,
        "contains": list(payload),
        "payload": payload,
        "created_at": int(now.timestamp()),
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    return raw, hmac_hex(secret, raw), f"evt_sim_{uuid.uuid4().hex[:14]}"
