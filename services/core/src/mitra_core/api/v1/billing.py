"""Billing & minutes (docs/07 §3.8): wallet summary, top-ups, settings, ledger, usage, invoices.

Owners and managers only (staff cannot see money). The Razorpay webhook is unauthenticated but
signature-verified; it finds the tenant through ``billing_topup_business`` (migration
0004_billing) and then works through the normal RLS policies.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import idempotency
from mitra_core.billing import rating, service
from mitra_core.billing.providers import PaymentProvider, get_payment_provider, verify_hmac
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError, not_found
from mitra_core.logging import get_logger
from mitra_core.models.billing import Invoice, TopupOrder, UsageEvent, Wallet, WalletTxn
from mitra_core.models.enums import MemberRole, VoiceTier
from mitra_core.schemas.billing import (
    BillingProfile,
    BillingSettingsIn,
    BillingSummary,
    BonusSlab,
    InvoiceList,
    InvoiceOut,
    InvoiceParty,
    InvoiceSummary,
    NumberRentalInfo,
    TierRate,
    TopupConfirmIn,
    TopupIn,
    TopupOut,
    TopupRules,
    TxnList,
    TxnOut,
    UsageByEmployee,
    UsageDay,
    UsageReport,
)
from mitra_core.security import Tenant, get_tenant_session, require_role
from mitra_core.tenancy import TenantContext, set_tenant

log = get_logger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])

_money_role = require_role(MemberRole.OWNER, MemberRole.MANAGER)
_TOPUP_ENDPOINT = "POST /v1/billing/topups"
_ORDER_LOOKUP = text("SELECT billing_topup_business(:order_id)")
# SAC 998599: other support services (prepaid calling credits). TODO(billing): confirm with CA.
SAC_CODE = "998599"


def summary_of(
    wallet: Wallet, rates: dict[VoiceTier, int], *, month: date, extras: int
) -> BillingSummary:
    month_usage = wallet.month_usage_paise
    bal = service.balances(wallet)
    st = service.status_of(wallet)
    cap = wallet.monthly_cap_paise
    return BillingSummary(
        balance_paise=wallet.balance_paise,
        bonus_paise=wallet.bonus_paise,
        available_paise=bal.available,
        rates=[
            TierRate(tier=t, paise_per_min=p, minutes_left=rating.minutes_left(bal.available, p))
            for t, p in rates.items()
        ],
        month=month,
        month_usage_paise=month_usage,
        month_extras_paise=extras,
        monthly_cap_paise=cap,
        cap_remaining_paise=None if cap is None else max(0, cap - wallet.month_usage_paise),
        outbound_paused=st.outbound_paused,
        pause_reason=st.pause_reason,
        low_balance=service.is_low(wallet),
        low_balance_threshold_paise=wallet.low_balance_threshold_paise,
        autopay_enabled=wallet.autopay_enabled,
        autopay_amount_paise=wallet.autopay_amount_paise,
        credits_expire_at=wallet.credits_expire_at,
        grace_seconds_left_today=max(0, rating.GRACE_SECONDS_PER_DAY - wallet.grace_seconds_used),
        number_rental=NumberRentalInfo(
            fee_paise=rating.NUMBER_RENTAL_PAISE,
            waiver_usage_paise=rating.RENTAL_WAIVER_USAGE_PAISE,
            remaining_to_waive_paise=max(0, rating.RENTAL_WAIVER_USAGE_PAISE - month_usage),
        ),
        topup_rules=TopupRules(
            min_paise=rating.MIN_TOPUP_PAISE,
            max_paise=rating.MAX_TOPUP_PAISE,
            gst_rate_pct=rating.GST_RATE_PCT,
            bonus_slabs=[BonusSlab(min_paise=m, pct=p) for m, p in reversed(rating.BONUS_SLABS)],
        ),
        profile=BillingProfile(
            billing_name=wallet.billing_name, gstin=wallet.gstin, state_code=wallet.state_code
        ),
    )


async def _summary(session: AsyncSession, wallet: Wallet, now: datetime) -> BillingSummary:
    rates = await service.current_rates(session, now)
    extras = await service.extras_since(session, wallet.business_id, service.month_start_utc(now))
    return summary_of(wallet, rates, month=service.month_start(now), extras=extras)


async def _invoice_id(session: AsyncSession, topup_id: uuid.UUID) -> uuid.UUID | None:
    return await session.scalar(select(Invoice.id).where(Invoice.topup_id == topup_id))


async def _topup_out(
    session: AsyncSession, order: TopupOrder, checkout: dict[str, Any] | None = None
) -> TopupOut:
    out = TopupOut.model_validate(order)
    return out.model_copy(
        update={"invoice_id": await _invoice_id(session, order.id), "checkout": checkout}
    )


@router.get("/summary", response_model=BillingSummary, summary="Wallet, minutes left, cap")
async def get_summary(
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> BillingSummary:
    now = clock()
    wallet = await service.lock_wallet(session, tenant.business_id, now)
    result = await _summary(session, wallet, now)
    await session.commit()
    return result


@router.patch("/settings", response_model=BillingSummary, summary="Spend cap, auto top-up, GST")
async def update_settings(
    body: BillingSettingsIn,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> BillingSummary:
    now = clock()
    wallet = await service.lock_wallet(session, tenant.business_id, now)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("gstin") and "state_code" not in changes:
        changes["state_code"] = changes["gstin"][:2]  # a GSTIN starts with the state code
    for field, value in changes.items():
        setattr(wallet, field, value)
    if not service.is_low(wallet):
        wallet.low_balance_alerted = False
    await session.flush()
    result = await _summary(session, wallet, now)
    await session.commit()
    return result


@router.post(
    "/topups",
    status_code=status.HTTP_201_CREATED,
    response_model=TopupOut,
    summary="Start a top-up (mock: paid at once; Razorpay: returns checkout details)",
)
async def create_topup(
    body: TopupIn,
    idempotency_key: idempotency.IdempotencyKey = None,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
    provider: PaymentProvider = Depends(get_payment_provider),
    settings: Settings = Depends(get_settings),
) -> TopupOut | JSONResponse:
    req_hash, replayed = await idempotency.lookup_for_business(
        session,
        business_id=tenant.business_id,
        endpoint=_TOPUP_ENDPOINT,
        key=idempotency_key,
        payload=body.model_dump(mode="json"),
    )
    if replayed is not None:
        return replayed
    now = clock()
    wallet = await service.lock_wallet(session, tenant.business_id, now)
    order = await service.create_topup(
        session,
        wallet,
        amount_paise=body.amount_paise,
        source="manual",
        user_id=tenant.user.id,
        provider=provider,
        settings=settings,
        now=now,
    )
    checkout = None
    if order.status == "created":
        checkout = {
            "provider": order.provider,
            "key_id": settings.razorpay_key_id,
            "order_id": order.provider_order_id,
            "amount": order.total_paise,
            "currency": "INR",
        }
    result = await _topup_out(session, order, checkout)
    if idempotency_key:
        idempotency.save(
            session,
            business_id=tenant.business_id,
            user_id=tenant.user.id,
            endpoint=_TOPUP_ENDPOINT,
            key=idempotency_key,
            req_hash=req_hash,
            status=status.HTTP_201_CREATED,
            body=result.model_dump(mode="json"),
        )
    await session.commit()
    return result


@router.post(
    "/topups/{topup_id}/confirm",
    response_model=TopupOut,
    summary="Confirm a Razorpay Checkout payment (signature-verified, idempotent)",
)
async def confirm_topup(
    topup_id: uuid.UUID,
    body: TopupConfirmIn,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
    provider: PaymentProvider = Depends(get_payment_provider),
    settings: Settings = Depends(get_settings),
) -> TopupOut:
    now = clock()
    wallet = await service.lock_wallet(session, tenant.business_id, now)
    order = await session.scalar(
        select(TopupOrder)
        .where(TopupOrder.id == topup_id, TopupOrder.business_id == tenant.business_id)
        .with_for_update()
    )
    if order is None:
        raise not_found("Top-up")
    if order.status != "paid":
        if not provider.verify_payment(order.provider_order_id, body.payment_id, body.signature):
            raise AppError(400, "invalid_signature", "Payment signature could not be verified")
        await service.mark_paid(
            session, order, wallet, payment_id=body.payment_id, settings=settings, now=now
        )
    result = await _topup_out(session, order)
    await session.commit()
    return result


@router.get("/topups/{topup_id}", response_model=TopupOut, summary="A top-up's status")
async def get_topup(
    topup_id: uuid.UUID,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
) -> TopupOut:
    order = await session.scalar(
        select(TopupOrder).where(
            TopupOrder.id == topup_id, TopupOrder.business_id == tenant.business_id
        )
    )
    if order is None:
        raise not_found("Top-up")
    return await _topup_out(session, order)


@router.get("/transactions", response_model=TxnList, summary="Wallet ledger, newest first")
async def list_transactions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
    kind: str | None = Query(None, pattern=r"^(topup|bonus|usage|passthrough|refund|expiry)$"),
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
) -> TxnList:
    stmt = select(WalletTxn).where(WalletTxn.business_id == tenant.business_id)
    if kind:
        stmt = stmt.where(WalletTxn.kind == kind)
    rows = await session.scalars(
        stmt.order_by(WalletTxn.created_at.desc(), WalletTxn.id).limit(limit).offset(offset)
    )
    return TxnList(items=[TxnOut.model_validate(r) for r in rows])


@router.get("/usage", response_model=UsageReport, summary="Usage by day and by employee")
async def usage_report(
    days: int = Query(30, ge=1, le=366),
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    clock: Clock = Depends(get_clock),
) -> UsageReport:
    since = service.ist_date(clock()) - timedelta(days=days - 1)
    start = datetime(since.year, since.month, since.day, tzinfo=service.IST)
    scope = (UsageEvent.business_id == tenant.business_id, UsageEvent.started_at >= start)
    day = func.date(func.timezone("Asia/Kolkata", UsageEvent.started_at)).label("day")
    totals = (
        func.count().label("calls"),
        func.coalesce(func.sum(UsageEvent.billable_seconds), 0).label("secs"),
        func.coalesce(func.sum(UsageEvent.amount_paise), 0).label("amount"),
    )
    by_day = await session.execute(select(day, *totals).where(*scope).group_by(day).order_by(day))
    by_emp = await session.execute(
        select(UsageEvent.employee_id, UsageEvent.employee_name, UsageEvent.tier, *totals)
        .where(*scope)
        .group_by(UsageEvent.employee_id, UsageEvent.employee_name, UsageEvent.tier)
        .order_by(func.sum(UsageEvent.amount_paise).desc())
    )
    return UsageReport(
        since=since,
        by_day=[
            UsageDay(day=r.day, calls=r.calls, billable_seconds=r.secs, amount_paise=r.amount)
            for r in by_day
        ],
        by_employee=[
            UsageByEmployee(
                employee_id=r.employee_id,
                employee_name=r.employee_name,
                tier=r.tier,
                calls=r.calls,
                billable_seconds=r.secs,
                amount_paise=r.amount,
            )
            for r in by_emp
        ],
    )


@router.get("/invoices", response_model=InvoiceList, summary="GST invoices, newest first")
async def list_invoices(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
) -> InvoiceList:
    rows = await session.scalars(
        select(Invoice)
        .where(Invoice.business_id == tenant.business_id)
        .order_by(Invoice.issued_at.desc(), Invoice.id)
        .limit(limit)
        .offset(offset)
    )
    return InvoiceList(items=[InvoiceSummary.model_validate(r) for r in rows])


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut, summary="GST invoice data")
async def get_invoice(
    invoice_id: uuid.UUID,
    tenant: Tenant = Depends(_money_role),
    session: AsyncSession = Depends(get_tenant_session),
    settings: Settings = Depends(get_settings),
) -> InvoiceOut:
    inv = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == tenant.business_id)
    )
    if inv is None:
        raise not_found("Invoice")
    return InvoiceOut(
        id=inv.id,
        number=inv.number,
        issued_at=inv.issued_at,
        supplier=InvoiceParty(
            name=settings.billing_supplier_name,
            gstin=settings.billing_supplier_gstin or None,
            state_code=settings.billing_supplier_state_code,
            address=settings.billing_supplier_address,
        ),
        buyer=InvoiceParty(name=inv.billing_name, gstin=inv.gstin, state_code=inv.place_of_supply),
        place_of_supply=inv.place_of_supply,
        intra_state=inv.intra_state,
        description=inv.description,
        sac_code=SAC_CODE,
        taxable_paise=inv.taxable_paise,
        cgst_paise=inv.cgst_paise,
        sgst_paise=inv.sgst_paise,
        igst_paise=inv.igst_paise,
        total_paise=inv.total_paise,
        gst_rate_pct=rating.GST_RATE_PCT,
    )


# ---------- Razorpay webhook ----------

_PAID_EVENTS = {"payment.captured", "order.paid"}


@router.post(
    "/webhooks/razorpay",
    summary="Razorpay webhook (X-Razorpay-Signature verified, idempotent)",
    include_in_schema=False,
)
async def razorpay_webhook(
    request: Request,
    signature: str = Header("", alias="X-Razorpay-Signature"),
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    secret = settings.razorpay_webhook_secret.get_secret_value()
    if not secret:
        raise AppError(503, "payments_not_configured", "Razorpay webhook secret is not set")
    raw = await request.body()
    if not verify_hmac(secret, raw, signature):
        raise AppError(400, "invalid_signature", "Webhook signature could not be verified")
    try:
        event = json.loads(raw)
        name = str(event.get("event", ""))
        payment = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = str(payment.get("order_id") or "")
        payment_id = str(payment.get("id") or "") or None
        amount = int(payment.get("amount") or 0)
    except (ValueError, AttributeError, TypeError) as exc:
        raise AppError(400, "bad_request", "Malformed webhook payload") from exc
    if not order_id or (name not in _PAID_EVENTS and name != "payment.failed"):
        return {"status": "ignored"}

    business_id = (await session.execute(_ORDER_LOOKUP, {"order_id": order_id})).scalar()
    if business_id is None:
        log.warning("billing.webhook_unknown_order", webhook_event=name)
        return {"status": "ignored"}
    await set_tenant(session, TenantContext(business_id=business_id))
    now = clock()
    wallet = await service.lock_wallet(session, business_id, now)
    order = await session.scalar(
        select(TopupOrder).where(TopupOrder.provider_order_id == order_id).with_for_update()
    )
    if order is None:  # pragma: no cover - the lookup just found it
        return {"status": "ignored"}
    outcome = "duplicate"
    if name in _PAID_EVENTS and order.status != "paid":
        if amount != order.total_paise:
            log.error("billing.webhook_amount_mismatch", topup_id=str(order.id))
            await session.rollback()
            return {"status": "amount_mismatch"}
        await service.mark_paid(
            session, order, wallet, payment_id=payment_id, settings=settings, now=now
        )
        outcome = "credited"
    elif name == "payment.failed" and order.status == "created":
        order.status = "failed"
        outcome = "failed"
    await session.commit()
    return {"status": outcome}
