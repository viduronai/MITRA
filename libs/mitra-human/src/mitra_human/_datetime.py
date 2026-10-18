"""Times, dates and weekday ranges, said the way an Indian telecaller says them.

Times without am/pm are ambiguous for hours 1-12 ("9:30"), so they are read without a
morning/evening word. A leading zero ("09:30") or a 24-hour value ("18:15") is taken
as 24-hour time and gets one.

Telugu choice: hh:30 uses the half form (ఆరున్నర); other minutes are read as
"hour minutes" (ఆరు పదిహేను), the form most urban telecallers use, rather than the
traditional quarter forms. Both are fine (confirmed by the founder); pass
``colloquial_quarters=True`` for ఆరుంబావు (6:15) / ఆరుముప్పావు (6:45). 1:00 is ఒంటి గంట.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

from mitra_human import _num_en
from mitra_human._lang import Lang
from mitra_human._lexicon import (
    BUCKET_WORDS,
    MONTH_PATTERN,
    MONTHS,
    RANGE_WORDS,
    WEEKDAY_PATTERN,
    WEEKDAYS,
    bucket_of,
    month_index,
    weekday_index,
)
from mitra_human._marks import mark
from mitra_human._num_te import oblique_phrase
from mitra_human.numwords import cardinal, half, ordinal, year

_DASH = r"\s*(?:[-–—]|(?<=\s)to(?=\s))\s*"


@dataclass(frozen=True, slots=True)
class Clock:
    hour12: int
    minute: int
    bucket: str | None


def _ap(i: int) -> str:
    # The dot after "p.m" is kept when it ends the sentence ("at 6 p.m." stays a full stop).
    return rf"(?P<ap{i}>[AaPp])\.?\s?[Mm](?![A-Za-z])(?:\.(?!\s*$|\s+[A-Z]))?"


def _time12(i: int, *, ap_optional: bool = False) -> str:
    base = rf"(?<![0-9.:])(?P<h{i}>1[0-2]|0?[1-9])(?:[:.](?P<m{i}>[0-5]\d))?"
    return base + (rf"(?:\s*{_ap(i)})?" if ap_optional else rf"\s*{_ap(i)}")


def _time24(i: int) -> str:
    return (
        rf"(?<![0-9.:])(?P<h{i}>[01]?\d|2[0-3]):(?P<m{i}>[0-5]\d)"
        r"(?:\s*(?:hrs|hours|hr)(?![A-Za-z]))?(?![0-9:])"
    )


_RANGE12 = re.compile(_time12(1, ap_optional=True) + _DASH + _time12(2))
_RANGE24 = re.compile(_time24(1) + _DASH + _time24(2))
_TIME12 = re.compile(_time12(1))
_TIME24 = re.compile(_time24(1))


def _to24(hour12: int, ap: str) -> int:
    return hour12 % 12 + (12 if ap.lower() == "p" else 0)


def _clock12(hour12: int, minute: int, ap: str) -> Clock:
    return Clock(hour12, minute, bucket_of(_to24(hour12, ap), minute))


def _clock24(hour_text: str, minute: int) -> Clock:
    hour = int(hour_text)
    hour12 = hour % 12 or 12
    explicit = hour == 0 or hour >= 13 or hour_text.startswith("0")
    return Clock(hour12, minute, bucket_of(hour, minute) if explicit else None)


def _core(c: Clock, lang: Lang, quarters: bool) -> str:
    h, m = c.hour12, c.minute
    if lang == "en":
        if m == 0:
            return _num_en.cardinal(h)
        tail = f"oh {_num_en.cardinal(m)}" if m < 10 else _num_en.cardinal(m)
        return f"{_num_en.cardinal(h)} {tail}"
    if lang == "hi":
        hw = cardinal(h, "hi")
        if m == 0:
            return f"{hw} बजे"
        if m == 15:
            return f"सवा {hw} बजे"
        if m == 30:
            return f"{half(h, 'hi')} बजे" if h <= 2 else f"साढ़े {hw} बजे"
        if m == 45:
            return f"पौने {cardinal(h % 12 + 1, 'hi')} बजे"
        return f"{hw} बजकर {cardinal(m, 'hi')} मिनट"
    hw = cardinal(h, "te")
    if m == 0:
        return "ఒంటి గంట" if h == 1 else f"{hw} గంటలు"
    if m == 30:
        return half(h, "te")
    if quarters and m == 15:
        return hw + "ంబావు"
    if quarters and m == 45:
        return hw + "ముప్పావు"
    if m < 10:
        hour_part = "ఒంటి గంట" if h == 1 else f"{hw} గంటల"
        return f"{hour_part} {cardinal(m, 'te')} నిమిషాలు"
    return f"{hw} {cardinal(m, 'te')}"


def render_time(c: Clock, lang: Lang, *, with_bucket: bool = True, quarters: bool = False) -> str:
    core = _core(c, lang, quarters)
    if not with_bucket or c.bucket is None:
        return core
    word = BUCKET_WORDS[lang][c.bucket]
    if lang == "en":
        if c.bucket in ("noon", "midnight"):
            return f"twelve {word}"
        return f"{core} {word}"
    return f"{word} {core}"


def render_time_range(a: Clock, b: Clock, lang: Lang, *, quarters: bool = False) -> str:
    shared = a.bucket is not None and a.bucket == b.bucket and a.bucket not in ("noon", "midnight")
    between, after = RANGE_WORDS[lang]
    if lang == "en":
        first = render_time(a, lang, with_bucket=not shared)
        return f"{first}{between}{render_time(b, lang)}"
    first = render_time(a, lang, quarters=quarters)
    second = render_time(b, lang, with_bucket=not shared, quarters=quarters)
    if lang == "te":
        first, second = oblique_phrase(first), oblique_phrase(second)
    return f"{first}{between}{second}{after}"


def _minute(m: re.Match[str], i: int) -> int:
    value = m.group(f"m{i}")
    return int(value) if value else 0


def apply_times(text: str, lang: Lang, *, quarters: bool = False) -> str:
    def range12(m: re.Match[str]) -> str:
        h1, h2 = int(m.group("h1")), int(m.group("h2"))
        m1, m2 = _minute(m, 1), _minute(m, 2)
        ap2 = m.group("ap2")
        ap1 = m.group("ap1")
        if ap1 is None:
            ap1 = ap2
            if _to24(h1, ap1) * 60 + m1 > _to24(h2, ap2) * 60 + m2:
                ap1 = "a" if ap2.lower() == "p" else "p"
        a, b = _clock12(h1, m1, ap1), _clock12(h2, m2, ap2)
        return mark(render_time_range(a, b, lang, quarters=quarters))

    def range24(m: re.Match[str]) -> str:
        a = _clock24(m.group("h1"), int(m.group("m1")))
        b = _clock24(m.group("h2"), int(m.group("m2")))
        return mark(render_time_range(a, b, lang, quarters=quarters))

    def single12(m: re.Match[str]) -> str:
        clock = _clock12(int(m.group("h1")), _minute(m, 1), m.group("ap1"))
        return mark(render_time(clock, lang, quarters=quarters))

    def single24(m: re.Match[str]) -> str:
        clock = _clock24(m.group("h1"), int(m.group("m1")))
        return mark(render_time(clock, lang, quarters=quarters))

    text = _RANGE12.sub(range12, text)
    text = _RANGE24.sub(range24, text)
    text = _TIME12.sub(single12, text)
    return _TIME24.sub(single24, text)


# ---------------------------------------------------------------- dates

_WD_PREFIX = rf"(?:(?P<wd>(?i:{WEEKDAY_PATTERN}))\.?,?\s+)?"
_ISO_DATE = re.compile(r"(?<![\d./-])(?P<y>\d{4})-(?P<mo>\d{1,2})-(?P<d>\d{1,2})(?!\d)")
_DMY_DATE = re.compile(
    r"(?<![\d./-])(?P<d>\d{1,2})(?P<sep>[/.-])(?P<mo>\d{1,2})(?P=sep)(?P<y>\d{4}|\d{2})"
    r"(?!\d|[/.-]\d)"
)
_YEAR_TAIL = r"(?:,?\s*(?P<y>(?:19|20)\d{2})(?!\d))?"
_DAY_MONTH = re.compile(
    _WD_PREFIX + r"(?<![\d.:/])(?P<d>[0-3]?\d)(?i:st|nd|rd|th)?\s*(?:of\s+)?"
    rf"(?P<mon>(?i:{MONTH_PATTERN}))(?![A-Za-z])" + _YEAR_TAIL
)
# Month-first only for capitalised month names, so "may 5" in a sentence is left alone.
_MONTH_DAY = re.compile(
    _WD_PREFIX + rf"(?P<mon>{MONTH_PATTERN})\.?\s+(?P<d>[0-3]?\d)(?i:st|nd|rd|th)?"
    r"(?![\d:A-Za-z]|\.\d)" + _YEAR_TAIL
)
_WEEKDAY_RANGE = re.compile(
    rf"(?<![A-Za-z])(?P<a>(?i:{WEEKDAY_PATTERN}))\.?{_DASH}(?P<b>(?i:{WEEKDAY_PATTERN}))\.?"
    r"(?![A-Za-z])"
)
_FULL_WEEKDAY = re.compile(
    r"(?<![A-Za-z])(?i:(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?)"
    r"(?![A-Za-z])"
)


def _valid(day: int, month: int, yr: int | None) -> bool:
    if not 1 <= month <= 12 or day < 1:
        return False
    return day <= calendar.monthrange(yr if yr is not None else 2024, month)[1]


def render_date(day: int, month: int, yr: int | None, weekday: int | None, lang: Lang) -> str:
    month_word = MONTHS[lang][month - 1]
    if lang == "en":
        body = f"{ordinal(day, lang)} {month_word}"
    elif lang == "hi":
        body = f"{cardinal(day, lang)} {month_word}"
    else:
        body = f"{month_word} {cardinal(day, lang)}"
    if yr is not None:
        body += (", " if lang == "te" else " ") + year(yr, lang)
    if weekday is not None:
        body = f"{WEEKDAYS[lang][weekday]}, {body}"
    return body


def apply_dates(text: str, lang: Lang) -> str:
    def numeric(m: re.Match[str]) -> str:
        day, month = int(m.group("d")), int(m.group("mo"))
        raw_year = m.group("y")
        yr = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
        if not _valid(day, month, yr):
            return m.group(0)
        return mark(render_date(day, month, yr, None, lang))

    def textual(m: re.Match[str]) -> str:
        day, month = int(m.group("d")), month_index(m.group("mon"))
        yr = int(m.group("y")) if m.group("y") else None
        if not _valid(day, month, yr):
            return m.group(0)
        wd = weekday_index(m.group("wd")) if m.group("wd") else None
        return mark(render_date(day, month, yr, wd, lang))

    text = _ISO_DATE.sub(numeric, text)
    text = _DMY_DATE.sub(numeric, text)
    text = _DAY_MONTH.sub(textual, text)
    return _MONTH_DAY.sub(textual, text)


def apply_weekdays(text: str, lang: Lang) -> str:
    """Mon-Sat -> Monday to Saturday; English weekday names into hi/te."""

    def weekday_range(m: re.Match[str]) -> str:
        names = WEEKDAYS[lang]
        between, after = RANGE_WORDS[lang]
        a, b = names[weekday_index(m.group("a"))], names[weekday_index(m.group("b"))]
        return mark(f"{a}{between}{b}{after}")

    text = _WEEKDAY_RANGE.sub(weekday_range, text)
    if lang != "en":
        text = _FULL_WEEKDAY.sub(lambda m: mark(WEEKDAYS[lang][weekday_index(m.group(1))]), text)
    return text
