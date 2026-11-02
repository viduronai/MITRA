"""Rating engine: pure table tests (no database)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from mitra_core.billing import rating
from mitra_core.billing.rating import (
    Balances,
    CallDirection,
    CallOutcome,
    PauseReason,
)
from mitra_core.catalog import RATES
from mitra_core.models.enums import VoiceTier

IN, OUT = CallDirection.INBOUND, CallDirection.OUTBOUND
NATURAL = rating.TIER_RATE_PAISE[VoiceTier.NATURAL]


def test_rates_match_public_catalog() -> None:
    assert {r.tier: round(r.inr_per_min * 100) for r in RATES} == rating.TIER_RATE_PAISE


@pytest.mark.parametrize(
    ("outcome", "seconds", "billable"),
    [
        (CallOutcome.CONNECTED, 0.4, 10),  # minimum 10 s per connected call
        (CallOutcome.CONNECTED, 9, 10),
        (CallOutcome.CONNECTED, 9.999, 10),
        (CallOutcome.CONNECTED, 10, 10),
        (CallOutcome.CONNECTED, 10.001, 11),  # partial seconds round UP
        (CallOutcome.CONNECTED, 60, 60),
        (CallOutcome.CONNECTED, 60.0000001, 60),  # float noise is not a second
        (CallOutcome.CONNECTED, 61, 61),
        (CallOutcome.CONNECTED, 0, 0),
        (CallOutcome.UNANSWERED, 30, 0),
        (CallOutcome.BUSY, 30, 0),
        (CallOutcome.VOICEMAIL, 30, 0),
        (CallOutcome.BLOCKED, 30, 0),
        (CallOutcome.FAILED, 30, 0),
    ],
)
def test_billable_seconds(outcome: CallOutcome, seconds: float, billable: int) -> None:
    assert rating.billable_seconds(outcome, seconds) == billable


@pytest.mark.parametrize(
    ("tier", "seconds", "paise"),
    [
        (VoiceTier.SMART, 10, 50),  # ₹3/min → 5 paise/s
        (VoiceTier.NATURAL, 10, 75),  # ₹4.5/min → 7.5 paise/s
        (VoiceTier.SIGNATURE, 10, 100),
        (VoiceTier.NATURAL, 60, 450),
        (VoiceTier.NATURAL, 61, 458),  # 457.5 rounds half up
        (VoiceTier.NATURAL, 11, 83),  # 82.5 → 83
        (VoiceTier.SMART, 61, 305),
        (VoiceTier.SIGNATURE, 61, 610),
        (VoiceTier.NATURAL, 0, 0),
        (VoiceTier.NATURAL, 3600, 27_000),
    ],
)
def test_charge_paise(tier: VoiceTier, seconds: int, paise: int) -> None:
    assert rating.charge_paise(seconds, rating.TIER_RATE_PAISE[tier]) == paise


def _call(
    seconds: float,
    paid: int,
    bonus: int = 0,
    *,
    direction: CallDirection = OUT,
    outcome: CallOutcome = CallOutcome.CONNECTED,
    grace_used: int = 0,
) -> rating.CallCharge:
    return rating.rate_call(
        outcome=outcome,
        direction=direction,
        connected_seconds=seconds,
        rate_paise_per_min=NATURAL,
        balances=Balances(paid, bonus),
        grace_used_today=grace_used,
    )


def test_unanswered_call_is_free_and_touches_nothing() -> None:
    charge = _call(45, 1000, outcome=CallOutcome.UNANSWERED)
    assert (charge.billable_seconds, charge.amount_paise) == (0, 0)
    assert charge.debit.after == Balances(1000, 0)


@pytest.mark.parametrize(
    ("paid", "bonus", "amount", "after", "paid_delta", "bonus_delta"),
    [
        (1000, 500, 300, Balances(700, 500), -300, 0),  # paid credits first
        (200, 500, 300, Balances(0, 400), -200, -100),  # then bonus
        (0, 500, 300, Balances(0, 200), 0, -300),
        (100, 100, 300, Balances(-100, 0), -200, -100),  # remainder becomes a debt
        (-50, 0, 100, Balances(-150, 0), -100, 0),
        (1000, 0, 0, Balances(1000, 0), 0, 0),
    ],
)
def test_debit_ordering(
    paid: int, bonus: int, amount: int, after: Balances, paid_delta: int, bonus_delta: int
) -> None:
    result = rating.debit(Balances(paid, bonus), amount)
    assert (result.after, result.paid_delta, result.bonus_delta) == (after, paid_delta, bonus_delta)


def test_topup_settles_debt_before_anything_else() -> None:
    assert rating.credit(Balances(-300, 0), 50_000, 0) == Balances(49_700, 0)
    assert Balances(-300, 0).available == 0
    assert Balances(-300, 500).available == 200


def test_outbound_call_overrunning_wallet_goes_negative() -> None:
    charge = _call(120, 300)  # 900 paise due, 300 available
    assert charge.amount_paise == 900
    assert charge.grace_seconds == 0
    assert charge.debit.after == Balances(-600, 0)


def test_inbound_at_zero_balance_uses_free_grace() -> None:
    charge = _call(90, 0, direction=IN)
    assert (charge.billable_seconds, charge.grace_seconds, charge.amount_paise) == (90, 90, 0)
    assert charge.debit.after == Balances(0, 0)


def test_inbound_grace_covers_only_the_unfunded_tail() -> None:
    charge = _call(60, 225, direction=IN)  # wallet funds 30 s
    assert (charge.grace_seconds, charge.amount_paise) == (30, 225)
    assert charge.debit.after == Balances(0, 0)


def test_inbound_grace_rounding_never_creates_debt() -> None:
    charge = _call(61, 400, direction=IN)  # funds 53 s (397.5 p), 8 s grace
    assert charge.grace_seconds == 8
    assert charge.amount_paise == 398
    assert charge.debit.after.paid == 2
    tight = _call(61, 398, direction=IN)  # funds 53 s exactly; 53 s rounds to 398
    assert (tight.grace_seconds, tight.amount_paise, tight.debit.after.paid) == (8, 398, 0)


def test_inbound_grace_exhausted_daily_then_debt() -> None:
    charge = _call(120, 0, direction=IN, grace_used=150)  # 30 s grace left
    assert charge.grace_seconds == 30
    assert charge.amount_paise == rating.charge_paise(90, NATURAL)
    assert charge.debit.after.paid == -675
    none_left = _call(30, 0, direction=IN, grace_used=rating.GRACE_SECONDS_PER_DAY)
    assert none_left.grace_seconds == 0


def test_outbound_never_uses_grace() -> None:
    assert _call(30, 0).grace_seconds == 0


@pytest.mark.parametrize(
    ("paid", "bonus", "cap", "used", "paused", "reason"),
    [
        (1000, 0, None, 0, False, None),
        (0, 1, None, 0, False, None),  # bonus alone keeps outbound running
        (0, 0, None, 0, True, PauseReason.ZERO_BALANCE),
        (-10, 0, None, 0, True, PauseReason.ZERO_BALANCE),
        (1000, 0, 500, 499, False, None),
        (1000, 0, 500, 500, True, PauseReason.SPEND_CAP),
        (1000, 0, 500, 900, True, PauseReason.SPEND_CAP),  # cap reached mid-call
        (1000, 0, 0, 0, True, PauseReason.SPEND_CAP),
    ],
)
def test_account_status(
    paid: int, bonus: int, cap: int | None, used: int, paused: bool, reason: PauseReason | None
) -> None:
    status = rating.account_status(Balances(paid, bonus), monthly_cap=cap, month_usage=used)
    assert (status.outbound_paused, status.pause_reason) == (paused, reason)


def test_cap_reached_mid_call_bills_the_whole_call_then_pauses() -> None:
    # Cap ₹10, ₹9 used; a 60 s call costs ₹4.50 and crosses the cap mid-call.
    charge = _call(60, 10_000)
    assert charge.amount_paise == 450
    status = rating.account_status(charge.debit.after, monthly_cap=1000, month_usage=900 + 450)
    assert status == rating.AccountStatus(True, PauseReason.SPEND_CAP)


def _allow(direction: CallDirection, paid: int, **kw: int | None) -> rating.Allowance:
    args: dict[str, int | None] = {"monthly_cap": None, "month_usage": 0, "grace_used_today": 0}
    args.update(kw)
    return rating.allowance(
        direction,
        Balances(paid, 0),
        rate_paise_per_min=NATURAL,
        monthly_cap=args["monthly_cap"],
        month_usage=args["month_usage"] or 0,
        grace_used_today=args["grace_used_today"] or 0,
    )


def test_allowance() -> None:
    assert _allow(OUT, 4500) == rating.Allowance(True, None, 600)
    assert _allow(OUT, 4500, monthly_cap=1000, month_usage=550) == rating.Allowance(True, None, 60)
    assert _allow(OUT, 4500, monthly_cap=1000, month_usage=1000).reason is PauseReason.SPEND_CAP
    assert _allow(OUT, 0) == rating.Allowance(False, PauseReason.ZERO_BALANCE, 0)
    assert _allow(OUT, 5) == rating.Allowance(False, PauseReason.ZERO_BALANCE, 0)  # < 1 s funded
    # Inbound ignores the cap and adds today's grace.
    assert _allow(IN, 450, monthly_cap=0) == rating.Allowance(True, None, 60 + 180)
    assert _allow(IN, 0, grace_used_today=100) == rating.Allowance(True, None, 80)
    assert _allow(IN, 0, grace_used_today=180) == rating.Allowance(
        False, PauseReason.ZERO_BALANCE, 0
    )


@pytest.mark.parametrize(
    ("before", "after", "crossed"),
    [
        (30_000, 15_000, True),
        (20_000, 19_999, True),
        (19_000, 10_000, False),
        (30_000, 20_000, False),
    ],
)
def test_low_balance_crossing(before: int, after: int, crossed: bool) -> None:
    assert rating.low_balance_crossed(before, after, 20_000) is crossed


@pytest.mark.parametrize(
    ("amount_rupees", "bonus_rupees"),
    [
        (500, 0),
        (9_999, 0),
        (10_000, 500),  # +5%
        (24_999, 1_249.95),
        (25_000, 2_500),  # +10%
        (99_999, 9_999.9),
        (1_00_000, 15_000),  # +15%
        (2_00_000, 30_000),
    ],
)
def test_topup_bonus_slabs(amount_rupees: int, bonus_rupees: float) -> None:
    assert rating.bonus_for_topup(amount_rupees * 100) == round(bonus_rupees * 100)


@pytest.mark.parametrize("amount", [0, 499_99, 500_50, 10_00_000_01])
def test_invalid_topups(amount: int) -> None:
    with pytest.raises(rating.TopupError):
        rating.validate_topup(amount)


def test_valid_topup_bounds() -> None:
    rating.validate_topup(rating.MIN_TOPUP_PAISE)
    rating.validate_topup(rating.MAX_TOPUP_PAISE)


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        (datetime(2026, 10, 20, 9, tzinfo=UTC), datetime(2027, 10, 20, 9, tzinfo=UTC)),
        (datetime(2028, 2, 29, tzinfo=UTC), datetime(2029, 2, 28, tzinfo=UTC)),  # leap day
    ],
)
def test_credit_expiry_twelve_months(start: datetime, expected: datetime) -> None:
    assert rating.credits_expiry(start) == expected
    assert rating.add_months(datetime(2026, 1, 31, tzinfo=UTC), 1).day == 28


def test_expiry_zeroes_credits_but_keeps_debt() -> None:
    assert rating.expire(Balances(1000, 300)).after == Balances(0, 0)
    assert rating.expire(Balances(1000, 300)).paid_delta == -1000
    assert rating.expire(Balances(-200, 0)).after == Balances(-200, 0)


@pytest.mark.parametrize(
    ("usage", "numbers", "amount", "waived"),
    [
        (0, 0, 0, False),
        (0, 1, 49_900, False),
        (2_999_99, 1, 49_900, False),
        (3_000_00, 1, 0, True),  # waiver threshold is inclusive
        (5_000_00, 2, 0, True),
        (1_000_00, 2, 99_800, False),
    ],
)
def test_number_rental_waiver(usage: int, numbers: int, amount: int, waived: bool) -> None:
    assert rating.number_rental(usage, numbers) == rating.RentalCharge(amount, waived)


def test_gst() -> None:
    intra = rating.gst(50_000, intra_state=True)
    assert (intra.cgst, intra.sgst, intra.igst, intra.total) == (4_500, 4_500, 0, 9_000)
    inter = rating.gst(50_000, intra_state=False)
    assert (inter.cgst, inter.sgst, inter.igst) == (0, 0, 9_000)
    odd = rating.gst(50_001, intra_state=True)  # 4500.09 each
    assert (odd.cgst, odd.sgst) == (4_500, 4_500)


@pytest.mark.parametrize(
    ("day", "fy"),
    [(date(2026, 10, 20), "26-27"), (date(2027, 3, 31), "26-27"), (date(2027, 4, 1), "27-28")],
)
def test_financial_year(day: date, fy: str) -> None:
    assert rating.financial_year(day) == fy


def test_invoice_number_fits_gst_limit() -> None:
    number = rating.invoice_number("26-27", 42)
    assert number == "MIT/26-27/000042"
    assert len(number) <= 16


def test_minutes_left() -> None:
    assert rating.minutes_left(45_000, NATURAL) == 100
    assert rating.minutes_left(449, NATURAL) == 0
    assert rating.minutes_left(-100, NATURAL) == 0
