"""Warm transfer down the escalation ladder (CALL-06/07/19): staff A -> B -> owner.

For each step the carrier rings the person with the caller on hold; when they pick up they hear
the one-line whisper summary privately, then the two calls are bridged. An unanswered, busy or
failed step moves on to the next. If nobody answers, the caller is handed back to the AI, which
takes a message (see ``control.LiveControl``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

import structlog

log = structlog.get_logger(__name__)

TransferOutcome = Literal["answered", "no_answer", "busy", "failed"]


@dataclass(frozen=True, slots=True)
class LadderStep:
    name: str
    phone_e164: str  # never logged
    ring_timeout_s: int = 20
    is_owner: bool = False


class Transferer(Protocol):
    async def transfer(
        self, call_sid: str, to_e164: str, *, whisper: str, ring_timeout_s: int
    ) -> TransferOutcome: ...


@dataclass
class LadderResult:
    answered_by: LadderStep | None = None
    attempts: list[dict[str, str]] = field(default_factory=list)


async def run_ladder(
    carrier: Transferer, call_sid: str, steps: list[LadderStep], whisper: str
) -> LadderResult:
    result = LadderResult()
    for step in steps:
        try:
            outcome = await carrier.transfer(
                call_sid, step.phone_e164, whisper=whisper, ring_timeout_s=step.ring_timeout_s
            )
        except Exception as exc:  # a carrier error is one failed step, never a dropped call
            log.warning("transfer.step_error", error=type(exc).__name__)
            outcome = "failed"
        result.attempts.append({"name": step.name, "outcome": outcome})
        log.info("transfer.step", step=len(result.attempts), outcome=outcome, owner=step.is_owner)
        if outcome == "answered":
            result.answered_by = step
            break
    return result
