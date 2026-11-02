"""Billing operations on the database. Callers bind the tenant and commit.

Every money-moving operation first locks the business's wallet row (``SELECT ... FOR UPDATE``),
which serialises concurrent usage, top-ups and webhooks for one business. Balances on the wallet
row are a cache of the append-only ``wallet_txn`` ledger; ``post_txn`` is the only writer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.billing import rating
from mitra_core.billing.providers import PaymentProvider
from mitra_core.billing.rating import Balances, CallDirection, CallOutcome
from mitra_core.config import Settings
from mitra_core.errors import AppError, not_found
from mitra_core.logging import get_logger
from mitra_core.models import Business, Employee
from mitra_core.models.billing import Invoice, RateCard, TopupOrder, UsageEvent, Wallet, WalletTxn
from mitra_core.models.enums import VoiceTier

log = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
_NEXT_INVOICE = text("SELECT billing_next_invoice_number(:fy)")


def ist_date(moment: datetime) -> date:
    return moment.astimezone(IST).date()


def month_start(moment: datetime) -> date:
    return ist_date(moment).replace(day=1)


def month_start_utc(moment: datetime) -> datetime:
    first = month_start(moment)
    return datetime(first.year, first.month, 1, tzinfo=IST)


def balances(wallet: Wallet) -> Balances:
    return Balances(wallet.balance_paise, wallet.bonus_paise)


# ---------- wallet + ledger ----------


def post_txn(
    session: AsyncSession,
    wallet: Wallet,
    *,
    kind: str,
    paid_delta: int,
    bonus_delta: int,
    ref: str | None,
    description: str,
    now: datetime,
    category: str | None = None,
) -> WalletTxn:
    wallet.balance_paise += paid_delta
    wallet.bonus_paise += bonus_delta
    txn = WalletTxn(
        id=uuid.uuid4(),
        business_id=wallet.business_id,
        kind=kind,
        category=category,
        paid_delta_paise=paid_delta,
        bonus_delta_paise=bonus_delta,
        balance_after_paise=wallet.balance_paise,
        bonus_after_paise=wallet.bonus_paise,
        ref=ref,
        description=description,
        created_at=now,
    )
    session.add(txn)
    return txn


async def lock_wallet(session: AsyncSession, business_id: uuid.UUID, now: datetime) -> Wallet:
    """The business's wallet, locked for update; created (with the trial credit) on first use.

    Also applies lazy housekeeping: month / grace-day rollover and credit expiry.
    """
    created = (
        await session.execute(
            pg_insert(Wallet)
            .values(
                business_id=business_id,
                low_balance_threshold_paise=rating.DEFAULT_LOW_BALANCE_PAISE,
                autopay_amount_paise=1_000_00,
                credits_expire_at=rating.credits_expiry(now),
                usage_month=month_start(now),
            )
            .on_conflict_do_nothing(index_elements=["business_id"])
            .returning(Wallet.business_id)
        )
    ).scalar_one_or_none()
    wallet = await session.scalar(
        select(Wallet)
        .where(Wallet.business_id == business_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if wallet is None:  # pragma: no cover - the insert above guarantees a row
        raise not_found("Wallet")
    if created is not None:
        post_txn(
            session,
            wallet,
            kind="bonus",
            paid_delta=0,
            bonus_delta=rating.TRIAL_CREDIT_PAISE,
            ref="signup_trial",
            description="Welcome credit: 100 free Natural minutes",
            now=now,
        )
    if wallet.usage_month != month_start(now):
        wallet.usage_month = month_start(now)
        wallet.month_usage_paise = 0
    if wallet.grace_day != ist_date(now):
        wallet.grace_day = ist_date(now)
        wallet.grace_seconds_used = 0
    expires = wallet.credits_expire_at
    if expires is not None and now >= expires and (wallet.balance_paise > 0 or wallet.bonus_paise):
        expired = rating.expire(balances(wallet))
        post_txn(
            session,
            wallet,
            kind="expiry",
            paid_delta=expired.paid_delta,
            bonus_delta=expired.bonus_delta,
            ref=f"expiry:{expires.isoformat()}",
            description="Unused credits expired (12 months after the last top-up)",
            now=now,
        )
    return wallet


async def current_rate(session: AsyncSession, tier: VoiceTier, at: datetime) -> int:
    paise = await session.scalar(
        select(RateCard.paise_per_min)
        .where(RateCard.tier == tier, RateCard.channel == "retail", RateCard.effective_from <= at)
        .order_by(RateCard.effective_from.desc())
        .limit(1)
    )
    return paise if paise is not None else rating.TIER_RATE_PAISE[tier]


async def current_rates(session: AsyncSession, at: datetime) -> dict[VoiceTier, int]:
    return {tier: await current_rate(session, tier, at) for tier in VoiceTier}


# ---------- usage ----------


@dataclass(frozen=True, slots=True)
class UsageInput:
    call_id: str
    employee_id: uuid.UUID
    direction: CallDirection
    outcome: CallOutcome
    connected_seconds: float
    started_at: datetime
    request_hash: str


@dataclass(frozen=True, slots=True)
class UsageResult:
    event: UsageEvent
    wallet: Wallet
    status: rating.AccountStatus
    low_balance: bool
    low_balance_alert: bool
    autopay_topup: TopupOrder | None
    replayed: bool


def is_low(wallet: Wallet) -> bool:
    return balances(wallet).available < wallet.low_balance_threshold_paise


def status_of(wallet: Wallet) -> rating.AccountStatus:
    return rating.account_status(
        balances(wallet),
        monthly_cap=wallet.monthly_cap_paise,
        month_usage=wallet.month_usage_paise,
    )


async def record_usage(
    session: AsyncSession,
    business_id: uuid.UUID,
    usage: UsageInput,
    *,
    now: datetime,
    provider: PaymentProvider,
    settings: Settings,
) -> UsageResult:
    wallet = await lock_wallet(session, business_id, now)
    existing = await session.scalar(
        select(UsageEvent).where(
            UsageEvent.business_id == business_id, UsageEvent.call_id == usage.call_id
        )
    )
    if existing is not None:
        if existing.request_hash != usage.request_hash:
            raise AppError(
                409, "usage_conflict", "This call_id was already recorded with different data"
            )
        return UsageResult(
            existing, wallet, status_of(wallet), is_low(wallet), False, None, replayed=True
        )

    employee = await session.scalar(
        select(Employee).where(
            Employee.id == usage.employee_id, Employee.business_id == business_id
        )
    )
    if employee is None:
        raise not_found("Employee")
    rate = await current_rate(session, employee.voice_tier, usage.started_at)
    before = balances(wallet)
    charge = rating.rate_call(
        outcome=usage.outcome,
        direction=usage.direction,
        connected_seconds=usage.connected_seconds,
        rate_paise_per_min=rate,
        balances=before,
        grace_used_today=wallet.grace_seconds_used,
    )
    event = UsageEvent(
        id=uuid.uuid4(),
        business_id=business_id,
        call_id=usage.call_id,
        request_hash=usage.request_hash,
        employee_id=employee.id,
        employee_name=employee.name,
        direction=usage.direction.value,
        outcome=usage.outcome.value,
        connected_ms=round(max(usage.connected_seconds, 0) * 1000),
        billable_seconds=charge.billable_seconds,
        grace_seconds=charge.grace_seconds,
        tier=employee.voice_tier,
        rate_paise_per_min=rate,
        amount_paise=charge.amount_paise,
        started_at=usage.started_at,
        created_at=now,
    )
    session.add(event)
    if charge.amount_paise:
        minutes = f"{charge.billable_seconds // 60}m {charge.billable_seconds % 60:02d}s"
        post_txn(
            session,
            wallet,
            kind="usage",
            paid_delta=charge.debit.paid_delta,
            bonus_delta=charge.debit.bonus_delta,
            ref=str(event.id),
            description=f"{usage.direction.value.title()} call · {employee.name} · {minutes}",
            now=now,
        )
    wallet.month_usage_paise += charge.amount_paise
    wallet.grace_seconds_used += charge.grace_seconds

    alert = (
        rating.low_balance_crossed(
            before.available, balances(wallet).available, wallet.low_balance_threshold_paise
        )
        and not wallet.low_balance_alerted
    )
    autopay = None
    if alert:
        wallet.low_balance_alerted = True
        log.info("billing.low_balance", business_id=str(business_id))
        if wallet.autopay_enabled:
            autopay = await create_topup(
                session,
                wallet,
                amount_paise=wallet.autopay_amount_paise,
                source="autopay",
                user_id=None,
                provider=provider,
                settings=settings,
                now=now,
            )
    await session.flush()
    return UsageResult(event, wallet, status_of(wallet), is_low(wallet), alert, autopay, False)


# ---------- top-ups + invoices ----------


async def create_topup(
    session: AsyncSession,
    wallet: Wallet,
    *,
    amount_paise: int,
    source: str,
    user_id: uuid.UUID | None,
    provider: PaymentProvider,
    settings: Settings,
    now: datetime,
) -> TopupOrder:
    try:
        rating.validate_topup(amount_paise)
    except rating.TopupError as exc:
        raise AppError(422, "invalid_topup", str(exc)) from exc
    tax = rating.gst(amount_paise, intra_state=_intra_state(wallet, settings))
    topup_id = uuid.uuid4()
    provider_order = await provider.create_order(
        amount_paise=amount_paise + tax.total,
        receipt=str(topup_id),
        notes={"business_id": str(wallet.business_id), "source": source},
    )
    order = TopupOrder(
        id=topup_id,
        business_id=wallet.business_id,
        provider=provider.name,
        provider_order_id=provider_order.order_id,
        status="created",
        source=source,
        amount_paise=amount_paise,
        bonus_paise=rating.bonus_for_topup(amount_paise),
        gst_paise=tax.total,
        total_paise=amount_paise + tax.total,
        created_by=user_id,
    )
    session.add(order)
    await session.flush()
    if provider_order.status == "paid":
        await mark_paid(
            session, order, wallet, payment_id=provider_order.payment_id, settings=settings, now=now
        )
    return order


def _intra_state(wallet: Wallet, settings: Settings) -> bool:
    # Unknown buyer state: place of supply defaults to the supplier's location.
    return (wallet.state_code or settings.billing_supplier_state_code) == (
        settings.billing_supplier_state_code
    )


async def mark_paid(
    session: AsyncSession,
    order: TopupOrder,
    wallet: Wallet,
    *,
    payment_id: str | None,
    settings: Settings,
    now: datetime,
) -> bool:
    """Credit a top-up exactly once. Returns False if it was already paid."""
    if order.status == "paid":
        return False
    order.status = "paid"
    order.provider_payment_id = payment_id
    order.paid_at = now
    rupees = order.amount_paise // 100
    post_txn(
        session,
        wallet,
        kind="topup",
        paid_delta=order.amount_paise,
        bonus_delta=0,
        ref=str(order.id),
        description=f"Top-up ₹{rupees:,}" + (" (auto top-up)" if order.source == "autopay" else ""),
        now=now,
    )
    if order.bonus_paise:
        post_txn(
            session,
            wallet,
            kind="bonus",
            paid_delta=0,
            bonus_delta=order.bonus_paise,
            ref=str(order.id),
            description=f"Top-up bonus +{rating.bonus_pct(order.amount_paise)}%",
            now=now,
        )
    wallet.credits_expire_at = rating.credits_expiry(now)
    if not is_low(wallet):
        wallet.low_balance_alerted = False
    await _issue_invoice(session, order, wallet, settings=settings, now=now)
    await session.flush()
    return True


async def _issue_invoice(
    session: AsyncSession, order: TopupOrder, wallet: Wallet, *, settings: Settings, now: datetime
) -> Invoice:
    fy = rating.financial_year(ist_date(now))
    sequence = (await session.execute(_NEXT_INVOICE, {"fy": fy})).scalar_one()
    business = await session.get(Business, wallet.business_id)
    intra = _intra_state(wallet, settings)
    tax = rating.gst(order.amount_paise, intra_state=intra)
    invoice = Invoice(
        id=uuid.uuid4(),
        business_id=wallet.business_id,
        topup_id=order.id,
        number=rating.invoice_number(fy, sequence),
        issued_at=now,
        billing_name=wallet.billing_name or (business.name if business else "Customer"),
        gstin=wallet.gstin,
        place_of_supply=wallet.state_code or settings.billing_supplier_state_code,
        intra_state=intra,
        description="Prepaid AI calling credits (talk-time wallet)",
        taxable_paise=order.amount_paise,
        cgst_paise=tax.cgst,
        sgst_paise=tax.sgst,
        igst_paise=tax.igst,
        total_paise=order.amount_paise + tax.total,
    )
    session.add(invoice)
    return invoice


# ---------- pass-through extras ----------


async def post_passthrough(
    session: AsyncSession,
    wallet: Wallet,
    *,
    category: str,
    amount_paise: int,
    ref: str,
    description: str,
    now: datetime,
) -> tuple[WalletTxn, bool]:
    """Charge an at-cost extra once per ``ref``. Returns (ledger line, created)."""
    existing = await session.scalar(
        select(WalletTxn).where(
            WalletTxn.business_id == wallet.business_id,
            WalletTxn.kind == "passthrough",
            WalletTxn.ref == ref,
        )
    )
    if existing is not None:
        return existing, False
    paid = rating.debit(balances(wallet), amount_paise)
    txn = post_txn(
        session,
        wallet,
        kind="passthrough",
        category=category,
        paid_delta=paid.paid_delta,
        bonus_delta=paid.bonus_delta,
        ref=ref,
        description=description,
        now=now,
    )
    await session.flush()
    return txn, True


async def usage_in_month(session: AsyncSession, business_id: uuid.UUID, first: date) -> int:
    start = datetime(first.year, first.month, 1, tzinfo=IST)
    end = rating.add_months(start, 1)
    total = await session.scalar(
        select(func.coalesce(func.sum(UsageEvent.amount_paise), 0)).where(
            UsageEvent.business_id == business_id,
            UsageEvent.created_at >= start,
            UsageEvent.created_at < end,
        )
    )
    return int(total or 0)


async def extras_since(session: AsyncSession, business_id: uuid.UUID, since: datetime) -> int:
    total = await session.scalar(
        select(
            func.coalesce(func.sum(-(WalletTxn.paid_delta_paise + WalletTxn.bonus_delta_paise)), 0)
        ).where(
            WalletTxn.business_id == business_id,
            WalletTxn.kind == "passthrough",
            WalletTxn.created_at >= since,
        )
    )
    return int(total or 0)
