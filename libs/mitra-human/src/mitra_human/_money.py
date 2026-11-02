"""Rupee amounts and lakh/crore-scaled numbers.

Decimal scale amounts are read as their exact value (₹1.2 lakh -> one lakh twenty
thousand rupees), except n.5 lakh/crore for n in 1-19, which use the spoken half form:
"two and a half crore", "ढाई करोड़", "రెండున్నర కోట్లు".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from mitra_human._lang import DEVANAGARI, TELUGU, BaseLang
from mitra_human._lexicon import RANGE_WORDS
from mitra_human._marks import mark, te_form_after
from mitra_human._num_te import TeForm
from mitra_human.numwords import cardinal, half

# An amount: Indian (1,20,000) or Western (120,000) grouping, or bare digits.
AMOUNT = r"(?:\d{1,3}(?:,(?:\d{3}|\d{2}))*,\d{3}|\d+)"
_NOT_WORD = rf"(?![A-Za-z{DEVANAGARI}{TELUGU}])"
# करोड़ may arrive with a precomposed (U+095C) or decomposed nukta.
_NATIVE_SCALES = r"लाख|करो(?:ड़|ड़)|లక్షలు|లక్షల|లక్ష|కోట్లు|కోట్ల|కోటి"
_SCALE_WORDS = rf"(?i:lakhs?|lacs?|crores?|cr|thousand|k|l)|{_NATIVE_SCALES}"
_CUR_PREFIX = r"(?:₹|(?<![A-Za-z])(?:Rs|RS|rs|INR)\.?)\s*"
_CUR_SUFFIX = r"(?:\s*/-|\s*(?:(?:Rs|INR)\.?|rupees?)(?![A-Za-z])|\s*₹)"


def _amount(i: int) -> str:
    return (
        rf"(?P<num{i}>{AMOUNT})(?:\.(?P<frac{i}>\d+))?"
        rf"(?:\s*(?P<scale{i}>{_SCALE_WORDS}){_NOT_WORD})?"
    )


_PREFIXED = re.compile(rf"{_CUR_PREFIX}{_amount(1)}{_CUR_SUFFIX}?(?![\d,.]\d)")
_SUFFIXED = re.compile(rf"(?<![\w.,]){_amount(1)}{_CUR_SUFFIX}(?![\d,.]\d)")
_RANGE = re.compile(
    rf"{_CUR_PREFIX}{_amount(1)}\s*(?:[-–—]|(?<=\s)to(?=\s))\s*(?:{_CUR_PREFIX})?{_amount(2)}"
    rf"{_CUR_SUFFIX}?(?![\d,.]\d)"
)
_SCALED = re.compile(
    rf"(?<![\w.,])(?P<num1>{AMOUNT})(?:\.(?P<frac1>\d+))?\s*"
    rf"(?P<scale1>(?i:lakhs?|lacs?|crores?|thousand)|{_NATIVE_SCALES}){_NOT_WORD}"
)

_MULTIPLIER = {"thousand": 1000, "lakh": 10**5, "crore": 10**7}
_SCALE_NAMES = {
    "en": {"lakh": "lakh", "crore": "crore"},
    "hi": {"lakh": "लाख", "crore": "करोड़"},
}
_POINT_WORD = {"en": "point", "hi": "पॉइंट", "te": "పాయింట్"}
_TE_SCALE = {"lakh": ("లక్షలు", "లక్షల"), "crore": ("కోట్లు", "కోట్ల")}


@dataclass(frozen=True, slots=True)
class Half:
    """n and a half lakh/crore."""

    whole: int
    scale: str


Amount = Half | Decimal


def _scale_key(word: str | None) -> str | None:
    if word is None:
        return None
    w = word.lower()
    if w.startswith(("lakh", "lac")) or w == "l" or w in ("लाख", "లక్షలు", "లక్షల", "లక్ష"):
        return "lakh"
    if w.startswith(("crore", "cr", "करो")) or w in ("కోట్లు", "కోట్ల", "కోటి"):
        return "crore"
    return "thousand"


def parse_amount(num: str, frac: str | None, scale_word: str | None) -> Amount:
    value = Decimal(num.replace(",", "") + (f".{frac}" if frac else ""))
    scale = _scale_key(scale_word)
    if scale is None:
        return value
    whole = int(value)
    if scale != "thousand" and value - whole == Decimal("0.5") and 1 <= whole <= 19:
        return Half(whole, scale)
    return value * _MULTIPLIER[scale]


def _split(value: Decimal) -> tuple[int, int]:
    paise_total = int(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)
    return divmod(paise_total, 100)


def amount_words(amount: Amount, lang: BaseLang, te_form: TeForm = "plain") -> str:
    """The number part of an amount, without the currency word."""
    if isinstance(amount, Half):
        h = half(amount.whole, lang)
        if lang == "te":
            plural, combining = _TE_SCALE[amount.scale]
            return f"{h} {plural if te_form == 'plain' else combining}"
        return f"{h} {_SCALE_NAMES[lang][amount.scale]}"
    rupees, paise = _split(amount)
    if paise:
        return f"{cardinal(rupees, lang)} {_POINT_WORD[lang]} {cardinal(paise, lang)}"
    return cardinal(rupees, lang, te_form)


def money_words(amount: Amount, lang: BaseLang) -> str:
    if isinstance(amount, Half):
        unit = {"en": "rupees", "hi": "रुपये", "te": "రూపాయలు"}[lang]
        return f"{amount_words(amount, lang, 'attr')} {unit}"
    rupees, paise = _split(amount)
    parts: list[str] = []
    if lang == "en":
        if rupees:
            parts.append(f"{cardinal(rupees, lang)} {'rupee' if rupees == 1 else 'rupees'}")
        if paise:
            parts.append(f"{cardinal(paise, lang)} {'paisa' if paise == 1 else 'paise'}")
        return " and ".join(parts) or "zero rupees"
    if lang == "hi":
        if rupees:
            parts.append(f"{cardinal(rupees, lang)} {'रुपया' if rupees == 1 else 'रुपये'}")
        if paise:
            parts.append(f"{cardinal(paise, lang)} पैसे")
        return " ".join(parts) or "शून्य रुपये"
    if rupees:
        unit = "రూపాయి" if rupees == 1 else ("రూపాయల" if paise else "రూపాయలు")
        parts.append(f"{cardinal(rupees, lang, 'attr')} {unit}")
    if paise:
        parts.append(f"{cardinal(paise, lang, 'attr')} పైసలు")
    return " ".join(parts) or "సున్నా రూపాయలు"


def _range_words(a: Amount, b: Amount, lang: BaseLang) -> str:
    between, after = RANGE_WORDS[lang]
    if lang == "en":
        return f"{amount_words(a, lang)}{between}{amount_words(b, lang)} rupees"
    if lang == "hi":
        return f"{amount_words(a, lang)}{between}{amount_words(b, lang)} रुपये"
    first = amount_words(a, lang, "oblique")
    return f"{first}{between}{amount_words(b, lang, 'attr')} రూపాయల{after}"


def apply_money(text: str, lang: BaseLang) -> str:
    def money_range(m: re.Match[str]) -> str:
        scale1, scale2 = m.group("scale1"), m.group("scale2")
        num1, num2 = m.group("num1"), m.group("num2")
        if (
            scale1 is None
            and scale2 is not None
            and Decimal(num1.replace(",", "")) <= Decimal(num2.replace(",", ""))
        ):
            scale1 = scale2
        a = parse_amount(num1, m.group("frac1"), scale1)
        b = parse_amount(num2, m.group("frac2"), scale2)
        return mark(_range_words(a, b, lang))

    def single(m: re.Match[str]) -> str:
        return mark(
            money_words(parse_amount(m.group("num1"), m.group("frac1"), m.group("scale1")), lang)
        )

    text = _RANGE.sub(money_range, text)
    text = _PREFIXED.sub(single, text)
    return _SUFFIXED.sub(single, text)


def apply_scaled_numbers(text: str, lang: BaseLang) -> str:
    """1.2 lakh -> one lakh twenty thousand, 2.5 करोड़ -> ढाई करोड़ (no currency sign)."""

    def scaled(m: re.Match[str]) -> str:
        amount = parse_amount(m.group("num1"), m.group("frac1"), m.group("scale1"))
        form = te_form_after(m.string[m.end() :]) if lang == "te" else "plain"
        return mark(amount_words(amount, lang, form))

    return _SCALED.sub(scaled, text)
