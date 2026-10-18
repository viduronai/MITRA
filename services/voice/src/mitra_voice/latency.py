"""Per-turn latency tracing (TRD §12: first audio <= 800 ms p95; WORKFLOWS §1 latency budget).

A Pipecat observer sees every frame push without being in the pipeline, so tracing never adds
latency. Observers run off a queue, so times come from each push's own timestamp (pipeline clock),
never from when the observer happens to run. Timestamps are ms since the pipeline started:

- ``user_speech_end``: VAD stop minus the VAD stop window, i.e. when the caller actually went quiet
- ``stt_final``: final transcript out of STT
- ``turn_end``: end-of-turn decision (UserStoppedSpeakingFrame)
- ``llm_request`` / ``llm_first_token``: context sent to the LLM / first token back
- ``tts_text_in`` / ``tts_first_byte``: first text into TTS / first audio out of TTS
- ``first_audio_out``: the output transport starts playing (BotStartedSpeakingFrame)
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    LLMContextFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregator
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService

DERIVED_METRICS = ("stt_ms", "turn_detect_ms", "llm_ttft_ms", "tts_ttfb_ms", "first_audio_ms")


@dataclass(slots=True)
class TurnTimings:
    turn: int
    user_speech_end: float | None = None
    stt_final: float | None = None
    turn_end: float | None = None
    llm_request: float | None = None
    llm_first_token: float | None = None
    tts_text_in: float | None = None
    tts_first_byte: float | None = None
    first_audio_out: float | None = None
    filler: str | None = None
    interrupted: bool = False

    @property
    def complete(self) -> bool:
        return self.first_audio_out is not None


def _delta(end: float | None, start: float | None) -> float | None:
    if end is None or start is None:
        return None
    return round(end - start, 1)


def derive(t: TurnTimings) -> dict[str, float | None]:
    """Stage durations in ms; ``first_audio_ms`` is the caller-perceived voice-to-voice latency."""
    return {
        "stt_ms": _delta(t.stt_final, t.user_speech_end),
        "turn_detect_ms": _delta(t.turn_end, t.user_speech_end),
        "llm_ttft_ms": _delta(t.llm_first_token, t.llm_request),
        "tts_ttfb_ms": _delta(t.tts_first_byte, t.tts_text_in),
        "first_audio_ms": _delta(t.first_audio_out, t.user_speech_end),
    }


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (``q`` in 0..100) of a non-empty sequence."""
    if not values:
        raise ValueError("percentile of an empty sequence")
    if not 0 <= q <= 100:
        raise ValueError("q must be within 0..100")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q / 100
    lo, hi = math.floor(rank), math.ceil(rank)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo), 1)


def summarize(turns: Sequence[TurnTimings]) -> dict[str, dict[str, float | int | None]]:
    summary: dict[str, dict[str, float | int | None]] = {}
    derived = [derive(t) for t in turns if t.complete]
    for name in DERIVED_METRICS:
        values = [v for d in derived if (v := d[name]) is not None]
        summary[name] = {
            "n": len(values),
            "p50": percentile(values, 50) if values else None,
            "p95": percentile(values, 95) if values else None,
        }
    return summary


def turn_record(t: TurnTimings) -> dict[str, Any]:
    return {**asdict(t), **derive(t)}


TurnCallback = Callable[[TurnTimings], Awaitable[None]]


@dataclass
class LatencyTracker:
    """Session-level store of turns; ``observer()`` builds the Pipecat observer that fills it."""

    on_turn_complete: TurnCallback | None = None
    turns: list[TurnTimings] = field(default_factory=list)

    @property
    def current(self) -> TurnTimings | None:
        return self.turns[-1] if self.turns else None

    def completed(self) -> list[TurnTimings]:
        return [t for t in self.turns if t.complete]

    def observer(self) -> LatencyObserver:
        return LatencyObserver(self)

    def mark_filler(self, text: str) -> None:
        if self.current is not None:
            self.current.filler = text

    def mark_reply_interrupted(self) -> None:
        """The caller barged in on the reply of the turn before the one now starting."""
        if len(self.turns) >= 2:
            self.turns[-2].interrupted = True


class LatencyObserver(BaseObserver):
    def __init__(self, tracker: LatencyTracker) -> None:
        super().__init__(observe_every_push=False)
        self._tracker = tracker

    async def on_push_frame(self, data: FramePushed) -> None:
        frame, tracker = data.frame, self._tracker
        # Broadcast frames travel both ways as two frames; count the downstream copy only.
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        now = round(data.timestamp / 1_000_000, 1)  # pipeline clock, ns -> ms
        if isinstance(frame, UserStartedSpeakingFrame):
            tracker.turns.append(TurnTimings(turn=len(tracker.turns) + 1))
            return
        turn = tracker.current
        if turn is None:
            return  # the greeting: no user turn yet
        if isinstance(frame, VADUserStoppedSpeakingFrame) and turn.llm_request is None:
            turn.user_speech_end = round(now - frame.stop_secs * 1000, 1)
        elif isinstance(frame, TranscriptionFrame) and isinstance(data.source, STTService):
            turn.stt_final = now
        elif isinstance(frame, UserStoppedSpeakingFrame):
            turn.turn_end = now
        elif isinstance(frame, LLMContextFrame) and isinstance(data.source, LLMUserAggregator):
            # The inference trigger can precede UserStoppedSpeakingFrame. Only the first hop is
            # observed (aggregator -> filler); the filler adds no measurable delay.
            turn.llm_request = turn.llm_request or now
        elif turn.llm_request is None or turn.turn_end is None:
            return  # back-channels and other output while the caller is still talking
        elif isinstance(frame, LLMTextFrame) and isinstance(data.source, LLMService):
            turn.llm_first_token = turn.llm_first_token or now
        elif isinstance(frame, (LLMTextFrame, TTSSpeakFrame)) and isinstance(
            data.destination, TTSService
        ):
            turn.tts_text_in = turn.tts_text_in or now
        elif isinstance(frame, TTSAudioRawFrame) and isinstance(data.source, TTSService):
            turn.tts_first_byte = turn.tts_first_byte or now
        elif isinstance(frame, BotStartedSpeakingFrame) and not turn.complete:
            turn.first_audio_out = now
            if tracker.on_turn_complete is not None:
                await tracker.on_turn_complete(turn)
