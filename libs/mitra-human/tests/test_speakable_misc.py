"""Phones, ranges, ordinals, percentages, Telugu numeral forms and untouched text."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mitra_human import Lang, speakable

LANGS: list[Lang] = ["en", "hi", "te"]

PHONES: list[tuple[str, Lang, str]] = [
    ("+91 98765 43210", "en", "nine eight seven six five, four three two one zero"),
    ("9876543210", "en", "nine eight seven six five, four three two one zero"),
    ("+919876543210", "en", "nine eight seven six five, four three two one zero"),
    ("098765 43210", "en", "nine eight seven six five, four three two one zero"),
    ("987-654-3210", "en", "nine eight seven, six five four, three two one zero"),
    ("1800-123-4567", "en", "one eight zero zero, one two three, four five six seven"),
    ("040-23456789", "en", "zero four zero, two three four five, six seven eight nine"),
    ("+1 415 555 0123", "en", "plus one, four one five, five five five, zero one two three"),
    ("Call 9876543210.", "en", "Call nine eight seven six five, four three two one zero."),
    ("+91 98765 43210", "hi", "नौ आठ सात छह पाँच, चार तीन दो एक ज़ीरो"),
    ("+91 98765 43210", "te", "తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు, నాలుగు మూడు రెండు ఒకటి సున్నా"),
    (
        "98765 43210 కి కాల్ చేయండి",
        "te",
        "తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు, నాలుగు మూడు రెండు ఒకటి సున్నాకి కాల్ చేయండి",
    ),
]


@pytest.mark.parametrize(("text", "lang", "expected"), PHONES)
def test_phones(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


MISC: list[tuple[str, Lang, str]] = [
    # ranges
    ("5-10 minutes", "en", "five to ten minutes"),
    ("2 to 3 days", "en", "two to three days"),
    ("2-3 दिन", "hi", "दो से तीन दिन"),
    ("5-10 రోజులు", "te", "ఐదు నుండి పది రోజులు"),
    # ordinals
    ("1st floor", "en", "first floor"),
    ("2nd", "en", "second"),
    ("21st", "en", "twenty-first"),
    ("3rd", "hi", "तीसरा"),
    ("1st", "te", "మొదటి"),
    ("2nd", "te", "రెండవ"),
    # percent
    ("50% off", "en", "fifty percent off"),
    ("12.5%", "en", "twelve point five percent"),
    ("50% छूट", "hi", "पचास परसेंट छूट"),
    ("10% తగ్గింపు", "te", "పది శాతం తగ్గింపు"),
    ("1%", "te", "ఒక శాతం"),
    # decimals, digit strings
    ("3.5", "en", "three point five"),
    ("3.5", "hi", "तीन पॉइंट पाँच"),
    ("OTP 0123", "en", "OTP zero one two three"),
    ("12345678901", "en", "one two three four five six seven eight nine zero one"),
    # Telugu numeral forms decided by the following word
    ("500 రూపాయలు", "te", "ఐదు వందల రూపాయలు"),
    ("1 రోజు", "te", "ఒక రోజు"),
    ("21 రోజులు", "te", "ఇరవై ఒక్క రోజులు"),
    ("2000 మంది", "te", "రెండు వేల మంది"),
    ("5 minutes", "te", "ఐదు minutes"),
    ("500 కి", "te", "ఐదు వందలకి"),
    ("1000 కి", "te", "వెయ్యికి"),
    ("200 వరకు", "te", "రెండు వందల వరకు"),
    ("1 వరకు", "te", "ఒకటి వరకు"),
    ("5 ఉన్నాయి", "te", "ఐదు ఉన్నాయి"),
    ("500.", "te", "ఐదు వందలు."),
    ("అక్టోబర్ 18", "te", "అక్టోబర్ పద్దెనిమిది"),
    ("18 अक्टूबर", "hi", "अठारह अक्टूबर"),
    # native digits
    ("५०० रुपये", "hi", "पाँच सौ रुपये"),
    ("౫౦౦ రూపాయలు", "te", "ఐదు వందల రూపాయలు"),
]


@pytest.mark.parametrize(("text", "lang", "expected"), MISC)
def test_misc(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


UNTOUCHED = [
    "Visit https://mitra.in/book?slot=5 today.",
    "Mail ravi.k99@gmail.com for details.",
    "See www.example.com/page/2",
    "Our site is mitra.co.in, and it is open.",
    "COVID-19 rules apply.",
    "Room A1 and 4G network",
    "24/7",
    "Call me tomorrow, okay?",
    "",
    "नमस्ते, मैं आपकी क्या मदद कर सकती हूँ?",
    "నమస్కారం, మీకు ఎలా సహాయం చేయగలను?",
]


@pytest.mark.parametrize("lang", ["en", "hi", "te"])
@pytest.mark.parametrize("text", UNTOUCHED)
def test_untouched(text: str, lang: Lang) -> None:
    assert speakable(text, lang) == text


def test_url_protection_with_numbers_around() -> None:
    assert (
        speakable("Pay ₹500 at https://pay.mitra.in/500 now", "en")
        == "Pay five hundred rupees at https://pay.mitra.in/500 now"
    )


def test_mixed_sentence_en() -> None:
    text = "Your appointment is on Sat, 18 Oct at 6:15 pm. Fee ₹1,200. Call 98765 43210."
    assert speakable(text, "en") == (
        "Your appointment is on Saturday, eighteenth October at six fifteen in the evening."
        " Fee one thousand two hundred rupees."
        " Call nine eight seven six five, four three two one zero."
    )


def test_mixed_sentence_hi() -> None:
    text = "आपकी अपॉइंटमेंट 18 Oct को 6:15 pm पर है, फ़ीस ₹1,200 है।"
    assert speakable(text, "hi") == (
        "आपकी अपॉइंटमेंट अठारह अक्टूबर को शाम सवा छह बजे पर है, फ़ीस एक हज़ार दो सौ रुपये है।"
    )


def test_mixed_sentence_te() -> None:
    text = "మీ అపాయింట్‌మెంట్ 18 Oct న 6 pm కి, ఫీజు ₹1,200."
    assert speakable(text, "te") == (
        "మీ అపాయింట్‌మెంట్ అక్టోబర్ పద్దెనిమిది న సాయంత్రం ఆరు గంటలకి, ఫీజు పన్నెండు వందల రూపాయలు."
    )


def test_rejects_unknown_language() -> None:
    with pytest.raises(ValueError, match="unsupported language"):
        speakable("5", "ta")  # type: ignore[arg-type]


def test_idempotent_on_output() -> None:
    once = speakable("₹1,20,000 on 18 Oct at 6 pm, call 9876543210", "en")
    assert speakable(once, "en") == once


_FUZZ_ALPHABET = list("0123456789 ,.:/-–₹%+@ap mRsINlakhcroeMonSatOct") + list("रुपयेలక్షకి")


@settings(max_examples=300)
@given(st.text(alphabet=st.sampled_from(_FUZZ_ALPHABET), max_size=60), st.sampled_from(LANGS))
def test_fuzz_never_raises_and_leaves_no_sentinels(text: str, lang: Lang) -> None:
    out = speakable(text, lang)
    assert not any(0xE000 <= ord(ch) <= 0xF8FF for ch in out)
