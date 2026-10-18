"""Bookkeeping shared by the speakable rules.

Generated phrases are wrapped in private-use sentinels while the rules run, so that
later rules never re-read them and the final Telugu pass can attach a following
కి/కు to *our* phrase only (గంటలు కి -> గంటలకి) without touching the LLM's own words.
"""

from __future__ import annotations

import re

from mitra_human._lang import TELUGU, Lang
from mitra_human._num_te import TeForm, merge_suffix

OPEN = "\ue010"
CLOSE = "\ue011"

_TE_MERGE = re.compile(
    rf"{OPEN}([^{OPEN}{CLOSE}]*){CLOSE} ?(కి|కు)(?![{TELUGU}])",
)
_SENTINELS = re.compile(f"[{OPEN}{CLOSE}]")

_NEXT_WORD = re.compile(rf"[ \t]?([{TELUGU}\u200c\u200d]+|[A-Za-z]+)")
_TE_POSTPOSITIONS = frozenset(("నుండి", "నుంచి", "వరకు", "వరకూ", "దాకా", "తో", "లో", "కంటే", "లోపు", "పైన"))
# Words that follow a bare number as a predicate, not as the counted noun.
_TE_PLAIN_PREFIXES = ("ఉన్న", "ఉంది", "ఉంటు", "అవు", "అయ", "కావా", "మాత్రమే", "కూడా", "ఇవ్వ", "చెప్ప")


def mark(phrase: str) -> str:
    return f"{OPEN}{phrase}{CLOSE}"


def finalize(text: str, lang: Lang) -> str:
    if lang == "te":
        text = _TE_MERGE.sub(lambda m: mark(merge_suffix(m.group(1), m.group(2))), text)
    return _SENTINELS.sub("", text)


def te_form_after(rest: str) -> TeForm:
    """Pick the Telugu numeral form from the word that follows the number."""
    m = _NEXT_WORD.match(rest)
    if m is None:
        return "plain"
    word = m.group(1)
    if word in ("కి", "కు"):
        return "plain"  # merged later: వందలు + కి -> వందలకి
    if word in _TE_POSTPOSITIONS:
        return "oblique"
    if word.startswith(_TE_PLAIN_PREFIXES):
        return "plain"
    return "attr"
