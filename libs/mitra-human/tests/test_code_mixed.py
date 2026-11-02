"""Code-mixed speech: Tenglish ("te-en") and Hinglish ("hi-en").

Founder rule: in code-mixed speech, times, dates and phone numbers are said in English,
while amounts and plain numbers stay Telugu/Hindi.
"""

from __future__ import annotations

import pytest

from mitra_human import (
    BackchannelPolicy,
    FillerPolicy,
    Lang,
    honorific,
    number_to_words,
    speakable,
    spell_digits,
    spell_email,
    spell_phone,
)
from mitra_human.backchannel import TOKENS, looks_mid_explanation
from mitra_human.filler import fillers

PHONE_EN = "nine eight seven six five, four three two one zero"

TENGLISH: list[tuple[str, str]] = [
    # times: English words, English time-of-day word, కి kept as its own word
    ("రేపు 6:30 pm కి slot ఉంది", "రేపు evening six thirty కి slot ఉంది"),
    ("రేపు evening 6:30 pm కి", "రేపు evening six thirty కి"),
    ("ఎల్లుండి morning 11 am కి కూడా ఉంది", "ఎల్లుండి morning eleven కి కూడా ఉంది"),
    ("సాయంత్రం 6:30 pm కి", "సాయంత్రం six thirty కి"),
    ("6:05 am", "morning six oh five"),
    ("18:15", "evening six fifteen"),
    ("9:30", "nine thirty"),
    ("12 pm", "afternoon twelve"),
    ("12 am", "night twelve"),
    ("9 am – 8 pm", "morning nine నుండి night eight వరకు"),
    ("9-11 am", "morning nine నుండి eleven వరకు"),
    ("morning 9-11 am", "morning nine నుండి eleven వరకు"),
    # phones and digit codes in English
    ("మీ number 9876543210, correct ఏనా?", f"మీ number {PHONE_EN}, correct ఏనా?"),
    ("+91 98765 43210 కి call చేయండి", f"{PHONE_EN} కి call చేయండి"),
    ("OTP 0123 చెప్పండి", "OTP zero one two three చెప్పండి"),
    # dates and weekdays in English, native connectors
    ("18 Oct న appointment", "eighteenth October న appointment"),
    ("2026-10-18", "eighteenth October two thousand twenty-six"),
    ("Sat, 18 Oct", "Saturday, eighteenth October"),
    ("Mon–Sat open", "Monday నుండి Saturday వరకు open"),
    ("Monday holiday", "Monday holiday"),
    # amounts and plain numbers stay Telugu, with the usual forms and కి merge
    ("Consultation fees ₹500", "Consultation fees ఐదు వందల రూపాయలు"),
    ("₹1500 కి", "పదిహేను వందల రూపాయలకి"),
    ("₹2.5 crore", "రెండున్నర కోట్ల రూపాయలు"),
    ("5 minutes లో", "ఐదు minutes లో"),
    ("500 కి", "ఐదు వందలకి"),
    ("50% off", "యాభై శాతం off"),
]


@pytest.mark.parametrize(("text", "expected"), TENGLISH)
def test_tenglish(text: str, expected: str) -> None:
    assert speakable(text, "te-en") == expected


HINGLISH: list[tuple[str, str]] = [
    # times: English words + बजे (added once, never doubled)
    ("कल 6:30 pm एक slot free है", "कल evening six thirty बजे एक slot free है"),
    ("कल evening 6:30 pm बजे", "कल evening six thirty बजे"),
    ("परसों 11 am मिल जाएगा", "परसों morning eleven बजे मिल जाएगा"),
    ("शाम 6:30 pm", "शाम six thirty बजे"),
    ("18:15", "evening six fifteen बजे"),
    ("12 am", "night twelve बजे"),
    ("9 am – 8 pm", "morning nine बजे से night eight बजे तक"),
    ("9-11 am", "morning nine बजे से eleven बजे तक"),
    # phones, dates, weekdays
    ("आपका number +91 98765 43210 है", f"आपका number {PHONE_EN} है"),
    ("18 Oct को", "eighteenth October को"),
    ("Mon–Sat", "Monday से Saturday तक"),
    # amounts stay Hindi
    ("fees ₹500 है", "fees पाँच सौ रुपये है"),
    ("₹1,20,000", "एक लाख बीस हज़ार रुपये"),
    ("₹2.5 crore", "ढाई करोड़ रुपये"),
    ("2-3 दिन", "दो से तीन दिन"),
]


@pytest.mark.parametrize(("text", "expected"), HINGLISH)
def test_hinglish(text: str, expected: str) -> None:
    assert speakable(text, "hi-en") == expected


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("6:30 pm", "te", "సాయంత్రం ఆరున్నర"),
        ("6:30 pm", "hi", "शाम साढ़े छह बजे"),
        ("6:30 pm", "en", "six thirty in the evening"),
        ("9876543210", "te", "తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు, నాలుగు మూడు రెండు ఒకటి సున్నా"),
        ("18 Oct", "hi", "अठारह अक्टूबर"),
    ],
)
def test_pure_languages_unchanged(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


def test_quarters_flag_ignored_in_code_mix() -> None:
    assert speakable("6:15 pm కి", "te-en", colloquial_quarters=True) == "evening six fifteen కి"


@pytest.mark.parametrize("lang", ["te-en", "hi-en"])
def test_helpers_read_digits_in_english(lang: Lang) -> None:
    assert spell_phone("9876543210", lang) == PHONE_EN
    assert spell_digits("4821", lang) == "four eight two one"
    assert spell_email("ravi.k@gmail.com", lang) == "ravi dot k at gmail dot com"


def test_helpers_keep_native_numbers_and_honorifics() -> None:
    assert number_to_words(500, "te-en") == "ఐదు వందలు"
    assert number_to_words(500, "hi-en") == "पाँच सौ"
    assert honorific("Ravi", "te-en") == "Ravi garu"
    assert honorific("Ravi", "hi-en") == "Ravi ji"


class TestCodeMixedPolicies:
    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("te-en", "నేను last week slot book చేశాను then మా brother call చేశాడు,"),
            ("hi-en", "मैंने last week slot book किया था और फिर मेरे brother का call आया,"),
        ],
    )
    def test_backchannel_tokens(self, lang: Lang, text: str) -> None:
        assert looks_mid_explanation(text, lang)
        token = BackchannelPolicy(lang, seed=3).on_user_speech(5000, text, 400)
        assert token in TOKENS[lang]

    @pytest.mark.parametrize(
        ("lang", "text"),
        [
            ("te-en", "నేను last week book చేశాను but can you change it"),
            ("te-en", "నేను last week book చేశాను ఎప్పుడు వస్తుంది"),
            ("hi-en", "मैंने last week book किया था but kab deliver hoga"),
            ("hi-en", "मैंने last week book किया था what is the status"),
        ],
    )
    def test_questions_in_either_language_block_backchannels(self, lang: Lang, text: str) -> None:
        assert BackchannelPolicy(lang, seed=3).on_user_speech(5000, text, 400) is None

    @pytest.mark.parametrize("lang", ["te-en", "hi-en"])
    def test_fillers_are_english_leaning(self, lang: Lang) -> None:
        p = FillerPolicy(lang, seed=2)
        said = [p.filler_for(1500, t) for t in range(0, 20, 2)]
        assert None not in said
        assert set(said) <= set(fillers(lang))
        assert any("minute" in f or "second" in f for f in fillers(lang))

    def test_hinglish_filler_gender(self) -> None:
        assert "check करती हूँ…" in fillers("hi-en", "female")
        assert "check करता हूँ…" in fillers("hi-en", "male")
        assert fillers("te-en", "male") == fillers("te-en", "female")
