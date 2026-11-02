"""Phone numbers read digit by digit in groups, the way telecallers read them back.

Indian mobiles drop the +91 / 0 prefix (telecallers read back only the ten digits) and
are grouped 5-5 unless the text already groups them (987-654-3210 stays 3-3-4).
"""

from __future__ import annotations

import re

from mitra_human._lang import BaseLang, check_lang, digits_lang
from mitra_human._lexicon import PLUS
from mitra_human._marks import finalize, mark
from mitra_human.numwords import digit_words

_SEP = r"[ \-]?"
_MOBILE = re.compile(
    r"(?<![\d+₹.,])(?:(?:\+91|0091|91)[ \-]?|0)?"
    r"(?P<num>[6-9](?:" + _SEP + r"\d){9})(?![\d])"
)
_TOLL_FREE = re.compile(r"(?<![\d+₹.,])(?P<num>1[89]00(?:" + _SEP + r"\d){6,7})(?!\d)")
_LANDLINE = re.compile(r"(?<![\d+₹.,])(?P<num>0\d{2,4}[ \-]\d{2,4}[ \-]?\d{3,4})(?!\d)")
_INTERNATIONAL = re.compile(r"(?<![\d+])\+(?P<num>[1-9]\d{0,2}(?:" + _SEP + r"\d){6,13})(?!\d)")


def _groups(raw: str, default: tuple[int, ...]) -> list[str]:
    if re.search(r"[ \-]", raw):
        return [g for g in re.split(r"[ \-]+", raw) if g]
    groups, start = [], 0
    for size in default:
        groups.append(raw[start : start + size])
        start += size
    if start < len(raw):
        groups.append(raw[start:])
    return [g for g in groups if g]


def _read(groups: list[str], lang: BaseLang, *, plus: bool = False) -> str:
    spoken = ", ".join(digit_words(g, lang, phone=True) for g in groups)
    return f"{PLUS[lang]} {spoken}" if plus else spoken


def _landline_groups(raw: str) -> list[str]:
    std, local = re.split(r"[ \-]+", raw, maxsplit=1)
    local = re.sub(r"[ \-]", "", local)
    split = {8: 4, 7: 3, 6: 3}.get(len(local), len(local))
    return [std, local[:split], local[split:]] if split < len(local) else [std, local]


def apply_phones(text: str, lang: BaseLang) -> str:
    def landline(m: re.Match[str]) -> str:
        raw = m.group("num")
        if len(re.sub(r"\D", "", raw)) != 11:  # STD code + local number, with the 0
            return raw
        return mark(_read(_landline_groups(raw), lang))

    text = _MOBILE.sub(lambda m: mark(_read(_groups(m.group("num"), (5, 5)), lang)), text)
    text = _TOLL_FREE.sub(lambda m: mark(_read(_groups(m.group("num"), (4, 3, 3)), lang)), text)
    text = _LANDLINE.sub(landline, text)
    return _INTERNATIONAL.sub(
        lambda m: mark(_read(_groups(m.group("num"), (3, 3, 4)), lang, plus=True)), text
    )


def spell_phone(number: str, lang: str) -> str:
    """Read a phone number aloud: "+91 98765 43210" -> "nine eight seven six five, ...".

    Code-mixed speakers ("te-en", "hi-en") read phone numbers in English digits.
    """
    language = digits_lang(check_lang(lang))
    stripped = number.strip()
    if not re.fullmatch(r"\+?[\d \-()]+", stripped) or not re.search(r"\d", stripped):
        raise ValueError(f"not a phone number: {number!r}")
    cleaned = re.sub(r"[()]", "", stripped)
    spoken = apply_phones(cleaned, language)
    if spoken != cleaned:
        return finalize(spoken, language)
    digits = re.sub(r"\D", "", cleaned)
    return _read(_groups(digits, (3, 3, 4)), language, plus=cleaned.startswith("+"))
