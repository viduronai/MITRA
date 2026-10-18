"""Per-language number words: cardinals, ordinals, halves, digits, decimals, years.

TODO: native-speaker review for hi/te tables.
"""

from __future__ import annotations

from mitra_human import _num_en, _num_hi, _num_te
from mitra_human._lang import Lang, check_lang
from mitra_human._num_te import TeForm

__all__ = [
    "TeForm",
    "cardinal",
    "decimal",
    "digit_words",
    "half",
    "number_to_words",
    "ordinal",
    "year",
]

_POINT = {"en": "point", "hi": "पॉइंट", "te": "పాయింట్"}


def cardinal(n: int, lang: Lang, te_form: TeForm = "plain") -> str:
    if lang == "en":
        return _num_en.cardinal(n)
    if lang == "hi":
        return _num_hi.cardinal(n)
    return _num_te.cardinal(n, te_form)


def number_to_words(n: int, lang: str) -> str:
    """Public helper: an integer as words in the Indian system (lakh/crore)."""
    return cardinal(n, check_lang(lang))


def ordinal(n: int, lang: Lang) -> str:
    if lang == "en":
        return _num_en.ordinal(n)
    if lang == "hi":
        return _num_hi.ordinal(n)
    return _num_te.ordinal(n)


def half(n: int, lang: Lang) -> str:
    if lang == "en":
        return _num_en.half(n)
    if lang == "hi":
        return _num_hi.half(n)
    return _num_te.half(n)


def year(n: int, lang: Lang) -> str:
    if lang == "en":
        return _num_en.year(n)
    if lang == "hi":
        return _num_hi.year(n)
    return _num_te.year(n)


def digit_words(digits: str, lang: Lang, *, phone: bool = False) -> str:
    """Read a string of ASCII digits one by one, space separated."""
    if lang == "en":
        table = _num_en.DIGITS
    elif lang == "hi":
        table = _num_hi.PHONE_DIGITS if phone else _num_hi.DIGITS
    else:
        table = _num_te.DIGITS
    return " ".join(table[int(d)] for d in digits)


def decimal(int_part: int, frac_digits: str, lang: Lang) -> str:
    """3.25 -> "three point two five" (digits after the point read one by one)."""
    return f"{cardinal(int_part, lang)} {_POINT[lang]} {digit_words(frac_digits, lang)}"
