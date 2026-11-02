"""Report calls to services/core: call start and call end (transcript, actions, latency, usage).

Never on the audio path: every report is a fire-and-forget asyncio task with its own retries,
built from a snapshot taken when the event happens, so a slow or down core cannot delay a turn.
Disabled cleanly (``from_settings`` returns None) unless ``MITRA_CORE_URL`` and
``MITRA_CORE_SERVICE_TOKEN`` are both set. Only calls whose pack came from core are reported
(the employee id must be a UUID; local fixture packs are skipped).

Core endpoints (``services/core/src/mitra_core/api/internal_calls.py``):
``POST /internal/v1/calls`` then ``POST /internal/v1/calls/{id}/end``; both are idempotent on
the call id (this session's id), so retries are safe. The end report waits for the start report.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import httpx
import structlog

from mitra_voice.config import Settings
from mitra_voice.latency import summarize

if TYPE_CHECKING:
    from mitra_voice.session import CallSession

log = structlog.get_logger(__name__)

Direction = Literal["inbound", "outbound", "web"]
ActionLog = Callable[[], list[dict[str, Any]]]

# Core's validation limits (schemas/call.py); trimmed here so a long call never gets a 422.
MAX_TURNS = 400
MAX_TURN_CHARS = 4_000
MAX_ACTIONS = 100
MAX_JSON_BYTES = 8_000
_ACTION_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_RETRYABLE = {408, 425, 429, 500, 502, 503, 504}


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _small(value: dict[str, Any]) -> dict[str, Any]:
    return value if len(json.dumps(value, default=str)) <= MAX_JSON_BYTES else {"truncated": True}


def start_payload(session: CallSession) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(uuid.UUID(session.id)),
        "employee_id": session.pack.employee_id,
        "direction": session.direction,
        "started_at": session.created_at,
        "language": session.call.language,
        "external_ref": session.id,
    }
    if session.caller_phone:
        body["caller_phone"] = session.caller_phone
    return body


def end_payload(session: CallSession) -> dict[str, Any]:
    actions = []
    for a in (session.action_log() if session.action_log else [])[:MAX_ACTIONS]:
        name = str(a.get("name", ""))
        if not _ACTION_NAME.fullmatch(name):
            continue
        actions.append(
            {
                "name": name,
                "args": _small(dict(a.get("args") or {})),
                "result": _small(dict(a.get("result") or {})),
            }
        )
    return {
        "employee_id": session.pack.employee_id,
        "ended_at": session.ended_at or datetime.now(UTC).isoformat(),
        "transcript": [
            {"role": t.role, "text": t.text[:MAX_TURN_CHARS], "interrupted": t.interrupted}
            for t in session.transcript[-MAX_TURNS:]
            if t.text.strip()
        ],
        "actions": actions,
        "language": session.call.language,
        "languages": list(dict.fromkeys(session.call.language_history))[:10],
        "latency_stats": _small(
            {"turns": len(session.tracker.turns), **summarize(session.tracker.turns)}
        ),
        "usage": _small(session.usage.summary()),
    }


class CoreCallReporter:
    def __init__(
        self,
        core_url: str,
        service_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        attempts: int = 4,
        backoff_s: float = 0.5,
        timeout_s: float = 5.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=core_url.rstrip("/"),
            headers={"Authorization": f"Bearer {service_token}"},
            timeout=timeout_s,
            transport=transport,
        )
        self._attempts = attempts
        self._backoff = backoff_s
        self._started: dict[str, asyncio.Task[bool]] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    @classmethod
    def from_settings(cls, settings: Settings) -> CoreCallReporter | None:
        if not settings.mitra_core_url or not settings.mitra_core_service_token:
            return None
        return cls(settings.mitra_core_url, settings.mitra_core_service_token.get_secret_value())

    @staticmethod
    def reportable(session: CallSession) -> bool:
        return _uuid(session.pack.employee_id) is not None and _uuid(session.id) is not None

    def _spawn(self, coro: Any) -> asyncio.Task[Any] | None:
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:  # no event loop (e.g. a sync test building a session)
            coro.close()
            return None
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def call_started(self, session: CallSession) -> None:
        if not self.reportable(session) or session.id in self._started:
            return
        task = self._spawn(self._post("/internal/v1/calls", start_payload(session), session.id))
        if task is not None:
            self._started[session.id] = task

    def call_ended(self, session: CallSession) -> None:
        if not self.reportable(session):
            return
        start, end = start_payload(session), end_payload(session)  # snapshot now
        self._spawn(self._finish(session.id, start, end))

    async def _finish(self, sid: str, start: dict[str, Any], end: dict[str, Any]) -> None:
        started = self._started.pop(sid, None)
        ok = await started if started is not None else False
        if not ok:  # start never reached core: try again before the end report
            ok = await self._post("/internal/v1/calls", start, sid)
        if ok:
            await self._post(f"/internal/v1/calls/{start['id']}/end", end, sid)

    async def _post(self, path: str, body: dict[str, Any], sid: str) -> bool:
        for attempt in range(1, self._attempts + 1):
            try:
                res = await self._client.post(path, json=body)
            except httpx.HTTPError as e:
                outcome = type(e).__name__
            else:
                if res.status_code < 300:
                    return True
                outcome = str(res.status_code)
                if res.status_code not in _RETRYABLE:
                    break
            if attempt < self._attempts:
                await asyncio.sleep(self._backoff * 2 ** (attempt - 1))
        # Never the payload (transcripts and phone numbers stay out of logs).
        log.warning("core_report.failed", session_id=sid, path=path.split("/")[-1], outcome=outcome)
        return False

    async def drain(self, timeout_s: float = 10.0) -> None:
        """Wait for pending reports (shutdown and tests)."""
        pending = list(self._tasks)
        if pending:
            await asyncio.wait(pending, timeout=timeout_s)

    async def aclose(self) -> None:
        await self.drain()
        await self._client.aclose()
