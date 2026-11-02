"""Number-health monitor (pure), forwarding codes and number display."""

from __future__ import annotations

import pytest

from mitra_core.telephony.enums import NumberHealth
from mitra_core.telephony.forwarding import codes_for, dial_form
from mitra_core.telephony.health import HealthInputs, assess
from mitra_core.telephony.service import display_number


@pytest.mark.parametrize(
    ("inputs", "health"),
    [
        (HealthInputs(0, 0), NumberHealth.HEALTHY),
        (HealthInputs(10, 0), NumberHealth.HEALTHY),  # too little data to judge
        (HealthInputs(10, 0, spam_flag=True), NumberHealth.PAUSED),  # spam always pauses
        (HealthInputs(100, 50), NumberHealth.HEALTHY),
        (HealthInputs(100, 25), NumberHealth.WATCH),  # < 30% answered
        (HealthInputs(100, 10), NumberHealth.PAUSED),  # < 15% answered
        (HealthInputs(100, 40, 100, 52), NumberHealth.WATCH),  # 23% relative drop
        (HealthInputs(100, 32, 100, 60), NumberHealth.PAUSED),  # 47% relative drop
        (HealthInputs(100, 40, 10, 9), NumberHealth.HEALTHY),  # previous week too small
    ],
)
def test_assess(inputs: HealthInputs, health: NumberHealth) -> None:
    result = assess(inputs)
    assert result.health == health
    assert (result.reasons == []) == (health == NumberHealth.HEALTHY)
    assert (result.remediation == []) == (health == NumberHealth.HEALTHY)


def test_answer_rate_is_reported() -> None:
    assert assess(HealthInputs(40, 18)).answer_rate_7d == pytest.approx(0.45)
    assert assess(HealthInputs(0, 0)).answer_rate_7d is None


@pytest.mark.parametrize(
    ("e164", "mobile", "dialled", "shown"),
    [
        ("+914041234567", False, "04041234567", "040 4123 4567"),
        ("+918664123456", False, "08664123456", "0866 412 3456"),
        ("+918041234567", False, "08041234567", "080 4123 4567"),
        ("+919876543210", True, "9876543210", "98765 43210"),
        ("+918876543210", True, "8876543210", "88765 43210"),
    ],
)
def test_number_forms(e164: str, mobile: bool, dialled: str, shown: str) -> None:
    assert dial_form(e164, mobile=mobile) == dialled
    assert display_number(e164, mobile=mobile) == shown


def test_forwarding_codes_per_operator() -> None:
    codes = {c.operator: c for c in codes_for("+914041234567")}
    assert list(codes) == ["jio", "airtel", "vi", "bsnl"]
    assert codes["jio"].busy == "*405*04041234567"
    assert codes["jio"].no_answer == "*403*04041234567"
    assert codes["jio"].unreachable == "*409*04041234567"
    assert codes["jio"].cancel == "*413"
    for op in ("airtel", "vi", "bsnl"):
        assert codes[op].busy == "**67*04041234567#"
        assert codes[op].no_answer == "**61*04041234567#"
        assert codes[op].unreachable == "**62*04041234567#"
        assert codes[op].cancel == "##004#"
