"""One live call: its pack, transcript, latency turns, and the channel back to the client."""

from __future__ import annotations

import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import structlog

from mitra_voice.call_context import CallContext, stt_lock_language
from mitra_voice.latency import LatencyTracker, TurnTimings, summarize, turn_record
from mitra_voice.logging import redact_phones
from mitra_voice.pack import EmployeePack, Lang, Scenario
from mitra_voice.providers import ResolvedProviders
from mitra_voice.usage import UsageMeter

if TYPE_CHECKING:
    from mitra_voice.brain.engine import Brain
    from mitra_voice.core_client import ActionLog, CoreCallReporter, Direction

log = structlog.get_logger(__name__)

Role = Literal["user", "assistant"]
SendFn = Callable[[dict[str, Any]], None]
MAX_SESSIONS = 50


def _noop(_: dict[str, Any]) -> None:
    return None


@dataclass
class TranscriptEntry:
    role: Role
    text: str
    interrupted: bool = False


@dataclass
class CallSession:
    scenario: Scenario
    pack: EmployeePack
    providers: ResolvedProviders
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str | None = None
    transcript: list[TranscriptEntry] = field(default_factory=list)
    tracker: LatencyTracker = field(default_factory=LatencyTracker)
    usage: UsageMeter = field(default_factory=UsageMeter)
    send: SendFn = _noop
    # Call reporting to services/core (core_client.py); None = not reported.
    reporter: CoreCallReporter | None = None
    direction: Direction = "web"
    caller_phone: str | None = field(default=None, repr=False)  # E.164; never logged
    action_log: ActionLog | None = None  # the brain's tool calls, read at call end
    # Phone calls: the carrier's call id, the call's brain, transcript listeners (team.control).
    call_sid: str | None = None
    brain: Brain | None = None
    listeners: list[Callable[[TranscriptEntry], None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.tracker.on_turn_complete = self._on_turn_complete
        self._log = log.bind(session_id=self.id, scenario=self.scenario)
        # Starts in the pack's default language (TODO: caller's last language from memory).
        self.call = CallContext(
            session_id=self.id,
            language=self.pack.default_language,
            allowed=tuple(self.pack.languages),
            stt_locked=self.providers.stt == "sarvam"
            and stt_lock_language(self.pack.languages) is not None,
        )
        self.call.on_language_change.append(self._on_language_change)
        if self.reporter is not None:
            self.reporter.call_started(self)

    async def _on_language_change(self, lang: Lang) -> None:
        self._log.info("call.language", language=lang)
        self.send({"type": "language", "language": lang})

    # --- events from the pipeline ---------------------------------------------------------------

    def _notify(self, entry: TranscriptEntry) -> None:
        self.transcript.append(entry)
        for listener in self.listeners:
            listener(entry)

    def add_user(self, text: str) -> None:
        self._notify(TranscriptEntry("user", text))
        self._log.info("turn.user", text=redact_phones(text), turn=len(self.tracker.turns))
        self.send(
            {"type": "transcript", "role": "user", "text": text, "language": self.call.human_lang}
        )

    def add_assistant(self, text: str, *, interrupted: bool = False) -> None:
        self._notify(TranscriptEntry("assistant", text, interrupted))
        self._log.info("turn.assistant", text=redact_phones(text), interrupted=interrupted)
        self.send(
            {"type": "transcript", "role": "assistant", "text": text, "interrupted": interrupted}
        )

    def assistant_delta(self, text: str) -> None:
        self.send({"type": "assistant_delta", "text": text})

    def human_layer(self, kind: Literal["filler", "backchannel"], text: str) -> None:
        if kind == "filler":
            self.tracker.mark_filler(text)
        self._log.info(f"human.{kind}", text=text)
        self.send({"type": kind, "text": text})

    async def _on_turn_complete(self, turn: TurnTimings) -> None:
        record = turn_record(turn)
        # Structured latency log line; timings only, never transcript text.
        self._log.info("turn.latency", **record)
        self.send({"type": "metrics", "turn": record})
        self.send({"type": "usage", "usage": self.usage.summary()})

    def end(self) -> None:
        first = self.ended_at is None
        self.ended_at = datetime.now(UTC).isoformat()
        self._log.info("session.ended", turns=len(self.tracker.turns), **self.usage.summary())
        if first and self.reporter is not None:
            self.reporter.call_ended(self)

    # --- read side ------------------------------------------------------------------------------

    def metrics(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "scenario": self.scenario,
            "created_at": self.created_at,
            "ended_at": self.ended_at,
            "languages": self.call.language_history,
            "providers": {
                "stt": self.providers.stt,
                "llm": self.providers.llm,
                "tts": self.providers.tts,
            },
            "turns": [turn_record(t) for t in self.tracker.turns],
            "summary": summarize(self.tracker.turns),
            "usage": self.usage.summary(),
        }


class SessionRegistry:
    """In-memory, bounded (oldest dropped). TODO(prod): Valkey for live state (TRD §4)."""

    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: OrderedDict[str, CallSession] = OrderedDict()
        self._max = max_sessions

    def add(self, session: CallSession) -> None:
        self._sessions[session.id] = session
        while len(self._sessions) > self._max:
            self._sessions.popitem(last=False)

    def get(self, session_id: str) -> CallSession | None:
        return self._sessions.get(session_id)

    def all(self) -> list[CallSession]:
        return list(self._sessions.values())
