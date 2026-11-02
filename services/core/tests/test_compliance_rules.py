"""compliance.check rules (08 section 3) and caller-ID selection (section 8.1), as tables."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from mitra_core.telephony.compliance import (
    ComplianceFacts,
    NumberInfo,
    evaluate,
    next_window_start,
    owner_summary,
    select_caller_id,
)
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

IST = ZoneInfo("Asia/Kolkata")


def ist(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def number(
    kind: NumberType,
    *,
    e164: str | None = "+914041234567",
    kyc: KycStatus = KycStatus.APPROVED,
    health: NumberHealth = NumberHealth.HEALTHY,
    enabled: bool = True,
    verified: bool = False,
) -> NumberInfo:
    status = VerificationStatus.VERIFIED if verified else VerificationStatus.NOT_STARTED
    return NumberInfo(
        id=uuid.uuid4(),
        e164=e164,
        type=kind,
        kyc_status=kyc,
        health=health,
        outbound_enabled=enabled,
        truecaller_status=status,
        cnap_status=status,
    )


LOCAL = number(NumberType.LOCAL)
SERIES_140 = number(NumberType.SERIES_140, e164="+91140123456")
SERIES_1601 = number(NumberType.SERIES_1601, e164="+911601234567")


def facts(purpose: CallPurpose = CallPurpose.SERVICE, **kw: object) -> ComplianceFacts:
    base = ComplianceFacts(
        purpose=purpose,
        now=ist(20, 11),
        consents=frozenset({ConsentScope.SERVICE}),
        numbers=[LOCAL],
    )
    return dataclasses.replace(base, **kw)  # type: ignore[arg-type]


def codes(result: object) -> list[str]:
    return [r.code for r in result.reasons]  # type: ignore[attr-defined]


# ---- the happy path ---


def test_consented_service_call_in_hours_is_allowed_from_the_local_number() -> None:
    result = evaluate(facts())
    assert result.decision == Decision.ALLOW
    assert result.caller == LOCAL
    assert result.reasons == []


def test_naive_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate(facts(now=datetime(2026, 10, 20, 11, 0)))  # noqa: DTZ001


# ---- 1. consent, 2. opt-out ---


@pytest.mark.parametrize(
    ("purpose", "consents", "decision"),
    [
        (CallPurpose.SERVICE, set(), Decision.BLOCK),
        (CallPurpose.SERVICE, {ConsentScope.PROMOTIONAL}, Decision.BLOCK),
        (CallPurpose.SERVICE, {ConsentScope.SERVICE}, Decision.ALLOW),
        (CallPurpose.CALLBACK, {ConsentScope.SERVICE}, Decision.ALLOW),
        (CallPurpose.CALLBACK, set(), Decision.BLOCK),
    ],
)
def test_consent_must_match_purpose(
    purpose: CallPurpose, consents: set[ConsentScope], decision: Decision
) -> None:
    result = evaluate(facts(purpose, consents=frozenset(consents)))
    assert result.decision == decision
    assert ("no_consent" in codes(result)) == (decision == Decision.BLOCK)


@pytest.mark.parametrize(
    ("opted_all", "opted_purposes", "purpose", "blocked"),
    [
        (True, set(), CallPurpose.SERVICE, True),
        (True, set(), CallPurpose.CALLBACK, True),
        (False, {CallPurpose.SERVICE}, CallPurpose.SERVICE, True),
        (False, {CallPurpose.PROMOTIONAL}, CallPurpose.SERVICE, False),
        (False, set(), CallPurpose.SERVICE, False),
    ],
)
def test_opt_out_global_and_per_purpose(
    opted_all: bool, opted_purposes: set[CallPurpose], purpose: CallPurpose, blocked: bool
) -> None:
    result = evaluate(
        facts(purpose, opted_out_all=opted_all, opted_out_purposes=frozenset(opted_purposes))
    )
    assert ("opted_out" in codes(result)) is blocked
    assert (result.decision == Decision.BLOCK) is blocked


# ---- 3. DND (promotional only), 7. DLT ---


def promo(**kw: object) -> ComplianceFacts:
    base = facts(
        CallPurpose.PROMOTIONAL,
        consents=frozenset({ConsentScope.PROMOTIONAL}),
        numbers=[LOCAL, SERIES_140],
        promotional_enabled=True,
        dnd=DndStatus.NOT_REGISTERED,
    )
    return dataclasses.replace(base, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("dnd", "expected"),
    [
        (DndStatus.NOT_REGISTERED, None),
        (DndStatus.REGISTERED, "dnd_registered"),
        (DndStatus.UNKNOWN, "dnd_unknown"),  # provider down: fail closed
        (None, "dnd_unknown"),
    ],
)
def test_dnd_scrub_for_promotional(dnd: DndStatus | None, expected: str | None) -> None:
    result = evaluate(promo(dnd=dnd))
    if expected is None:
        assert result.decision == Decision.ALLOW
        assert result.caller == SERIES_140
    else:
        assert result.decision == Decision.BLOCK
        assert expected in codes(result)


def test_dnd_is_ignored_for_service_calls() -> None:
    assert evaluate(facts(dnd=DndStatus.REGISTERED)).decision == Decision.ALLOW


def test_dlt_template_required_once_enforced() -> None:
    assert "dlt_template_missing" in codes(evaluate(promo(dlt_enforced=True)))
    assert evaluate(promo(dlt_enforced=True, dlt_template_id="1107160000000012345")).allowed


# ---- 5. purpose -> caller ID (section 8.1) ---


def test_promotional_is_off_by_default() -> None:
    result = evaluate(promo(promotional_enabled=False))
    assert result.decision == Decision.BLOCK
    assert "promotional_disabled" in codes(result)


def test_promotional_never_uses_the_local_number() -> None:
    result = evaluate(promo(numbers=[LOCAL]))
    assert result.decision == Decision.BLOCK
    assert "no_caller_id" in codes(result)


def test_callback_uses_the_number_the_customer_called() -> None:
    other = number(NumberType.LOCAL, e164="+914049999999", verified=True)
    chosen, _ = select_caller_id(
        facts(CallPurpose.CALLBACK, numbers=[other, LOCAL], called_number_id=LOCAL.id)
    )
    assert chosen == LOCAL


def test_callback_falls_back_when_called_number_is_paused() -> None:
    paused = number(NumberType.LOCAL, health=NumberHealth.PAUSED)
    chosen, _ = select_caller_id(
        facts(CallPurpose.CALLBACK, numbers=[paused, LOCAL], called_number_id=paused.id)
    )
    assert chosen == LOCAL


def test_service_prefers_verified_numbers() -> None:
    verified = number(NumberType.MOBILE_VIRTUAL, e164="+919000000001", verified=True)
    chosen, _ = select_caller_id(facts(numbers=[LOCAL, verified]))
    assert chosen == verified


def test_service_honours_a_suitable_requested_number() -> None:
    second = number(NumberType.LOCAL, e164="+914040000002")
    assert select_caller_id(facts(numbers=[LOCAL, second], requested_number_id=second.id))[0] == (
        second
    )
    # A 140 number is never acceptable for a service call, even when requested.
    assert select_caller_id(facts(numbers=[LOCAL, SERIES_140], requested_number_id=SERIES_140.id))[
        0
    ] == (LOCAL)


@pytest.mark.parametrize(
    ("purpose", "numbers", "mandated", "expected", "reason"),
    [
        (CallPurpose.SERVICE, [SERIES_140], False, None, "no_caller_id"),
        (CallPurpose.SERVICE, [SERIES_1601], False, None, "no_caller_id"),
        (CallPurpose.MANDATED_SERVICE, [LOCAL], False, None, "no_caller_id"),
        (CallPurpose.MANDATED_SERVICE, [LOCAL, SERIES_1601], False, SERIES_1601, None),
        (CallPurpose.SERVICE, [LOCAL, SERIES_1601], True, SERIES_1601, None),  # mandated sector
        (CallPurpose.SERVICE, [LOCAL], True, None, "no_caller_id"),
    ],
)
def test_purpose_to_caller_id(
    purpose: CallPurpose,
    numbers: list[NumberInfo],
    mandated: bool,
    expected: NumberInfo | None,
    reason: str | None,
) -> None:
    chosen, block = select_caller_id(facts(purpose, numbers=numbers, sector_mandated=mandated))
    assert chosen == expected
    assert block == reason


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (number(NumberType.LOCAL, health=NumberHealth.PAUSED), "number_paused"),
        (number(NumberType.LOCAL, kyc=KycStatus.PENDING_KYC, e164=None), "no_caller_id"),
        (number(NumberType.LOCAL, kyc=KycStatus.SUBMITTED), "no_caller_id"),
        (number(NumberType.LOCAL, enabled=False), "no_caller_id"),
        (
            number(NumberType.LOCAL, health=NumberHealth.PAUSED, enabled=False),
            "number_paused",
        ),
    ],
)
def test_unusable_numbers_block(candidate: NumberInfo, reason: str) -> None:
    result = evaluate(facts(numbers=[candidate]))
    assert result.decision == Decision.BLOCK
    assert codes(result) == [reason]


def test_watch_numbers_still_call() -> None:
    watch = number(NumberType.LOCAL, health=NumberHealth.WATCH)
    assert evaluate(facts(numbers=[watch])).caller == watch


# ---- 4. calling hours (IST) ---


@pytest.mark.parametrize(
    ("now", "purpose", "decision", "until"),
    [
        (ist(20, 8, 59), CallPurpose.SERVICE, Decision.DEFER, ist(20, 9)),
        (ist(20, 9, 0), CallPurpose.SERVICE, Decision.ALLOW, None),
        (ist(20, 20, 59), CallPurpose.SERVICE, Decision.ALLOW, None),
        (ist(20, 21, 0), CallPurpose.SERVICE, Decision.DEFER, ist(21, 9)),
        (ist(20, 23, 30), CallPurpose.CALLBACK, Decision.DEFER, ist(21, 9)),
        (ist(20, 9, 30), CallPurpose.PROMOTIONAL, Decision.DEFER, ist(20, 10)),
        (ist(20, 18, 59), CallPurpose.PROMOTIONAL, Decision.ALLOW, None),
        (ist(20, 19, 0), CallPurpose.PROMOTIONAL, Decision.DEFER, ist(21, 10)),
    ],
)
def test_calling_hours_in_ist(
    now: datetime, purpose: CallPurpose, decision: Decision, until: datetime | None
) -> None:
    base = promo() if purpose == CallPurpose.PROMOTIONAL else facts(purpose)
    result = evaluate(dataclasses.replace(base, now=now))
    assert result.decision == decision
    assert result.defer_until == (until.astimezone(UTC) if until else None)
    if decision == Decision.DEFER:
        assert codes(result) == ["outside_hours"]
        assert result.caller is not None  # the deferred call keeps its caller ID


def test_hours_use_ist_even_when_now_is_utc() -> None:
    # 02:00 UTC = 07:30 IST: too early.
    result = evaluate(facts(now=datetime(2026, 10, 20, 2, 0, tzinfo=UTC)))
    assert result.decision == Decision.DEFER
    assert result.defer_until == ist(20, 9).astimezone(UTC)


def test_next_window_start() -> None:
    window = (ist(1, 9).time(), ist(1, 21).time())
    assert next_window_start(ist(20, 12), window) == ist(20, 12)
    assert next_window_start(ist(20, 7), window) == ist(20, 9)
    assert next_window_start(ist(20, 22), window) == ist(21, 9)


# ---- 6. frequency caps ---


def test_daily_cap_defers_to_tomorrow_morning() -> None:
    today = [ist(20, 9, 5), ist(20, 9, 40), ist(20, 10, 15)]
    result = evaluate(facts(attempts=today))
    assert result.decision == Decision.DEFER
    assert codes(result) == ["daily_cap"]
    assert result.defer_until == ist(21, 9).astimezone(UTC)


def test_two_calls_today_is_fine() -> None:
    assert evaluate(facts(attempts=[ist(20, 9, 5), ist(20, 9, 40)])).allowed


def test_yesterdays_calls_do_not_count_for_today() -> None:
    assert evaluate(facts(attempts=[ist(19, 10), ist(19, 12), ist(19, 20)])).allowed


def test_weekly_cap_defers_until_the_oldest_attempt_ages_out() -> None:
    week = [ist(d, 10) for d in (14, 15, 16, 17, 18, 19, 19)]
    result = evaluate(facts(attempts=week))
    assert result.decision == Decision.DEFER
    assert codes(result) == ["weekly_cap"]
    # The 14th 10:00 attempt leaves the 7-day window on the 21st 10:00 (inside hours).
    assert result.defer_until == ist(21, 10).astimezone(UTC)


def test_attempts_older_than_a_week_are_ignored() -> None:
    old = [ist(12, 10)] * 10
    assert evaluate(facts(attempts=old)).allowed


def test_blocks_win_over_defers() -> None:
    result = evaluate(facts(now=ist(20, 23), consents=frozenset(), attempts=[ist(20, 9)] * 3))
    assert result.decision == Decision.BLOCK
    assert codes(result) == ["no_consent"]


def test_owner_summary_is_plain_language() -> None:
    lines = owner_summary({"dnd_registered": 18, "outside_hours": 1, "opted_out": 2})
    assert lines == [
        "18 people skipped: on Do-Not-Disturb list",
        "2 people skipped: asked not to be called",
        "1 person deferred: outside allowed calling hours",
    ]


def test_all_reasons_are_worded() -> None:
    from mitra_core.telephony.compliance import REASON_TEXT

    # Each reason reads after "N people skipped: ", so no capital-led sentence or full stop.
    assert all(text and not text.endswith(".") for text in REASON_TEXT.values())
