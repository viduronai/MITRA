from __future__ import annotations

from typing import Any

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    Frame,
    LLMContextFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from mitra_voice.latency import LatencyTracker, TurnTimings, derive, percentile, summarize
from mitra_voice.pack import FIXTURES_DIR, load_fixture
from mitra_voice.providers.mock_llm import MockLLMService
from mitra_voice.providers.mock_stt import SCRIPTS, MockSTTService
from mitra_voice.providers.mock_tts import MockTTSService


def test_derive_stage_durations() -> None:
    t = TurnTimings(
        turn=1,
        user_speech_end=1000,
        stt_final=1150,
        turn_end=1200,
        llm_request=1190,
        llm_first_token=1440,
        tts_text_in=1450,
        tts_first_byte=1540,
        first_audio_out=1600,
    )
    assert derive(t) == {
        "stt_ms": 150,
        "turn_detect_ms": 200,
        "llm_ttft_ms": 250,
        "tts_ttfb_ms": 90,
        "first_audio_ms": 600,
    }
    assert derive(TurnTimings(turn=2))["first_audio_ms"] is None


def test_percentile_interpolates() -> None:
    assert percentile([5], 95) == 5
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([100, 200, 300, 400, 500], 95) == 480
    assert percentile([300, 100, 200], 0) == 100
    with pytest.raises(ValueError, match="empty"):
        percentile([], 50)
    with pytest.raises(ValueError, match="q must"):
        percentile([1], 101)


def test_summary_uses_complete_turns_only() -> None:
    turns = [
        TurnTimings(turn=i, user_speech_end=0, first_audio_out=ms)
        for i, ms in enumerate([500, 600, 700, 900], start=1)
    ]
    turns.append(TurnTimings(turn=5, user_speech_end=0))  # abandoned: never answered
    s = summarize(turns)
    assert s["first_audio_ms"] == {"n": 4, "p50": 650.0, "p95": 870.0}
    assert s["llm_ttft_ms"] == {"n": 0, "p50": None, "p95": None}


class _Proc(FrameProcessor):
    pass


async def test_observer_records_one_turn_from_frame_pushes() -> None:
    pack = load_fixture(FIXTURES_DIR / "sunrise-clinic.json")
    stt, llm, tts = MockSTTService(SCRIPTS["clinic"]), MockLLMService(pack), MockTTSService()
    user = LLMContextAggregatorPair(LLMContext()).user()
    other, out = _Proc(), _Proc()
    completed: list[TurnTimings] = []

    async def on_complete(turn: TurnTimings) -> None:
        completed.append(turn)

    tracker = LatencyTracker(on_turn_complete=on_complete)
    observer = tracker.observer()

    async def push(ms: float, frame: Frame, src: Any = None, dst: Any = None) -> None:
        await observer.on_push_frame(
            FramePushed(
                source=src or other,
                destination=dst or other,
                frame=frame,
                direction=FrameDirection.DOWNSTREAM,
                timestamp=int(ms * 1_000_000),
            )
        )

    await push(0, BotStartedSpeakingFrame())  # greeting: no turn yet, ignored
    await push(100, UserStartedSpeakingFrame())
    await push(1400, VADUserStoppedSpeakingFrame(stop_secs=0.2))
    await push(1300, BotStartedSpeakingFrame())  # back-channel mid-turn: ignored
    await push(1450, TranscriptionFrame("fee?", "", "now"), src=stt)
    await push(1500, LLMContextFrame(LLMContext()), src=user)
    await push(1510, UserStoppedSpeakingFrame())
    await push(1760, LLMTextFrame("The"), src=llm)
    await push(1770, LLMTextFrame("The fee is ₹500."), dst=tts)
    await push(1860, TTSAudioRawFrame(b"\0\0", 24000, 1), src=tts)
    await push(1880, BotStartedSpeakingFrame(), dst=out)
    await push(1990, BotStartedSpeakingFrame(), dst=out)  # later chunks don't move it

    assert len(completed) == 1
    d = derive(completed[0])
    assert d == {
        "stt_ms": 250,
        "turn_detect_ms": 310,
        "llm_ttft_ms": 260,
        "tts_ttfb_ms": 90,
        "first_audio_ms": 680,
    }
    tracker.turns.append(TurnTimings(turn=2))
    tracker.mark_reply_interrupted()
    assert tracker.turns[0].interrupted
