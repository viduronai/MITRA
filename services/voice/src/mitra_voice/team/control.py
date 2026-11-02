"""One phone call's link to people: live transcript out, supervisor instructions in, transfers.

* Every transcript turn is posted to core (``/internal/v1/team/live/{id}/turns``) in order, off
  the audio path; the response carries any pending supervisor instructions. A slow poll picks
  them up when nobody is talking.
* A whisper becomes a vetted per-turn note for the brain (``supervisor.clean_instruction``).
* A takeover, or the brain's ``transfer_to_human`` tool, runs the escalation ladder. If somebody
  answers, the AI steps out; if nobody does, a hand-off card is created in core, the caller
  hears when they will be called back, and the AI carries on with the call.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from mitra_voice.brain.tools import IST, ToolCall
from mitra_voice.config import Settings
from mitra_voice.team.ladder import LadderStep, Transferer, run_ladder
from mitra_voice.team.supervisor import (
    clean_instruction,
    hold_line,
    nobody_line,
    whisper_summary,
)

if TYPE_CHECKING:
    from mitra_voice.brain.engine import Brain
    from mitra_voice.session import CallSession, TranscriptEntry

log = structlog.get_logger(__name__)

Say = Callable[[str], Awaitable[None]]
End = Callable[[str], Awaitable[None]]
POLL_S = 2.0
FALLBACK_CALLBACK = timedelta(hours=2)


def _uuid(value: str) -> str | None:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


class LiveControl:
    def __init__(
        self,
        session: CallSession,
        *,
        client: httpx.AsyncClient,
        carrier: Transferer | None,
        call_sid: str | None,
        poll_s: float = POLL_S,
    ) -> None:
        self.session = session
        self.call_id = _uuid(session.id) or session.id
        self.employee_id = session.pack.employee_id
        self._client = client
        self._carrier = carrier
        self._call_sid = call_sid
        self._poll_s = poll_s
        self._say: Say | None = None
        self._end: End | None = None
        self._queue: asyncio.Queue[TranscriptEntry | None] = asyncio.Queue()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._transfer: asyncio.Task[None] | None = None
        self.message_taken = False

    @classmethod
    def from_settings(
        cls, settings: Settings, session: CallSession, carrier: object, call_sid: str | None
    ) -> LiveControl | None:
        """Only for calls core knows about (UUID employee and call ids) with core configured."""
        token = settings.mitra_core_service_token
        if not settings.mitra_core_url or token is None:
            return None
        if _uuid(session.pack.employee_id) is None or _uuid(session.id) is None:
            return None
        client = httpx.AsyncClient(
            base_url=settings.mitra_core_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token.get_secret_value()}"},
            timeout=5.0,
        )
        transferer = carrier if hasattr(carrier, "transfer") else None
        return cls(session, client=client, carrier=transferer, call_sid=call_sid)

    # --- wiring -----------------------------------------------------------------------------------

    @property
    def brain(self) -> Brain | None:
        return self.session.brain

    def attach(self, say: Say, end: End) -> None:
        """Start: listen to the transcript, poll for instructions, take over transfers."""
        self._say, self._end = say, end
        self.session.listeners.append(self._queue.put_nowait)
        if self.brain is not None:
            self.brain.executor.on_transfer = self.request_transfer
        self._spawn(self._post_turns())
        self._spawn(self._poll())

    def _spawn(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def aclose(self) -> None:
        self._queue.put_nowait(None)
        for task in list(self._tasks):
            if task is not self._transfer:
                task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, timeout=2.0)
        await self._client.aclose()

    # --- live transcript + instructions ---------------------------------------------------------

    async def _post_turns(self) -> None:
        while (entry := await self._queue.get()) is not None:
            body = {"employee_id": self.employee_id, "role": entry.role, "text": entry.text[:2000]}
            data = await self._call("POST", f"/live/{self.call_id}/turns", json=body)
            await self.apply(data.get("instructions", []) if data else [])

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(self._poll_s)
            data = await self._call(
                "GET",
                f"/live/{self.call_id}/instructions",
                params={"employee_id": self.employee_id},
            )
            await self.apply(data.get("instructions", []) if data else [])

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any] | None:
        try:
            res = await self._client.request(method, f"/internal/v1/team{path}", **kwargs)
        except httpx.HTTPError as exc:
            log.warning("team.core_unreachable", path=path.split("/")[-1], error=type(exc).__name__)
            return None
        if res.status_code >= 300:
            log.warning("team.core_refused", path=path.split("/")[-1], status=res.status_code)
            return None
        data = res.json()
        return data if isinstance(data, dict) else None

    async def apply(self, instructions: list[dict[str, Any]]) -> None:
        for item in instructions:
            kind = item.get("kind")
            if kind == "whisper":
                text = clean_instruction(str(item.get("text") or ""))
                if text is None or self.brain is None:
                    log.warning("supervisor.whisper_refused", session_id=self.session.id)
                    continue
                self.brain.supervisor_notes.append(text)
                log.info("supervisor.whisper", session_id=self.session.id)
            elif kind == "takeover" and item.get("phone_e164"):
                step = LadderStep(str(item.get("name") or "the manager"), item["phone_e164"], 25)
                self._start_transfer("supervisor takeover", [step], announce=True)

    # --- transfers ------------------------------------------------------------------------------

    def request_transfer(self, reason: str) -> None:
        """From the brain's ``transfer_to_human`` tool (sync, inside a turn)."""
        self._start_transfer(reason, None, announce=False)

    def _start_transfer(
        self, reason: str, steps: list[LadderStep] | None, *, announce: bool
    ) -> None:
        if self._transfer is not None and not self._transfer.done():
            return
        self._transfer = asyncio.get_running_loop().create_task(
            self.transfer(reason, steps, announce=announce)
        )
        self._tasks.add(self._transfer)
        self._transfer.add_done_callback(self._tasks.discard)

    async def _ladder(self) -> tuple[list[LadderStep], dict[str, Any]]:
        data = await self._call("GET", "/ladder", params={"employee_id": self.employee_id}) or {}
        steps = [
            LadderStep(s["name"], s["phone_e164"], int(s["ring_timeout_s"]), bool(s["is_owner"]))
            for s in data.get("steps", [])
        ]
        return steps, data

    def _record(self, name: str, args: dict[str, Any], result: dict[str, Any]) -> None:
        if self.brain is not None:
            self.brain.executor.calls.append(ToolCall(name=name, args=args, result=result))

    async def transfer(
        self, reason: str, steps: list[LadderStep] | None = None, *, announce: bool = False
    ) -> None:
        lang = self.session.call.language
        ladder, data = await self._ladder()
        steps = steps or ladder
        if announce and steps and self._say is not None:
            await self._say(hold_line(lang, steps[0].name))
        callers = [t.text for t in self.session.transcript if t.role == "user"]
        last4 = self.session.caller_phone[-4:] if self.session.caller_phone else None
        whisper = whisper_summary(reason, callers, last4)
        result = None
        if steps and self._carrier is not None and self._call_sid:
            result = await run_ladder(self._carrier, self._call_sid, steps, whisper)
        attempts = result.attempts if result else []
        if result is not None and result.answered_by is not None:
            self._record("transfer_result", {"reason": reason}, {"status": "connected"})
            log.info("transfer.connected", session_id=self.session.id, attempts=len(attempts))
            if self._end is not None:
                await self._end("transferred to staff")
            return
        await self._take_message(reason, callers, attempts, data)

    async def _take_message(
        self,
        reason: str,
        callers: list[str],
        attempts: list[dict[str, str]],
        ladder: dict[str, Any],
    ) -> None:
        body: dict[str, Any] = {
            "employee_id": self.employee_id,
            "call_id": self.call_id,
            "reason": reason[:300],
            "message": " / ".join(callers[-3:])[:1000],
            "attempts": attempts[:5],
        }
        if self.session.caller_phone:
            body["caller_phone"] = self.session.caller_phone
        card = await self._call("POST", "/handoff-cards", json=body)
        when = str(ladder.get("callback_local") or "")
        day = str(ladder.get("callback_day") or "today")
        if not when:  # core unreachable: still promise something concrete
            when, day = (datetime.now(IST) + FALLBACK_CALLBACK).strftime("%H:%M"), "today"

        self.message_taken = True
        self._record(
            "take_message",
            {"reason": reason[:200]},
            {"status": "message_taken" if card else "failed", "callback_by": when, "day": day},
        )
        if self.brain is not None:
            self.brain.executor.on_transfer = None  # don't ring the ladder twice
            self.brain.supervisor_notes.append(
                "Nobody could take the transfer. You already took the caller's message and told "
                f"them the team will call back by {when or 'soon'} {day}. Do not offer another "
                "transfer; keep helping with anything else."
            )
        if self._say is not None:
            await self._say(nobody_line(self.session.call.language, when, day))
