"""Sim carrier: places nothing on the phone network. Default until a carrier account is live.

Each placed call gets a ``SIM...`` sid and is remembered in ``placed``. With ``answer_ws_url``
set, the "customer" picks up: the carrier simulator connects to our own Exotel WebSocket with
that sid, so the full outbound loop (compliance -> place -> stream -> pipeline) runs locally.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

import structlog

from mitra_voice.carriers.base import CarrierName, OutboundIntent, PlacedCall, new_sim_sid
from mitra_voice.carriers.simulator import SimulatedCall, simulate_call
from mitra_voice.team.ladder import TransferOutcome

log = structlog.get_logger(__name__)


@dataclass
class SimCarrier:
    answer_ws_url: str | None = None
    answer_pcm: bytes = b""  # what the simulated customer says after the greeting
    headers: dict[str, str] = field(default_factory=dict)
    placed: list[tuple[PlacedCall, OutboundIntent]] = field(default_factory=list)
    answered: list[SimulatedCall] = field(default_factory=list)
    name: CarrierName = "sim"
    # Warm transfers (CALL-06): how each staff number "answers"; unknown numbers don't.
    staff_answers: dict[str, TransferOutcome] = field(default_factory=dict)
    ring_s: float = 0.0  # simulated ringing per step (0 in tests)
    transfers: list[tuple[str, str, str, TransferOutcome]] = field(default_factory=list)
    _tasks: set[asyncio.Task[None]] = field(default_factory=set)

    async def place_call(self, intent: OutboundIntent) -> PlacedCall:
        placed = PlacedCall(carrier="sim", call_sid=new_sim_sid(), status="queued")
        self.placed.append((placed, intent))
        log.info("sim.call_placed", call_sid=placed.call_sid, purpose=intent.purpose)
        if self.answer_ws_url:
            task = asyncio.create_task(self._answer(placed, intent))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return placed

    async def _answer(self, placed: PlacedCall, intent: OutboundIntent) -> None:
        assert self.answer_ws_url is not None  # noqa: S101 (checked by the caller)
        await asyncio.sleep(0.05)  # "ringing": let place_call's caller register the sid first
        try:
            call = await simulate_call(
                self.answer_ws_url,
                self.answer_pcm,
                call_sid=placed.call_sid,
                from_=intent.contact_phone,
                to=intent.caller_id,
                headers=self.headers,
            )
            self.answered.append(call)
        except Exception:
            log.exception("sim.answer_failed", call_sid=placed.call_sid)

    async def transfer(
        self, call_sid: str, to_e164: str, *, whisper: str, ring_timeout_s: int
    ) -> TransferOutcome:
        """Ring staff with the caller on hold; whisper, then bridge if they pick up."""
        outcome = self.staff_answers.get(to_e164, "no_answer")
        await asyncio.sleep(min(self.ring_s, ring_timeout_s))
        self.transfers.append((call_sid, to_e164, whisper, outcome))
        log.info("sim.transfer", call_sid=call_sid, outcome=outcome)
        return outcome

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
