"""Filler and back-channel hooks around the human-layer policies."""

from __future__ import annotations

import time

from pipecat.frames.frames import (
    InterimTranscriptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import SleepFrame, run_test

from mitra_voice.call_context import CallContext
from mitra_voice.latency import LatencyTracker, TurnTimings
from mitra_voice.processors.backchannel import BackchannelPlayer, UserSpeechState, UserSpeechTap
from mitra_voice.processors.filler import PRIOR_ANSWER_MS, FillerProcessor, LatencyPredictor
from mitra_voice.processors.reply import ReplyLog
from mitra_voice.processors.speakable import (
    SpeakableProcessor,
    split_first_words,
    split_sentences,
)
from mitra_voice.providers.clips import ToneClips


def _context(text: str) -> LLMContextFrame:
    return LLMContextFrame(LLMContext(messages=[{"role": "user", "content": text}]))


def test_predictor_uses_measured_median_plus_tool_time() -> None:
    tracker = LatencyTracker()
    predictor = LatencyPredictor(tracker, tool_latency_ms=600)
    assert predictor.expected_ms("What is the fee?") == PRIOR_ANSWER_MS
    assert predictor.expected_ms("Book me for tomorrow") == PRIOR_ANSWER_MS + 600
    for i, (ttft, ttfb) in enumerate([(200, 80), (300, 100), (900, 100)], start=1):
        tracker.turns.append(
            TurnTimings(
                turn=i,
                user_speech_end=0,
                llm_request=0,
                llm_first_token=ttft,
                tts_text_in=0,
                tts_first_byte=ttfb,
                first_audio_out=1,
            )
        )
    assert predictor.expected_ms("fee?") == 400


async def test_filler_is_spoken_before_a_slow_tool_turn_only() -> None:
    fillers: list[str] = []

    async def on_filler(text: str) -> None:
        fillers.append(text)

    processor = FillerProcessor(
        LatencyPredictor(LatencyTracker(), tool_latency_ms=600),
        call=CallContext(session_id="s", language="en"),
        on_filler=on_filler,
    )
    down, _ = await run_test(
        processor,
        frames_to_send=[_context("What is the fee?"), _context("Book me for tomorrow evening.")],
    )
    kinds = [type(f) for f in down]
    assert kinds == [LLMContextFrame, TTSSpeakFrame, LLMContextFrame]
    filler = down[1]
    assert isinstance(filler, TTSSpeakFrame)
    assert not filler.append_to_context
    assert fillers == [filler.text]
    # The filler follows the caller's current language.
    assert filler.text in ("Sure, one second.", "Let me check.", "Okay, just a moment.")


async def test_speakable_chunks_sentences_and_normalises() -> None:
    reply = ReplyLog()
    sentences: list[str] = []

    async def on_sentence(text: str) -> None:
        sentences.append(text)

    tokens = ["The consultation ", "fee is ₹5", "00. We're at Road No. ", "3, Banjara Hills."]
    down, _ = await run_test(
        SpeakableProcessor(
            reply,
            call=CallContext(session_id="s", language="en"),
            tts_language="en",
            on_sentence=on_sentence,
        ),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            *(LLMTextFrame(t) for t in tokens),
            LLMFullResponseEndFrame(),
        ],
    )
    assert sentences[0] == "The consultation fee is five hundred rupees."
    assert sentences[1].startswith("We're at Road No.")
    assert "three" in sentences[1]
    assert [f.text for f in down if isinstance(f, LLMTextFrame)] == [s + " " for s in sentences]
    assert reply.text == " ".join(sentences)


def test_split_sentences_keeps_abbreviations_together() -> None:
    done, rest = split_sentences("Plot 12, Road No. 3. Near Dr. Rao's clinic. And")
    assert done == ["Plot 12, Road No. 3.", "Near Dr. Rao's clinic."]
    assert rest == "And"


async def test_backchannel_plays_a_quiet_clip_in_a_long_turn() -> None:
    state = UserSpeechState()
    tokens: list[str] = []

    async def on_token(token: str) -> None:
        tokens.append(token)

    player = BackchannelPlayer(
        state,
        CallContext(session_id="s", language="en"),
        ToneClips(24000),
        seed=1,
        on_token=on_token,
    )
    tap = UserSpeechTap(state)

    # Drive the shared state through the tap, then let the player poll during a pause.
    await run_test(
        tap,
        frames_to_send=[
            UserStartedSpeakingFrame(),
            VADUserStartedSpeakingFrame(),
            InterimTranscriptionFrame("so my mother has had a fever since", "", "now"),
        ],
    )
    state.turn_started_at = time.monotonic() - 5.0  # the caller has been talking for 5 s
    await run_test(tap, frames_to_send=[VADUserStoppedSpeakingFrame(stop_secs=0.2)])
    state.in_turn = True

    down, _ = await run_test(player, frames_to_send=[SleepFrame(sleep=0.35)])
    clips = [f for f in down if isinstance(f, OutputAudioRawFrame)]
    assert len(clips) == 1
    assert len(tokens) == 1
    assert tokens[0] in ("mm-hmm", "okay", "right")
    samples = memoryview(clips[0].audio).cast("h")
    assert max(abs(s) for s in samples) < 0.1 * 32767  # quiet, well below speech level


def test_long_clauses_flush_early_but_numbers_never_split() -> None:
    done, rest = split_sentences("Our clinic timings are Monday to Saturday, 10 AM to 1 PM and")
    assert done == ["Our clinic timings are Monday to Saturday,"]
    assert rest == "10 AM to 1 PM and"
    done, rest = split_sentences("Yes, the total is ₹1,00,000 for the full package; ")
    assert done == ["Yes, the total is ₹1,00,000 for the full package;"]


def test_early_first_chunk_never_cuts_after_a_number() -> None:
    assert split_first_words("The consultation fee for a ", 5) == ("The consultation fee for a", "")
    assert split_first_words("The fee is four", 5) is None  # too few words
    assert split_first_words("The fee for you is ₹65 ", 5) is None  # "₹65 | lakh" stays whole
    assert split_first_words("We open at 10 ", 3) is None  # "10 | AM" stays whole
    assert split_first_words("The consultation fee for a", 5) is None  # last word may continue
    assert split_first_words("The consultation fee for a ", 0) is None  # disabled


async def test_filler_flag_tells_the_brain_a_filler_was_spoken() -> None:
    call = CallContext(session_id="s", language="en")
    processor = FillerProcessor(LatencyPredictor(LatencyTracker(), tool_latency_ms=600), call=call)
    await run_test(processor, frames_to_send=[_context("Book me for tomorrow evening.")])
    assert call.filler_spoken
    await run_test(processor, frames_to_send=[_context("What is the fee?")])
    assert not call.filler_spoken
