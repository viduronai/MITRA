"""Month, weekday, time-of-day and connective words per language."""

from __future__ import annotations

from typing import Final

from mitra_human._lang import Lang

MONTHS: Final[dict[Lang, tuple[str, ...]]] = {
    "en": tuple(
        "January February March April May June July August September October November December".split()  # noqa: E501
    ),
    "hi": tuple("जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर".split()),
    "te": tuple("జనవరి ఫిబ్రవరి మార్చి ఏప్రిల్ మే జూన్ జూలై ఆగస్టు సెప్టెంబర్ అక్టోబర్ నవంబర్ డిసెంబర్".split()),
}

# Index 0 is Monday.
WEEKDAYS: Final[dict[Lang, tuple[str, ...]]] = {
    "en": tuple("Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()),
    "hi": tuple("सोमवार मंगलवार बुधवार गुरुवार शुक्रवार शनिवार रविवार".split()),
    "te": tuple("సోమవారం మంగళవారం బుధవారం గురువారం శుక్రవారం శనివారం ఆదివారం".split()),
}

# Regex alternations (used with re.IGNORECASE) and how to map a match to an index.
MONTH_PATTERN: Final = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
WEEKDAY_PATTERN: Final = (
    r"Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?"
    r"|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?"
)


def month_index(token: str) -> int:
    """1-based month number for an English month name or abbreviation."""
    return (
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    ).index(token[:3].lower()) + 1


def weekday_index(token: str) -> int:
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun").index(token[:3].lower())


# Time-of-day buckets. "noon"/"midnight" are used only for exactly 12:00 and 00:00.
BUCKET_WORDS: Final[dict[Lang, dict[str, str]]] = {
    "en": {
        "morning": "in the morning",
        "afternoon": "in the afternoon",
        "evening": "in the evening",
        "night": "at night",
        "noon": "noon",
        "midnight": "midnight",
    },
    "hi": {
        "morning": "सुबह",
        "afternoon": "दोपहर",
        "evening": "शाम",
        "night": "रात",
        "noon": "दोपहर",
        "midnight": "रात",
    },
    "te": {
        "morning": "ఉదయం",
        "afternoon": "మధ్యాహ్నం",
        "evening": "సాయంత్రం",
        "night": "రాత్రి",
        "noon": "మధ్యాహ్నం",
        "midnight": "అర్ధరాత్రి",
    },
}


def bucket_of(hour24: int, minute: int) -> str:
    if hour24 == 12 and minute == 0:
        return "noon"
    if hour24 == 0 and minute == 0:
        return "midnight"
    if 4 <= hour24 < 12:
        return "morning"
    if 12 <= hour24 < 16:
        return "afternoon"
    if 16 <= hour24 < 20:
        return "evening"
    return "night"


# "A to B" for ranges: (between, after). Telugu/Hindi wrap the range: A నుండి B వరకు.
RANGE_WORDS: Final[dict[Lang, tuple[str, str]]] = {
    "en": (" to ", ""),
    "hi": (" से ", " तक"),
    "te": (" నుండి ", " వరకు"),
}
# Plain number ranges ("5-10 minutes") read without the closing word.
NUMBER_RANGE_WORDS: Final[dict[Lang, str]] = {"en": " to ", "hi": " से ", "te": " నుండి "}

PERCENT: Final[dict[Lang, str]] = {"en": "percent", "hi": "परसेंट", "te": "శాతం"}
PLUS: Final[dict[Lang, str]] = {"en": "plus", "hi": "प्लस", "te": "ప్లస్"}
