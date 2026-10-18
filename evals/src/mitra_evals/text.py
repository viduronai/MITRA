"""Multilingual text utilities for the deterministic checks: normalisation, fact mentions,
₹ amounts, script shares and sentence counts (en / Telugu / Hindi / code-mixed)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_INDIC_DIGITS = str.maketrans(
    "౦౧౨౩౪౫౬౭౮౯०१२३४५६७८९",
    "01234567890123456789",
)
_DIGIT_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")
_SPACE_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """NFC, casefold, Indic digits -> ASCII, ``1,50,000`` -> ``150000``, single spaces."""
    text = unicodedata.normalize("NFC", text).translate(_INDIC_DIGITS).casefold()
    text = text.replace("‌", "").replace("‍", "")  # ZWNJ/ZWJ vary between writers
    return _SPACE_RE.sub(" ", _DIGIT_COMMA_RE.sub("", text)).strip()


def mentions(text: str, form: str) -> bool:
    """Whether ``form`` occurs in ``text``; all-digit forms must not be part of a longer number
    (``"500"`` does not match ``"1500"``)."""
    haystack, needle = normalise(text), normalise(form)
    if not needle:
        return False
    if needle.isdigit():
        return re.search(rf"(?<!\d){re.escape(needle)}(?!\d)", haystack) is not None
    return needle in haystack


def words(text: str) -> list[str]:
    """Normalised words with punctuation and symbols dropped. (A plain regex word class would
    split Telugu and Devanagari words at their vowel signs, which are combining marks.)"""
    kept = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in normalise(text))
    return kept.split()


# --- ₹ amounts ----------------------------------------------------------------------------------

_NUM = r"\d+(?:\.\d+)?"
_UNIT = r"lakhs?|lacs?|crores?|cr(?![a-z])|k(?![a-z])|లక్ష\S*|కోటి|కోట్ల\S*|लाख|करोड़?"
_RUPEES = r"rupees?|రూపాయ\S*|रुपये|रुपए|रुपया"
_MONEY_RE = re.compile(
    rf"(?:₹|(?<![a-z])rs\.?|(?<![a-z])inr)\s?(?P<a>{_NUM})\s*(?P<au>{_UNIT})?"
    rf"|(?P<b>{_NUM})\s*(?P<bu>{_UNIT}|{_RUPEES})"
)


def _multiplier(unit: str | None) -> float:
    if not unit:
        return 1
    if unit.startswith(("lakh", "lac", "లక్ష", "लाख")):
        return 100_000
    if unit.startswith(("cr", "కోట", "కోటి", "करोड")):
        return 10_000_000
    if unit == "k":
        return 1_000
    return 1


def money_amounts(text: str) -> list[int]:
    """Rupee amounts said with a currency marker or a lakh/crore unit, in rupees.
    Bare numbers ("call 112", "1,150 sq ft") are deliberately not money."""
    amounts: list[int] = []
    for match in _MONEY_RE.finditer(normalise(text)):
        number = match.group("a") or match.group("b")
        unit = match.group("au") if match.group("a") else match.group("bu")
        amounts.append(round(float(number) * _multiplier(unit)))
    return amounts


# --- scripts and sentences ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScriptShares:
    telugu: float
    devanagari: float
    latin: float
    letters: int


def script_shares(text: str) -> ScriptShares:
    te = sum(1 for c in text if "ఀ" <= c <= "౿")
    hi = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    la = sum(1 for c in text if c.isascii() and c.isalpha())
    total = te + hi + la
    if total == 0:
        return ScriptShares(0.0, 0.0, 0.0, 0)
    return ScriptShares(te / total, hi / total, la / total, total)


_ABBREV_RE = re.compile(r"(?<![a-z])(dr|mr|mrs|ms|no|st|sr|jr|rd|vs|approx)\.", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?।]+(?=\s|$)|\n+")
_HAS_WORD_RE = re.compile(r"\w")


def sentence_count(text: str) -> int:
    text = _ABBREV_RE.sub(r"\1", text)
    text = text.replace("डॉ.", "डॉ").replace("డా.", "డా")
    text = re.sub(r"\b([ap])\.m\.", r"\1m", text, flags=re.IGNORECASE)
    return sum(1 for part in _SENTENCE_END_RE.split(text) if _HAS_WORD_RE.search(part))
