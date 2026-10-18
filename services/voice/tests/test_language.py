"""Caller-language detection and its effect on the pipeline."""

from __future__ import annotations

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.tests.utils import run_test
from pipecat.transcriptions.language import Language

from mitra_voice.call_context import (
    CallContext,
    detect_caller_language,
    stt_lang,
    stt_lock_language,
)
from mitra_voice.pack import Lang
from mitra_voice.processors.language import LanguageTracker
from mitra_voice.processors.reply import ReplyLog
from mitra_voice.processors.speakable import SpeakableProcessor


@pytest.mark.parametrize(
    ("text", "code", "current", "expected"),
    [
        # Real Sarvam "codemix" transcripts from the live probe.
        ("consultation fee ఎంత?", "te-IN", "en", "te"),
        ("क्या मैं कल शाम के लिए appointment book कर सकता हूँ?", "hi-IN", "te", "hi"),
        ("What are your clinic timings?", "en-IN", "te", "en"),
        ("Parking ఉందా?", "te-IN", "en", "te"),
        # Native script wins over a wrong language code (one word misread as Malayalam).
        ("నమస్కారం.", "ml-IN", "en", "te"),
        # Unsupported language code on Latin text: English.
        ("Hello there sir", "ta-IN", "te", "en"),
        # Romanised Hindi: trust the STT code.
        ("kal shaam ko aa sakta hoon", "hi-IN", "en", "hi"),
        # One Latin word is not enough evidence to switch.
        ("okay", "en-IN", "te", "te"),
        ("haan", "hi-IN", "en", "en"),
        ("", "en-IN", "hi", "hi"),
    ],
)
def test_detect_caller_language(text: str, code: str, current: Lang, expected: Lang) -> None:
    assert detect_caller_language(text, code, current) == expected


def test_locked_stt_reads_latin_as_english_and_stays_in_the_pack() -> None:
    # Pinned to te-IN, Sarvam returned Hindi audio as English text, tagged te-IN.
    kw = {"allowed": ("te", "en"), "stt_locked": True}
    assert detect_caller_language("Can I book for tomorrow?", "te-IN", "te", **kw) == "en"  # type: ignore[arg-type]
    assert detect_caller_language("Parking ఉందా?", "te-IN", "en", **kw) == "te"  # type: ignore[arg-type]
    # Devanagari in a te/en pack: not a language we can answer in, keep the current one.
    assert detect_caller_language("कितना लगेगा?", "hi-IN", "te", **kw) == "te"  # type: ignore[arg-type]
    # Auto-detect: an out-of-pack detection on Latin text falls back to English, if allowed.
    assert detect_caller_language("fees kitni hai", "hi-IN", "te", allowed=("te", "en")) == "en"


def test_stt_lock_choice() -> None:
    assert stt_lock_language(["te", "en"]) == "te"
    assert stt_lock_language(["en", "hi"]) == "hi"
    assert stt_lock_language(["en"]) == "en"
    assert stt_lock_language(["te", "hi", "en"]) is None


def test_stt_codes() -> None:
    assert stt_lang("te-IN") == "te"
    assert stt_lang(Language.HI_IN.value) == "hi"
    assert stt_lang("ml-IN") is None
    assert stt_lang(None) is None


async def test_call_context_switches_and_notifies() -> None:
    seen: list[Lang] = []

    async def hook(lang: Lang) -> None:
        seen.append(lang)

    call = CallContext(session_id="s", language="te")
    call.on_language_change.append(hook)
    assert not await call.observe_utterance("ఫీజు ఎంత?", "te-IN")
    assert await call.observe_utterance("What are your timings?", "en-IN")
    assert await call.observe_utterance("कितना लगेगा?", "hi-IN")
    assert call.language == "hi"
    assert call.language_history == ["te", "en", "hi"]
    assert seen == ["en", "hi"]


async def test_tracker_updates_language_from_transcripts() -> None:
    call = CallContext(session_id="s", language="te")
    frames = [TranscriptionFrame("What are your timings?", "", "now", Language.EN_IN)]
    down, _ = await run_test(LanguageTracker(call), frames_to_send=frames)
    assert call.language == "en"
    assert any(isinstance(f, TranscriptionFrame) for f in down)  # passed through untouched


async def test_tts_language_follows_the_caller() -> None:
    call = CallContext(session_id="s", language="te")
    processor = SpeakableProcessor(ReplyLog(), call=call, tts_language="te")
    await call.observe_utterance("What is the fee?", "en-IN")
    down, _ = await run_test(
        processor,
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("The fee is ₹500."),
            LLMFullResponseEndFrame(),
        ],
    )
    updates = [f for f in down if isinstance(f, TTSUpdateSettingsFrame)]
    assert len(updates) == 1
    assert updates[0].delta is not None
    assert updates[0].delta.language == Language.EN_IN
    # The update reaches the TTS before the reply it applies to.
    first_text = next(i for i, f in enumerate(down) if isinstance(f, LLMTextFrame))
    assert down.index(updates[0]) < first_text
    texts = [f.text for f in down if isinstance(f, LLMTextFrame)]
    assert texts == ["The fee is five hundred rupees. "]


async def test_no_tts_update_when_language_is_unchanged() -> None:
    call = CallContext(session_id="s", language="te")
    down, _ = await run_test(
        SpeakableProcessor(ReplyLog(), call=call, tts_language="te"),
        frames_to_send=[LLMFullResponseStartFrame(), LLMFullResponseEndFrame()],
    )
    assert not any(isinstance(f, TTSUpdateSettingsFrame) for f in down)
