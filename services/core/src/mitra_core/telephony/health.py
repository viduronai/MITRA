"""Number health monitor (NUM-08, WORKFLOWS 11b): answer rate and spam labels per number.

Pure: :func:`assess` takes this week's and last week's attempt counts plus the spam flag and
returns Healthy / Watch / Paused with plain-language reasons and remediation steps. The job
(``service.run_health``) counts attempts from ``outbound_attempt`` and applies the result; a
Paused number gets ``outbound_enabled = false`` until the owner resumes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mitra_core.telephony.enums import NumberHealth

MIN_SAMPLE = 20  # fewer attempts than this: too little data to judge a rate
PAUSE_BELOW = 0.15
WATCH_BELOW = 0.30
PAUSE_DROP = 0.40  # relative drop vs the previous 7 days
WATCH_DROP = 0.20

REMEDIATION: dict[NumberHealth, list[str]] = {
    NumberHealth.HEALTHY: [],
    NumberHealth.WATCH: [
        "Send a WhatsApp heads-up before each call so people expect it.",
        "Finish Truecaller verification and CNAP name registration if pending.",
        "Avoid calling the same person again soon after a missed call.",
    ],
    NumberHealth.PAUSED: [
        "Outbound calls from this number are paused; inbound calls still work.",
        "We are appealing the spam label with Truecaller and the carrier.",
        "Re-verify your business name, then resume calls from this card.",
    ],
}


@dataclass(frozen=True, slots=True)
class HealthInputs:
    attempts_7d: int
    answered_7d: int
    attempts_prev_7d: int = 0
    answered_prev_7d: int = 0
    spam_flag: bool = False


@dataclass(frozen=True, slots=True)
class HealthAssessment:
    health: NumberHealth
    answer_rate_7d: float | None
    reasons: list[str] = field(default_factory=list)

    @property
    def remediation(self) -> list[str]:
        return REMEDIATION[self.health]


def _rate(answered: int, attempts: int) -> float | None:
    return answered / attempts if attempts else None


def assess(inputs: HealthInputs) -> HealthAssessment:
    rate = _rate(inputs.answered_7d, inputs.attempts_7d)
    if inputs.spam_flag:
        return HealthAssessment(NumberHealth.PAUSED, rate, ["Marked as spam by callers"])
    if rate is None or inputs.attempts_7d < MIN_SAMPLE:
        return HealthAssessment(NumberHealth.HEALTHY, rate)

    previous = _rate(inputs.answered_prev_7d, inputs.attempts_prev_7d)
    drop = 0.0
    if previous and inputs.attempts_prev_7d >= MIN_SAMPLE:
        drop = max(0.0, (previous - rate) / previous)
    pct = f"{round(rate * 100)}%"
    if rate < PAUSE_BELOW:
        return HealthAssessment(NumberHealth.PAUSED, rate, [f"Only {pct} of calls answered"])
    if drop >= PAUSE_DROP:
        return HealthAssessment(
            NumberHealth.PAUSED, rate, [f"Answer rate fell sharply to {pct} this week"]
        )
    if rate < WATCH_BELOW:
        return HealthAssessment(NumberHealth.WATCH, rate, [f"{pct} of calls answered"])
    if drop >= WATCH_DROP:
        return HealthAssessment(NumberHealth.WATCH, rate, [f"Answer rate dropped to {pct}"])
    return HealthAssessment(NumberHealth.HEALTHY, rate)
