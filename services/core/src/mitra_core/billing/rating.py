"""Pure rating engine: no I/O, no clock, integer paise everywhere (docs/09 §3, docs/04 §11).

Rules implemented here:

* Connected talk-time is billed per second, partial seconds rounded UP, with a minimum of
  ``MIN_BILLABLE_SECONDS`` per connected call. Every other outcome (unanswered, busy,
  voicemail dropped, compliance-blocked, failed) is free.
* Amount = seconds x tier rate / 60, rounded half-up to the paisa.
* Debits consume paid credits first, then bonus credits. Whatever neither covers becomes a
  negative paid balance (the call already happened); the next top-up absorbs it.
* Inbound calls the wallet cannot fund use the daily grace allowance (free) before going
  negative, so a business at zero balance can still take messages.
* Outbound pauses at zero available balance or when this month's usage reaches the cap.
* Credits are valid for ``CREDIT_VALIDITY_MONTHS`` after the most recent top-up.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from mitra_core.models.enums import VoiceTier

# Retail rates, paise per connected minute. Must match the rate_card seed (0004_billing) and
# the public catalog (GET /v1/catalog/rates); a test keeps the three in sync.
TIER_RATE_PAISE: dict[VoiceTier, int] = {
    VoiceTier.SMART: 300,
    VoiceTier.NATURAL: 450,
    VoiceTier.SIGNATURE: 600,
}
# Agency wholesale (docs/09 §3.3). Stored in rate_card; agency billing itself is P3.
AGENCY_RATE_PAISE: dict[VoiceTier, int] = {
    VoiceTier.SMART: 240,
    VoiceTier.NATURAL: 360,
    VoiceTier.SIGNATURE: 480,
}

MIN_BILLABLE_SECONDS = 10
GRACE_SECONDS_PER_DAY = 3 * 60
CREDIT_VALIDITY_MONTHS = 12

MIN_TOPUP_PAISE = 500_00
MAX_TOPUP_PAISE = 10_00_000_00
# (minimum top-up, bonus %), highest first: ₹1,00,000+ 15% · ₹25,000+ 10% · ₹10,000+ 5%.
BONUS_SLABS: tuple[tuple[int, int], ...] = ((1_00_000_00, 15), (25_000_00, 10), (10_000_00, 5))
# 100 free Natural minutes on sign-up.
TRIAL_CREDIT_PAISE = 100 * TIER_RATE_PAISE[VoiceTier.NATURAL]
DEFAULT_LOW_BALANCE_PAISE = 200_00

NUMBER_RENTAL_PAISE = 499_00
RENTAL_WAIVER_USAGE_PAISE = 3_000_00

GST_RATE_PCT = 18


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallOutcome(StrEnum):
    CONNECTED = "connected"
    UNANSWERED = "unanswered"
    BUSY = "busy"
    VOICEMAIL = "voicemail"
    BLOCKED = "blocked"
    FAILED = "failed"


class PauseReason(StrEnum):
    ZERO_BALANCE = "zero_balance"
    SPEND_CAP = "spend_cap"


def _half_up_div(numerator: int, denominator: int) -> int:
    """round(numerator / denominator) with halves rounded up, for non-negative numerators."""
    return (2 * numerator + denominator) // (2 * denominator)


# ---------- per-call charge ----------


def billable_seconds(outcome: CallOutcome, connected_seconds: float) -> int:
    if outcome is not CallOutcome.CONNECTED or connected_seconds <= 0:
        return 0
    millis = round(connected_seconds * 1000)  # drop float noise before rounding up
    return max(MIN_BILLABLE_SECONDS, -(-millis // 1000))


def charge_paise(seconds: int, rate_paise_per_min: int) -> int:
    return _half_up_div(seconds * rate_paise_per_min, 60)


@dataclass(frozen=True, slots=True)
class Balances:
    """``paid`` may be negative (usage the wallet could not cover); ``bonus`` never is."""

    paid: int
    bonus: int

    @property
    def available(self) -> int:
        return max(0, self.paid + self.bonus)


@dataclass(frozen=True, slots=True)
class Debit:
    paid_delta: int
    bonus_delta: int
    after: Balances


def debit(balances: Balances, amount: int) -> Debit:
    """Take ``amount`` from paid credits first, then bonus, then into a negative paid balance."""
    from_paid = min(amount, max(balances.paid, 0))
    from_bonus = min(amount - from_paid, balances.bonus)
    uncovered = amount - from_paid - from_bonus
    paid_delta = -(from_paid + uncovered)
    after = Balances(balances.paid + paid_delta, balances.bonus - from_bonus)
    return Debit(paid_delta, -from_bonus, after)


def credit(balances: Balances, paid: int, bonus: int) -> Balances:
    """A top-up: paid credits first settle any negative balance."""
    return Balances(balances.paid + paid, balances.bonus + bonus)


@dataclass(frozen=True, slots=True)
class CallCharge:
    billable_seconds: int
    grace_seconds: int
    amount_paise: int
    debit: Debit


def rate_call(
    *,
    outcome: CallOutcome,
    direction: CallDirection,
    connected_seconds: float,
    rate_paise_per_min: int,
    balances: Balances,
    grace_used_today: int,
) -> CallCharge:
    billable = billable_seconds(outcome, connected_seconds)
    amount = charge_paise(billable, rate_paise_per_min)
    grace = 0
    available = balances.available
    if direction is CallDirection.INBOUND and amount > available:
        funded = available * 60 // rate_paise_per_min
        unfunded = billable - funded
        grace = min(unfunded, max(0, GRACE_SECONDS_PER_DAY - grace_used_today))
        if grace > 0:
            amount = charge_paise(billable - grace, rate_paise_per_min)
            if grace == unfunded:
                # Grace covered the whole unfunded tail: rounding must not leave a debt.
                amount = min(amount, available)
    return CallCharge(billable, grace, amount, debit(balances, amount))


# ---------- account state ----------


@dataclass(frozen=True, slots=True)
class AccountStatus:
    outbound_paused: bool
    pause_reason: PauseReason | None


def account_status(
    balances: Balances, *, monthly_cap: int | None, month_usage: int
) -> AccountStatus:
    if balances.available <= 0:
        return AccountStatus(True, PauseReason.ZERO_BALANCE)
    if monthly_cap is not None and month_usage >= monthly_cap:
        return AccountStatus(True, PauseReason.SPEND_CAP)
    return AccountStatus(False, None)


@dataclass(frozen=True, slots=True)
class Allowance:
    allowed: bool
    reason: PauseReason | None
    max_seconds: int


def allowance(
    direction: CallDirection,
    balances: Balances,
    *,
    rate_paise_per_min: int,
    monthly_cap: int | None,
    month_usage: int,
    grace_used_today: int,
) -> Allowance:
    """Whether a call may start now and how many seconds the wallet (and cap) can fund."""
    funded = balances.available * 60 // rate_paise_per_min
    if direction is CallDirection.INBOUND:
        # The cap stops outbound only; inbound keeps working, on grace once funds run out.
        total = funded + max(0, GRACE_SECONDS_PER_DAY - grace_used_today)
        reason = None if total > 0 else PauseReason.ZERO_BALANCE
        return Allowance(total > 0, reason, total)
    status = account_status(balances, monthly_cap=monthly_cap, month_usage=month_usage)
    if status.outbound_paused:
        return Allowance(False, status.pause_reason, 0)
    if monthly_cap is not None:
        funded = min(funded, (monthly_cap - month_usage) * 60 // rate_paise_per_min)
    return Allowance(funded > 0, None if funded > 0 else PauseReason.ZERO_BALANCE, funded)


def low_balance_crossed(before: int, after: int, threshold: int) -> bool:
    """True once, when available credit drops below the alert threshold."""
    return before >= threshold > after


def minutes_left(available: int, rate_paise_per_min: int) -> int:
    return max(0, available) // rate_paise_per_min


# ---------- top-ups ----------


class TopupError(ValueError):
    pass


def validate_topup(amount_paise: int) -> None:
    if amount_paise < MIN_TOPUP_PAISE:
        raise TopupError(f"minimum top-up is {MIN_TOPUP_PAISE // 100} rupees")
    if amount_paise > MAX_TOPUP_PAISE:
        raise TopupError(f"maximum top-up is {MAX_TOPUP_PAISE // 100} rupees")
    if amount_paise % 100:
        raise TopupError("top-ups are in whole rupees")


def bonus_pct(amount_paise: int) -> int:
    return next((pct for minimum, pct in BONUS_SLABS if amount_paise >= minimum), 0)


def bonus_for_topup(amount_paise: int) -> int:
    return amount_paise * bonus_pct(amount_paise) // 100


# ---------- expiry ----------


def add_months(moment: datetime, months: int) -> datetime:
    month_index = moment.month - 1 + months
    year, month = moment.year + month_index // 12, month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def credits_expiry(last_topup_at: datetime) -> datetime:
    return add_months(last_topup_at, CREDIT_VALIDITY_MONTHS)


def expire(balances: Balances) -> Debit:
    """Zero out unused credits. A negative balance (money owed) does not expire."""
    paid = max(balances.paid, 0)
    return Debit(-paid, -balances.bonus, Balances(balances.paid - paid, 0))


# ---------- pass-through extras ----------


@dataclass(frozen=True, slots=True)
class RentalCharge:
    amount_paise: int
    waived: bool


def number_rental(month_usage_paise: int, numbers: int) -> RentalCharge:
    """₹499 per dedicated number per month, waived in a month with ≥ ₹3,000 of usage."""
    if numbers <= 0:
        return RentalCharge(0, False)
    if month_usage_paise >= RENTAL_WAIVER_USAGE_PAISE:
        return RentalCharge(0, True)
    return RentalCharge(NUMBER_RENTAL_PAISE * numbers, False)


# ---------- GST ----------


@dataclass(frozen=True, slots=True)
class Tax:
    cgst: int
    sgst: int
    igst: int

    @property
    def total(self) -> int:
        return self.cgst + self.sgst + self.igst


def gst(taxable_paise: int, *, intra_state: bool) -> Tax:
    """18% GST: CGST 9% + SGST 9% within the supplier's state, else IGST 18%."""
    if intra_state:
        half = _half_up_div(taxable_paise * GST_RATE_PCT, 200)
        return Tax(half, half, 0)
    return Tax(0, 0, _half_up_div(taxable_paise * GST_RATE_PCT, 100))


def financial_year(day: date) -> str:
    """Indian financial year (April-March): 2026-10-20 -> '26-27'."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def invoice_number(fy: str, sequence: int) -> str:
    """At most 16 characters, as GST rules require: 'MIT/26-27/000042'."""
    return f"MIT/{fy}/{sequence:06d}"
