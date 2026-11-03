"""Payments (ACT-05/11, INT-08): the business's own collections from its customers.

Owners and managers only, like billing (staff cannot see money). This is not Mitra's wallet:
see ``api.v1.billing`` for that. The Razorpay webhook and the local simulator live in
``api.v1.payments_public``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.config import get_settings
from mitra_core.errors import AppError, not_found
from mitra_core.models import Business, CollectionSettings, PaymentRequest
from mitra_core.models.enums import MemberRole
from mitra_core.payments import (
    approval_handlers,  # noqa: F401  (registers the handler)
    claims,  # noqa: F401  (registers the WhatsApp "Already paid" handler)
    service,
)
from mitra_core.payments import settings as collection
from mitra_core.schemas.payments import (
    CollectionSettingsIn,
    CollectionSettingsOut,
    PaymentList,
    PaymentRequestIn,
    PaymentRequestOut,
    PaymentTotals,
    Status,
)
from mitra_core.security import Tenant, get_tenant_session, require_role

router = APIRouter(prefix="/payments", tags=["payments"])
_money_role = require_role(MemberRole.OWNER, MemberRole.MANAGER)
_owner_only = require_role(MemberRole.OWNER)


def _settings_out(row: CollectionSettings) -> CollectionSettingsOut:
    return CollectionSettingsOut(
        mode=row.mode,  # type: ignore[arg-type]
        razorpay_key_id=collection.masked_key_id(row.razorpay_key_id),
        has_key_secret=bool(row.razorpay_key_secret_sealed),
        has_webhook_secret=bool(row.razorpay_webhook_secret_sealed),
        webhook_url=collection.webhook_url(row),
        upi_vpa=row.upi_vpa,
        payee_name=row.payee_name,
        reminders_enabled=row.reminders_enabled,
        link_expiry_days=row.link_expiry_days,
        is_lender=row.is_lender,
        simulated=get_settings().collections_provider == "sim",
        auto_confirm=row.mode == "razorpay",
    )


@router.get("/settings", response_model=CollectionSettingsOut, summary="How you collect")
async def get_collection_settings(
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
) -> CollectionSettingsOut:
    row = await collection.get_settings_row(session, tenant.business_id)
    await session.commit()
    return _settings_out(row)


@router.put(
    "/settings",
    response_model=CollectionSettingsOut,
    summary="Connect Razorpay, use a UPI ID, or stop (owner only; secrets are write-only)",
)
async def put_collection_settings(
    body: CollectionSettingsIn,
    tenant: Tenant = Depends(_owner_only),
    session: AsyncSession = Depends(get_tenant_session),
) -> CollectionSettingsOut:
    row = await collection.get_settings_row(session, tenant.business_id)
    if body.mode == "razorpay":
        collection.connect_razorpay(
            row,
            # Omitted: keep the connected account (its secrets stay stored).
            key_id=body.razorpay_key_id or row.razorpay_key_id or "",
            key_secret=body.razorpay_key_secret,
            webhook_secret=body.razorpay_webhook_secret,
        )
    elif body.mode == "upi":
        collection.use_upi_id(row, vpa=body.upi_vpa or "", payee_name=body.payee_name)
    else:
        collection.disconnect(row)
    if body.reminders_enabled is not None:
        row.reminders_enabled = body.reminders_enabled
    if body.link_expiry_days is not None:
        row.link_expiry_days = body.link_expiry_days  # applies to links sent from now on
    if body.is_lender is not None:
        row.is_lender = body.is_lender
    await session.flush()
    out = _settings_out(row)
    await session.commit()
    return out


@router.post(
    "/settings/rotate-webhook",
    response_model=CollectionSettingsOut,
    summary="New webhook address (paste it into Razorpay again)",
)
async def rotate_webhook(
    tenant: Tenant = Depends(_owner_only),
    session: AsyncSession = Depends(get_tenant_session),
) -> CollectionSettingsOut:
    row = await collection.get_settings_row(session, tenant.business_id)
    collection.rotate_webhook_token(row)
    await session.flush()
    out = _settings_out(row)
    await session.commit()
    return out


async def _month_start(session: AsyncSession, business_id: uuid.UUID, now: datetime) -> datetime:
    tz = await session.scalar(select(Business.timezone).where(Business.id == business_id))
    local = now.astimezone(ZoneInfo(tz or "Asia/Kolkata"))
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _totals(session: AsyncSession, business_id: uuid.UUID, now: datetime) -> PaymentTotals:
    start = await _month_start(session, business_id, now)
    base = select(func.coalesce(func.sum(PaymentRequest.amount_paise), 0), func.count()).where(
        PaymentRequest.business_id == business_id
    )
    paid_sum, paid_count = (
        await session.execute(
            base.where(PaymentRequest.status == "paid", PaymentRequest.paid_at >= start)
        )
    ).one()
    open_sum, open_count = (
        await session.execute(base.where(PaymentRequest.status.in_(("sent", "failed"))))
    ).one()
    failed = await session.scalar(
        select(func.count()).where(
            PaymentRequest.business_id == business_id, PaymentRequest.status == "failed"
        )
    )
    return PaymentTotals(
        collected_this_month_paise=int(paid_sum),
        paid_this_month=int(paid_count),
        pending_paise=int(open_sum),
        pending_count=int(open_count),
        failed_count=int(failed or 0),
    )


@router.get("", response_model=PaymentList, summary="Payment requests and this month's totals")
async def list_payments(
    status_filter: Status | None = Query(default=None, alias="status"),
    contact_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> PaymentList:
    stmt = select(PaymentRequest).where(PaymentRequest.business_id == tenant.business_id)
    if status_filter is not None:
        stmt = stmt.where(PaymentRequest.status == status_filter)
    if contact_id is not None:
        stmt = stmt.where(PaymentRequest.contact_id == contact_id)
    rows = await session.scalars(stmt.order_by(PaymentRequest.created_at.desc()).limit(limit))
    return PaymentList(
        items=[PaymentRequestOut.model_validate(r) for r in rows],
        totals=await _totals(session, tenant.business_id, clock()),
    )


@router.post(
    "",
    response_model=PaymentRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment link and WhatsApp it to the customer",
)
async def create_payment(
    body: PaymentRequestIn,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> PaymentRequest:
    now = clock()
    if body.due_date is not None and body.due_date < now.date() - timedelta(days=1):
        raise AppError(422, "invalid_due_date", "The due date is in the past")
    req = await service.create_request(
        session,
        tenant.business_id,
        service.NewRequest(
            amount_paise=body.amount_paise,
            purpose=body.purpose,
            source="owner",
            contact_id=body.contact_id,
            phone_e164=body.phone,
            customer_name=body.customer_name,
            due_date=body.due_date,
            created_by=tenant.user.id,
            client_ref=body.client_ref,
        ),
        now=now,
    )
    await session.flush()
    await session.refresh(req)
    await session.commit()
    return req


async def _get(session: AsyncSession, tenant: Tenant, payment_id: uuid.UUID) -> PaymentRequest:
    req = await session.scalar(
        select(PaymentRequest)
        .where(PaymentRequest.id == payment_id, PaymentRequest.business_id == tenant.business_id)
        .with_for_update()
    )
    if req is None:
        raise not_found("Payment")
    return req


@router.get("/{payment_id}", response_model=PaymentRequestOut, summary="One payment request")
async def get_payment(
    payment_id: uuid.UUID,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
) -> PaymentRequest:
    return await _get(session, tenant, payment_id)


Action = Literal["resend", "cancel", "mark-paid"]


@router.post(
    "/{payment_id}/{action}",
    response_model=PaymentRequestOut,
    summary="Send again, cancel, or mark as paid (paid outside the link, or UPI-ID mode)",
)
async def act_on_payment(
    payment_id: uuid.UUID,
    action: Action,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> PaymentRequest:
    req = await _get(session, tenant, payment_id)
    now = clock()
    if action == "resend":
        await service.resend(session, req, now=now)
    elif action == "cancel":
        await service.cancel(session, req, now=now)
    else:
        if req.status not in ("sent", "failed", "expired"):
            raise AppError(409, "not_open", "Only an unpaid request can be marked as paid")
        await service.mark_paid(session, req, via="manual", now=now)
    await session.flush()
    await session.refresh(req)
    await session.commit()
    return req
