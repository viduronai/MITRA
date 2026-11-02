"""``compliance.check(contact, purpose, time, number)``: hard rules, in code (08 section 3).

Pure and synchronous: :func:`evaluate` gets every fact it needs already loaded (consents,
opt-outs, DND status, recent attempts, the business's numbers) and returns a decision with
reasons. ``telephony.service`` loads those facts from the database and logs the result.

Order: every BLOCK rule is evaluated first (consent, opt-out, DND, DLT, caller ID); only a call
that passes all of them can be DEFERRED (calling hours, frequency caps) or ALLOWED.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mitra_core.telephony.enums import (
    CallPurpose,
    ConsentScope,
    Decision,
    DndStatus,
    KycStatus,
    NumberHealth,
    NumberType,
    VerificationStatus,
)

DEFAULT_TIMEZONE = "Asia/Kolkata"

# Plain-language reasons shown to the owner ("18 people skipped: on Do-Not-Disturb list").
REASON_TEXT: dict[str, str] = {
    "no_consent": "no consent on record for this kind of call",
    "opted_out": "asked not to be called",
    "dnd_registered": "on Do-Not-Disturb list",
    "dnd_unknown": "Do-Not-Disturb status could not be checked",
    "promotional_disabled": "promotional calling is off",
    "dlt_template_missing": "script is not registered on DLT",
    "no_caller_id": "no verified number for this kind of call",
    "number_paused": "your calling number is paused for its health",
    "outside_hours": "outside allowed calling hours",
    "daily_cap": "already called 3 times today",
    "weekly_cap": "already called 7 times this week",
    "wallet_zero_balance": "your Mitra balance is used up",
    "wallet_spend_cap": "your monthly spending limit is reached",
}

_LOCAL_TYPES = (NumberType.BYO_SIP, NumberType.LOCAL, NumberType.MOBILE_VIRTUAL)
_MANDATED_TYPES = (NumberType.SERIES_1601, NumberType.SERIES_1600)


@dataclass(frozen=True, slots=True)
class CallingRules:
    """Defaults per 08 section 3 (hours are conservative; legal confirms before outbound GA)."""

    service_window: tuple[time, time] = (time(9, 0), time(21, 0))
    promotional_window: tuple[time, time] = (time(10, 0), time(19, 0))
    max_per_day: int = 3
    max_per_week: int = 7


DEFAULT_RULES = CallingRules()


@dataclass(frozen=True, slots=True)
class NumberInfo:
    id: uuid.UUID
    e164: str | None
    type: NumberType
    kyc_status: KycStatus
    health: NumberHealth
    outbound_enabled: bool = True
    truecaller_status: VerificationStatus = VerificationStatus.NOT_STARTED
    cnap_status: VerificationStatus = VerificationStatus.NOT_STARTED

    @property
    def live(self) -> bool:
        return self.kyc_status == KycStatus.APPROVED and bool(self.e164) and self.outbound_enabled

    @property
    def usable(self) -> bool:
        return self.live and self.health != NumberHealth.PAUSED

    @property
    def trust(self) -> int:
        """Higher = more likely to be answered (verified name shown on the customer's phone)."""
        return sum(
            s == VerificationStatus.VERIFIED for s in (self.truecaller_status, self.cnap_status)
        )


@dataclass(frozen=True, slots=True)
class ComplianceFacts:
    purpose: CallPurpose
    now: datetime  # timezone-aware
    consents: frozenset[ConsentScope] = frozenset()
    opted_out_all: bool = False
    opted_out_purposes: frozenset[CallPurpose] = frozenset()
    dnd: DndStatus | None = None  # only looked up for promotional calls
    attempts: Sequence[datetime] = ()  # this contact's attempts in the last 7 days
    numbers: Sequence[NumberInfo] = ()
    called_number_id: uuid.UUID | None = None  # callback: the number the customer called
    requested_number_id: uuid.UUID | None = None
    timezone: str = DEFAULT_TIMEZONE
    promotional_enabled: bool = False
    dlt_enforced: bool = False
    dlt_template_id: str | None = None
    sector_mandated: bool = False  # BFSI / utilities / logistics: service calls via 1600/1601
    wallet_pause: str | None = None  # billing PauseReason value: outbound is paused until top-up
    rules: CallingRules = DEFAULT_RULES


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ComplianceResult:
    decision: Decision
    reasons: list[Reason] = field(default_factory=list)
    caller: NumberInfo | None = None
    defer_until: datetime | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW


def _reason(code: str) -> Reason:
    return Reason(code, REASON_TEXT[code])


def _best(numbers: Sequence[NumberInfo], types: Sequence[NumberType]) -> NumberInfo | None:
    """Most trusted usable number of the given types (types listed in preference order)."""
    candidates = [n for n in numbers if n.type in types and n.usable]
    if not candidates:
        return None
    return max(candidates, key=lambda n: (n.trust, -types.index(n.type)))


def select_caller_id(facts: ComplianceFacts) -> tuple[NumberInfo | None, str | None]:
    """Caller ID per 08 section 8.1 / WORKFLOWS 11b. Returns (number, block reason code)."""
    numbers = facts.numbers
    by_id = {n.id: n for n in numbers}
    purpose = facts.purpose

    if purpose == CallPurpose.PROMOTIONAL:
        if not facts.promotional_enabled:
            return None, "promotional_disabled"
        types: Sequence[NumberType] = (NumberType.SERIES_140,)
    elif purpose == CallPurpose.MANDATED_SERVICE or facts.sector_mandated:
        types = _MANDATED_TYPES
    else:
        types = _LOCAL_TYPES
        if purpose == CallPurpose.CALLBACK and facts.called_number_id:
            called = by_id.get(facts.called_number_id)
            if called is not None and called.usable:
                return called, None  # same number the customer called

    requested = by_id.get(facts.requested_number_id) if facts.requested_number_id else None
    if requested is not None and requested.type in types and requested.usable:
        return requested, None
    best = _best(numbers, types)
    if best is not None:
        return best, None
    # The monitor also switches outbound off when it pauses a number: still report "paused".
    paused = any(
        n.type in types and n.kyc_status == KycStatus.APPROVED and n.health == NumberHealth.PAUSED
        for n in numbers
    )
    return None, "number_paused" if paused else "no_caller_id"


def _window(facts: ComplianceFacts) -> tuple[time, time]:
    if facts.purpose == CallPurpose.PROMOTIONAL:
        return facts.rules.promotional_window
    return facts.rules.service_window


def next_window_start(local_now: datetime, window: tuple[time, time]) -> datetime:
    """The next moment calls are allowed (``local_now`` itself if inside the window)."""
    start, end = window
    if start <= local_now.time() < end:
        return local_now
    day = local_now.date() if local_now.time() < start else local_now.date() + timedelta(days=1)
    return datetime.combine(day, start, tzinfo=local_now.tzinfo)


def _frequency_defer(
    facts: ComplianceFacts, local_now: datetime, tz: ZoneInfo
) -> tuple[list[Reason], datetime | None]:
    rules = facts.rules
    week_ago = facts.now - timedelta(days=7)
    recent = sorted(a for a in facts.attempts if a > week_ago)
    reasons: list[Reason] = []
    until: datetime | None = None
    today = [a for a in recent if a.astimezone(tz).date() == local_now.date()]
    if len(today) >= rules.max_per_day:
        reasons.append(_reason("daily_cap"))
        tomorrow = datetime.combine(local_now.date() + timedelta(days=1), time(0), tzinfo=tz)
        until = tomorrow
    if len(recent) >= rules.max_per_week:
        reasons.append(_reason("weekly_cap"))
        # The oldest attempt that keeps the count at the cap must age out of the 7-day window.
        frees_at = recent[len(recent) - rules.max_per_week] + timedelta(days=7)
        until = max(until, frees_at) if until else frees_at
    return reasons, until


def evaluate(facts: ComplianceFacts) -> ComplianceResult:
    if facts.now.tzinfo is None:
        raise ValueError("facts.now must be timezone-aware")
    purpose = facts.purpose
    blocks: list[Reason] = []

    # 1. Consent for this purpose (service consent covers callbacks and mandated service).
    needed = (
        ConsentScope.PROMOTIONAL if purpose == CallPurpose.PROMOTIONAL else ConsentScope.SERVICE
    )
    if needed not in facts.consents:
        blocks.append(_reason("no_consent"))
    # 2. Opt-out: global per business, or for this purpose.
    if facts.opted_out_all or purpose in facts.opted_out_purposes:
        blocks.append(_reason("opted_out"))
    if purpose == CallPurpose.PROMOTIONAL:
        # 3. DND/NCPR for promotional calls; an unknown status fails closed.
        if facts.dnd == DndStatus.REGISTERED:
            blocks.append(_reason("dnd_registered"))
        elif facts.dnd != DndStatus.NOT_REGISTERED:
            blocks.append(_reason("dnd_unknown"))
        # 7. DLT template mapping, once enforced.
        if facts.dlt_enforced and not facts.dlt_template_id:
            blocks.append(_reason("dlt_template_missing"))
    # 5. Caller ID for the purpose.
    caller, caller_block = select_caller_id(facts)
    if caller_block:
        blocks.append(_reason(caller_block))
    # 8. Wallet: no outbound dialling at zero balance or past the monthly spending cap.
    if facts.wallet_pause:
        blocks.append(_reason(f"wallet_{facts.wallet_pause}"))
    if blocks:
        return ComplianceResult(Decision.BLOCK, blocks)

    # 4. Allowed hours in the contact's timezone, 6. frequency caps -> defer.
    tz = ZoneInfo(facts.timezone)
    local_now = facts.now.astimezone(tz)
    window = _window(facts)
    defers, until = _frequency_defer(facts, local_now, tz)
    earliest = max(local_now, until.astimezone(tz)) if until else local_now
    start = next_window_start(earliest, window)  # a deferred call still lands inside the window
    if start > local_now and not defers:
        defers.append(_reason("outside_hours"))
    if defers:
        return ComplianceResult(
            Decision.DEFER, defers, caller=caller, defer_until=start.astimezone(UTC)
        )
    return ComplianceResult(Decision.ALLOW, [], caller=caller)


def owner_summary(reason_counts: dict[str, int]) -> list[str]:
    """``{"dnd_registered": 18}`` -> ``["18 people skipped: on Do-Not-Disturb list"]``."""
    lines = []
    for code, count in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        who = "1 person" if count == 1 else f"{count} people"
        verb = "deferred" if code in {"outside_hours", "daily_cap", "weekly_cap"} else "skipped"
        lines.append(f"{who} {verb}: {REASON_TEXT.get(code, code)}")
    return lines
