"""Times, dates and weekday ranges."""

from __future__ import annotations

import pytest

from mitra_human import Lang, speakable

TIMES: list[tuple[str, Lang, str]] = [
    # English
    ("6:15 pm", "en", "six fifteen in the evening"),
    ("6:15pm", "en", "six fifteen in the evening"),
    ("6.15 PM", "en", "six fifteen in the evening"),
    ("6 p.m.", "en", "six in the evening."),
    ("6 p.m. tomorrow", "en", "six in the evening tomorrow"),
    ("18:15", "en", "six fifteen in the evening"),
    ("18:15 hrs", "en", "six fifteen in the evening"),
    ("6:05 am", "en", "six oh five in the morning"),
    ("9:30 am", "en", "nine thirty in the morning"),
    ("09:30", "en", "nine thirty in the morning"),
    ("9:30", "en", "nine thirty"),
    ("2:45 pm", "en", "two forty-five in the afternoon"),
    ("10 pm", "en", "ten at night"),
    ("00:30", "en", "twelve thirty at night"),
    ("12 pm", "en", "twelve noon"),
    ("12 am", "en", "twelve midnight"),
    ("9 am – 9 pm", "en", "nine in the morning to nine at night"),
    ("10:30 am to 7 pm", "en", "ten thirty in the morning to seven in the evening"),
    ("9-11 am", "en", "nine to eleven in the morning"),
    ("11-2 pm", "en", "eleven in the morning to two in the afternoon"),
    ("09:00-18:00", "en", "nine in the morning to six in the evening"),
    ("Open at 10am.", "en", "Open at ten in the morning."),
    # Hindi
    ("6:15 pm", "hi", "शाम सवा छह बजे"),
    ("6:30 pm", "hi", "शाम साढ़े छह बजे"),
    ("6:45 pm", "hi", "शाम पौने सात बजे"),
    ("6 pm", "hi", "शाम छह बजे"),
    ("6:10 pm", "hi", "शाम छह बजकर दस मिनट"),
    ("18:15", "hi", "शाम सवा छह बजे"),
    ("9 am", "hi", "सुबह नौ बजे"),
    ("1:30 pm", "hi", "दोपहर डेढ़ बजे"),
    ("2:30 pm", "hi", "दोपहर ढाई बजे"),
    ("12:45 pm", "hi", "दोपहर पौने एक बजे"),
    ("10 pm", "hi", "रात दस बजे"),
    ("12 pm", "hi", "दोपहर बारह बजे"),
    ("12 am", "hi", "रात बारह बजे"),
    ("9 am – 9 pm", "hi", "सुबह नौ बजे से रात नौ बजे तक"),
    ("9-11 am", "hi", "सुबह नौ बजे से ग्यारह बजे तक"),
    # Telugu
    ("6:15 pm", "te", "సాయంత్రం ఆరు పదిహేను"),
    ("6:30 pm", "te", "సాయంత్రం ఆరున్నర"),
    ("6 pm", "te", "సాయంత్రం ఆరు గంటలు"),
    ("1 pm", "te", "మధ్యాహ్నం ఒంటి గంట"),
    ("1:30 pm", "te", "మధ్యాహ్నం ఒకటిన్నర"),
    ("6:05 am", "te", "ఉదయం ఆరు గంటల ఐదు నిమిషాలు"),
    ("10 pm", "te", "రాత్రి పది గంటలు"),
    ("12 am", "te", "అర్ధరాత్రి పన్నెండు గంటలు"),
    ("6 pm కి రండి", "te", "సాయంత్రం ఆరు గంటలకి రండి"),
    ("10:30 am కు", "te", "ఉదయం పదిన్నరకు"),
    ("9 am – 9 pm", "te", "ఉదయం తొమ్మిది గంటల నుండి రాత్రి తొమ్మిది గంటల వరకు"),
]


@pytest.mark.parametrize(("text", "lang", "expected"), TIMES)
def test_times(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


DATES: list[tuple[str, Lang, str]] = [
    ("18 Oct", "en", "eighteenth October"),
    ("18th October", "en", "eighteenth October"),
    ("18th of October, 2026", "en", "eighteenth October two thousand twenty-six"),
    ("Oct 18", "en", "eighteenth October"),
    ("Oct 18, 2026", "en", "eighteenth October two thousand twenty-six"),
    ("18/10/2026", "en", "eighteenth October two thousand twenty-six"),
    ("18-10-2026", "en", "eighteenth October two thousand twenty-six"),
    ("2026-10-18", "en", "eighteenth October two thousand twenty-six"),
    ("1st Jan", "en", "first January"),
    ("Sat, 18 Oct", "en", "Saturday, eighteenth October"),
    ("1995-08-15", "en", "fifteenth August nineteen ninety-five"),
    ("see you tomorrow", "en", "see you tomorrow"),
    ("31/02/2026", "en", "31/02/2026"),
    ("18 Oct", "hi", "अठारह अक्टूबर"),
    ("18/10/2026", "hi", "अठारह अक्टूबर दो हज़ार छब्बीस"),
    ("2026-10-18", "hi", "अठारह अक्टूबर दो हज़ार छब्बीस"),
    ("Sat, 18 Oct", "hi", "शनिवार, अठारह अक्टूबर"),
    ("1995-08-15", "hi", "पंद्रह अगस्त उन्नीस सौ पचानवे"),
    ("18 Oct", "te", "అక్టోబర్ పద్దెనిమిది"),
    ("2026-10-18", "te", "అక్టోబర్ పద్దెనిమిది, రెండు వేల ఇరవై ఆరు"),
    ("Sat, 18 Oct", "te", "శనివారం, అక్టోబర్ పద్దెనిమిది"),
    ("1995-08-15", "te", "ఆగస్టు పదిహేను, పంతొమ్మిది వందల తొంభై ఐదు"),
]


@pytest.mark.parametrize(("text", "lang", "expected"), DATES)
def test_dates(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


WEEKDAYS: list[tuple[str, Lang, str]] = [
    ("Mon–Sat", "en", "Monday to Saturday"),
    ("Mon-Fri", "en", "Monday to Friday"),
    ("Tue to Thu", "en", "Tuesday to Thursday"),
    ("Mon–Sat", "hi", "सोमवार से शनिवार तक"),
    ("Mon–Sat", "te", "సోమవారం నుండి శనివారం వరకు"),
    ("Monday को", "hi", "सोमवार को"),
    ("Sunday సెలవు", "te", "ఆదివారం సెలవు"),
    ("Monday works", "en", "Monday works"),
    ("I sat down", "en", "I sat down"),
    (
        "Mon–Sat, 9 am – 9 pm",
        "en",
        "Monday to Saturday, nine in the morning to nine at night",
    ),
    (
        "Mon–Sat, 9 am – 9 pm",
        "hi",
        "सोमवार से शनिवार तक, सुबह नौ बजे से रात नौ बजे तक",
    ),
]


@pytest.mark.parametrize(("text", "lang", "expected"), WEEKDAYS)
def test_weekdays(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


QUARTERS: list[tuple[str, str]] = [
    ("6:15 pm", "సాయంత్రం ఆరుంబావు"),
    ("6:45 pm", "సాయంత్రం ఆరుముప్పావు"),
    ("1:15 pm", "మధ్యాహ్నం ఒకటింబావు"),
    ("6:30 pm", "సాయంత్రం ఆరున్నర"),
    ("6:20 pm", "సాయంత్రం ఆరు ఇరవై"),
    ("6:15 pm కి", "సాయంత్రం ఆరుంబావుకి"),
    ("6:15 pm - 7:45 pm", "సాయంత్రం ఆరుంబావు నుండి ఏడుముప్పావు వరకు"),
]


@pytest.mark.parametrize(("text", "expected"), QUARTERS)
def test_telugu_colloquial_quarters(text: str, expected: str) -> None:
    assert speakable(text, "te", colloquial_quarters=True) == expected


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("6:15 pm", "te", "సాయంత్రం ఆరు పదిహేను"),
        ("6:45 pm", "te", "సాయంత్రం ఆరు నలభై ఐదు"),
        ("6:15 pm", "hi", "शाम सवा छह बजे"),
        ("6:15 pm", "en", "six fifteen in the evening"),
    ],
)
def test_quarters_flag_default_off_and_telugu_only(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected
    if lang != "te":
        assert speakable(text, lang, colloquial_quarters=True) == expected
