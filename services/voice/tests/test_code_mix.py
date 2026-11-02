"""Code-mixed callers (Tenglish / Hinglish): detection and the human-layer language they drive."""

from __future__ import annotations

from pipecat.frames.frames import LLMContextFrame, TTSSpeakFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import run_test

from mitra_human.backchannel import TOKENS
from mitra_human.filler import fillers
from mitra_voice.call_context import CallContext, has_latin_words, human_lang_for
from mitra_voice.config import Settings
from mitra_voice.latency import LatencyTracker
from mitra_voice.pack import FIXTURES_DIR, load_fixture
from mitra_voice.pipeline import _fillers_to_prerender, human_langs
from mitra_voice.processors.filler import FillerProcessor, LatencyPredictor
from mitra_voice.processors.speakable import spoken_form
from mitra_voice.providers import resolve_providers
from mitra_voice.session import CallSession


def test_latin_words_mark_mixing() -> None:
    assert has_latin_words("consultation fee ఎంత?")
    assert has_latin_words("appointment book कर सकता हूँ")
    assert not has_latin_words("ఫీజు ఎంత అవుతుంది?")
    assert not has_latin_words("₹500, 9 ఎ")  # numbers and single letters are not words


def test_human_lang_codes() -> None:
    assert human_lang_for("te", True) == "te-en"
    assert human_lang_for("hi", True) == "hi-en"
    assert human_lang_for("en", True) == "en"
    assert human_lang_for("te", False) == "te"


async def test_code_mixing_is_a_sticky_caller_trait() -> None:
    call = CallContext(session_id="s", language="te", allowed=("te", "en"))
    await call.observe_utterance("ఫీజు ఎంత?", "te-IN")
    assert call.human_lang == "te"
    await call.observe_utterance("consultation fee ఎంత?", "te-IN")  # Tenglish
    assert call.human_lang == "te-en"
    await call.observe_utterance("సరే.", "te-IN")  # too short to say they stopped mixing
    assert call.human_lang == "te-en"
    await call.observe_utterance("What are your timings?", "en-IN")  # English: base switches
    assert (call.language, call.human_lang) == ("en", "en")
    await call.observe_utterance("Parking ఉందా?", "te-IN")  # back to Telugu, still mixing
    assert call.human_lang == "te-en"
    await call.observe_utterance("రేపు సాయంత్రం రావచ్చా అండి?", "te-IN")  # clearly native-only
    assert call.human_lang == "te"


def test_spoken_form_uses_code_mixed_rules_only_for_the_callers_language() -> None:
    mixed = spoken_form("Clinic Monday నుండి Saturday వరకు, 6:30 pm కి close ₹500 fee", "te", True)
    assert "ఐదు వందల రూపాయలు" in mixed  # amounts stay native
    assert "six thirty" in mixed  # times in English
    assert "₹" not in mixed
    native = spoken_form("ఫీజు ₹500", "te", False)
    assert "ఐదు వందల రూపాయలు" in native
    english = spoken_form("The fee is ₹500.", "te", True)  # Latin-only reply reads as English
    assert "five hundred rupees" in english


async def test_filler_speaks_tenglish_to_a_code_mixer() -> None:
    call = CallContext(session_id="s", language="te", code_mixed=True)
    processor = FillerProcessor(LatencyPredictor(LatencyTracker(), tool_latency_ms=600), call=call)
    frame = LLMContextFrame(LLMContext(messages=[{"role": "user", "content": "book చేయండి"}]))
    down, _ = await run_test(processor, frames_to_send=[frame])
    spoken = [f.text for f in down if isinstance(f, TTSSpeakFrame)]
    assert spoken
    assert spoken[0] in fillers("te-en", "female")


def test_prerender_covers_mixed_variants() -> None:
    session = CallSession(
        scenario="clinic",
        pack=load_fixture(FIXTURES_DIR / "sunrise-clinic.json"),  # te + en
        providers=resolve_providers(Settings()),
    )
    assert human_langs(session.pack.languages) == ["te", "te-en", "en"]
    langs = {lang for lang, _ in _fillers_to_prerender(session)}
    assert langs == {"te", "te-en", "en"}
    assert len(_fillers_to_prerender(session)) == 9
    assert "okay" in TOKENS["te-en"]  # mixed back-channels are rendered too (BackchannelClips)
