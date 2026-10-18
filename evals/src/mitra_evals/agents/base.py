"""The agent-under-test interface. Every adapter (scripted, reference, core-sim, voice-text)
implements :class:`AgentUnderTest`; the runner only ever talks to this Protocol.

Text-mode contract (what services/voice must expose for text-mode evals)
--------------------------------------------------------------------------
One eval scenario = one call = one :class:`ConversationSession`:

1. ``session = await agent.open(pack, context)`` - load the employee pack (facts, greeting,
   behaviour) exactly as a live call would, but skip STT/TTS and telephony.
2. ``greeting = await session.start()`` - the employee's first turn, spoken before the caller
   says anything (must carry the AI + recording disclosure).
3. ``reply = await session.send(caller_text, interrupt=False)`` - once per caller turn.
   ``interrupt=True`` means the caller barged in while the previous reply was still playing;
   treat it like a barge-in (stop, keep only what was heard, answer the new utterance).
4. ``await session.close()`` - always called, even after errors.

Each :class:`AgentReply` carries the text that would be spoken, the in-call tool calls made
during that turn (``actions``), whether the agent hung up, and optional timings. Over HTTP the
same contract is (JSON bodies are these dataclasses' fields):

* ``POST {MITRA_VOICE_TEXT_URL}/v1/text-sessions``  ``{"pack": EmployeePack, "context":
  CallContext}`` -> ``201 {"session_id": str, "reply": AgentReply}`` (the reply is the greeting)
* ``POST /v1/text-sessions/{session_id}/turns``  ``{"text": str, "interrupt": bool}``
  -> ``200 AgentReply``
* ``DELETE /v1/text-sessions/{session_id}`` -> ``204``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from mitra_evals.schema import ActionName, Direction, EmployeePack, Language


class AgentUnavailableError(RuntimeError):
    """The adapter cannot run here (missing env, import or service); the CLI reports it."""


@dataclass(frozen=True, slots=True)
class Action:
    name: ActionName
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TurnTimings:
    """Milliseconds from the end of the caller's turn. Text-mode agents may leave these unset;
    the runner always records its own wall-clock ``response_ms``."""

    first_token_ms: float | None = None
    first_audio_ms: float | None = None
    # Barge-in only: time from caller speech onset to TTS stop.
    tts_stop_ms: float | None = None


@dataclass(frozen=True, slots=True)
class AgentReply:
    text: str
    actions: tuple[Action, ...] = ()
    end_call: bool = False
    timings: TurnTimings = field(default_factory=TurnTimings)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AgentReply:
        timings = data.get("timings") or {}
        return cls(
            text=str(data.get("text", "")),
            actions=tuple(
                Action(name=a["name"], args=dict(a.get("args") or {}))
                for a in data.get("actions") or []
            ),
            end_call=bool(data.get("end_call", False)),
            timings=TurnTimings(
                first_token_ms=timings.get("first_token_ms"),
                first_audio_ms=timings.get("first_audio_ms"),
                tts_stop_ms=timings.get("tts_stop_ms"),
            ),
        )


@dataclass(frozen=True, slots=True)
class CallContext:
    scenario_id: str
    # The caller's language as known before the call (memory / IVR); greet in its base language.
    language: Language
    direction: Direction = "inbound"
    caller_name: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "language": self.language,
            "direction": self.direction,
            "caller_name": self.caller_name,
        }


class ConversationSession(Protocol):
    async def start(self) -> AgentReply: ...

    async def send(self, caller_text: str, *, interrupt: bool = False) -> AgentReply: ...

    async def close(self) -> None: ...


class AgentUnderTest(Protocol):
    name: str

    async def open(self, pack: EmployeePack, context: CallContext) -> ConversationSession: ...
