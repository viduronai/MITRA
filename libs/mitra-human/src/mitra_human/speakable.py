"""``speakable``: rewrite written forms into what an Indian telecaller would say.

TODO: native-speaker review for hi/te tables.

The output stays in the script the LLM produced; only numbers, amounts, dates, times,
phone numbers, percentages, ordinals and weekday ranges are rewritten. URLs and email
addresses are never touched (see ``spell_email`` to read one aloud on purpose).

Rules run in a fixed order, most specific first: dates -> times -> phones -> money ->
percent -> ordinals -> weekdays -> lakh/crore numbers -> ranges -> plain numbers.
"""

from __future__ import annotations

import re

from mitra_human._datetime import apply_dates, apply_times, apply_weekdays
from mitra_human._lang import Lang, check_lang
from mitra_human._lexicon import NUMBER_RANGE_WORDS, PERCENT
from mitra_human._marks import finalize, mark, te_form_after
from mitra_human._money import AMOUNT, apply_money, apply_scaled_numbers
from mitra_human._num_te import TeForm
from mitra_human._phone import apply_phones
from mitra_human.numwords import cardinal, decimal, digit_words, ordinal

__all__ = ["speakable", "spell_digits", "spell_email"]

_NATIVE_DIGITS = str.maketrans(
    {**{chr(0x0966 + i): str(i) for i in range(10)}, **{chr(0x0C66 + i): str(i) for i in range(10)}}
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_URL = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|(?<![\w@.])[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
    r"\.(?:com|in|org|net|co|io|app|ai|info|biz|edu|gov|me|store|shop)(?:\.in)?"
    r"(?![A-Za-z0-9-])(?:/[^\s<>\"']*)?"
)
_TRAILING_PUNCT = ".,!?;:)]}'\""
_PLACEHOLDER = re.compile("\ue000(.)\ue001")

_NUM_BEFORE = r"(?<![A-Za-z0-9_.,\-/:])"
_NUM_AFTER = r"(?![A-Za-z0-9_/]|[.,:]\d)"
_PERCENT = re.compile(rf"{_NUM_BEFORE}(?P<n>{AMOUNT})(?:\.(?P<f>\d+))?\s?%")
_ORDINAL = re.compile(rf"{_NUM_BEFORE}(?P<n>\d+)(?i:st|nd|rd|th)(?![A-Za-z0-9])")
_NUMBER_RANGE = re.compile(
    rf"{_NUM_BEFORE}(?P<a>\d{{1,7}})\s*(?:[-–—]|(?<=\s)to(?=\s))\s*(?P<b>\d{{1,7}}){_NUM_AFTER}"
)
_PLAIN = re.compile(rf"{_NUM_BEFORE}(?P<n>{AMOUNT})(?:\.(?P<f>\d+))?{_NUM_AFTER}")


def _protect(text: str) -> tuple[str, list[str]]:
    saved: list[str] = []

    def stash(m: re.Match[str]) -> str:
        whole = m.group(0)
        body = whole.rstrip(_TRAILING_PUNCT)
        saved.append(body)
        return f"\ue000{chr(0xE100 + len(saved) - 1)}\ue001{whole[len(body) :]}"

    text = _EMAIL.sub(stash, text)
    return _URL.sub(stash, text), saved


def _restore(text: str, saved: list[str]) -> str:
    return _PLACEHOLDER.sub(lambda m: saved[ord(m.group(1)) - 0xE100], text)


def _form(m: re.Match[str], lang: Lang) -> TeForm:
    return te_form_after(m.string[m.end() :]) if lang == "te" else "plain"


def _number(raw: str, frac: str | None, lang: Lang, form: TeForm) -> str:
    if frac is not None:
        return decimal(int(raw.replace(",", "")), frac, lang)
    if "," not in raw and (len(raw) >= 11 or (len(raw) > 1 and raw.startswith("0"))):
        return digit_words(raw, lang)  # account numbers, OTP-like codes with leading zeros
    return cardinal(int(raw.replace(",", "")), lang, form)


def _apply_numbers(text: str, lang: Lang) -> str:
    def percent(m: re.Match[str]) -> str:
        form: TeForm = "attr"
        return mark(f"{_number(m.group('n'), m.group('f'), lang, form)} {PERCENT[lang]}")

    def nth(m: re.Match[str]) -> str:
        return mark(ordinal(int(m.group("n")), lang))

    def number_range(m: re.Match[str]) -> str:
        a, b = int(m.group("a")), int(m.group("b"))
        first = cardinal(a, lang, "oblique")
        return mark(f"{first}{NUMBER_RANGE_WORDS[lang]}{cardinal(b, lang, _form(m, lang))}")

    def plain(m: re.Match[str]) -> str:
        return mark(_number(m.group("n"), m.group("f"), lang, _form(m, lang)))

    text = _PERCENT.sub(percent, text)
    text = _ORDINAL.sub(nth, text)
    text = apply_weekdays(text, lang)
    text = apply_scaled_numbers(text, lang)
    text = _NUMBER_RANGE.sub(number_range, text)
    return _PLAIN.sub(plain, text)


def speakable(text: str, lang: Lang, *, colloquial_quarters: bool = False) -> str:
    """Rewrite numbers, money, dates, times and phone numbers into spoken form.

    ``colloquial_quarters`` (Telugu only) reads 6:15 / 6:45 as ఆరుంబావు / ఆరుముప్పావు
    instead of ఆరు పదిహేను / ఆరు నలభై ఐదు.

    >>> speakable("Fees are ₹1,20,000/-", "en")
    'Fees are one lakh twenty thousand rupees'
    """
    language = check_lang(lang)
    if not text:
        return text
    working, saved = _protect(text)
    working = working.translate(_NATIVE_DIGITS)
    working = apply_dates(working, language)
    working = apply_times(working, language, quarters=colloquial_quarters)
    working = apply_phones(working, language)
    working = apply_money(working, language)
    working = _apply_numbers(working, language)
    return _restore(finalize(working, language), saved)


def spell_digits(digits: str, lang: str) -> str:
    """Read a code digit by digit: "4821" -> "four eight two one"."""
    language = check_lang(lang)
    clean = digits.translate(_NATIVE_DIGITS)
    if not clean.isascii() or not clean.isdigit():
        raise ValueError(f"expected only digits, got {digits!r}")
    return digit_words(clean, language)


_EMAIL_SYMBOLS = {
    "en": {".": "dot", "@": "at", "_": "underscore", "-": "hyphen", "+": "plus"},
    "hi": {".": "डॉट", "@": "एट", "_": "अंडरस्कोर", "-": "हाइफ़न", "+": "प्लस"},
    "te": {".": "డాట్", "@": "ఎట్", "_": "అండర్‌స్కోర్", "-": "హైఫన్", "+": "ప్లస్"},
}


def spell_email(email: str, lang: str) -> str:
    """Read an email address aloud: "ravi.k@gmail.com" -> "ravi dot k at gmail dot com"."""
    language = check_lang(lang)
    address = email.strip()
    if not _EMAIL.fullmatch(address):
        raise ValueError(f"not an email address: {email!r}")
    symbols = _EMAIL_SYMBOLS[language]
    words: list[str] = []
    for token in re.findall(r"[A-Za-z]+|\d|[^A-Za-z\d]", address):
        if token.isdigit():
            words.append(digit_words(token, language))
        else:
            words.append(symbols.get(token, token))
    return " ".join(words)
