"""Telugu number words (Telugu script), Indian system.

TODO: native-speaker review for hi/te tables.

Telugu numerals change shape with what follows them, so ``cardinal`` takes a form:

- ``plain``: the number on its own. 500 -> ఐదు వందలు, 1,20,000 -> ఒక లక్ష ఇరవై వేలు.
- ``oblique``: before a postposition (నుండి, వరకు). The last scale word takes its
  combining form: ఐదు వందల వరకు, రెండు వేల నుండి.
- ``attr``: before a counted noun (రూపాయలు, రోజులు). Oblique, plus 1 becomes ఒక
  (or ఒక్క inside a compound): ఒక రోజు, ఇరవై ఒక్క రూపాయలు, ఐదు వందల రూపాయలు.

1100-1999 are a count of hundreds (confirmed by the founder): పదకొండు వందలు,
పన్నెండు వందల యాభై, పదిహేను వందల రూపాయలు. 1000-1099 stay వెయ్యి ... (వెయ్యి యాభై).

Scale words: వంద / నూట (100 alone / 100 followed by more, e.g. నూట ఇరవై),
N వందలు / N వందల, వెయ్యి (1000), N వేలు / N వేల, ఒక లక్ష, N లక్షలు / N లక్షల,
ఒక కోటి, N కోట్లు / N కోట్ల.
"""

from __future__ import annotations

from typing import Literal

TeForm = Literal["plain", "oblique", "attr"]

_TE_0_19: tuple[str, ...] = tuple(
    """
    సున్నా ఒకటి రెండు మూడు నాలుగు ఐదు ఆరు ఏడు ఎనిమిది తొమ్మిది
    పది పదకొండు పన్నెండు పదమూడు పద్నాలుగు పదిహేను పదహారు పదిహేడు పద్దెనిమిది పంతొమ్మిది
    """.split()
)
_TE_TENS = {
    2: "ఇరవై",
    3: "ముప్పై",
    4: "నలభై",
    5: "యాభై",
    6: "అరవై",
    7: "డెబ్బై",
    8: "ఎనభై",
    9: "తొంభై",
}

DIGITS: tuple[str, ...] = _TE_0_19[:10]
HALF_SUFFIX = "న్నర"


def _below_100(n: int, form: TeForm, compound: bool) -> str:
    if n < 20:
        if n == 1 and form == "attr":
            return "ఒక్క" if compound else "ఒక"
        return _TE_0_19[n]
    tens, unit = divmod(n, 10)
    word = _TE_TENS[tens]
    if unit:
        word += " " + _below_100(unit, form, compound=True)
    return word


def _scale(
    multiplier: int, singular: str, plural: str, combining: str, final: bool, form: TeForm
) -> str:
    if multiplier == 1:
        return singular
    word = plural if final and form == "plain" else combining
    return f"{cardinal(multiplier, 'attr')} {word}"


def cardinal(n: int, form: TeForm = "plain") -> str:
    if n < 0:
        raise ValueError("negative numbers are not supported")
    if n == 0:
        return _TE_0_19[0]
    if 1100 <= n <= 1999:
        # Spoken as a count of hundreds: పదకొండు వందలు, పన్నెండు వందల యాభై.
        hundreds, rest = divmod(n, 100)
        word = "వందలు" if rest == 0 and form == "plain" else "వందల"
        head = f"{_TE_0_19[hundreds]} {word}"
        return f"{head} {_below_100(rest, form, compound=True)}" if rest else head
    crore, rest = divmod(n, 10**7)
    lakh, rest = divmod(rest, 10**5)
    thousand, rest = divmod(rest, 1000)
    hundred, rest = divmod(rest, 100)
    parts: list[str] = []
    if crore:
        final = n % 10**7 == 0
        parts.append(_scale(crore, "ఒక కోటి", "కోట్లు", "కోట్ల", final, form))
    if lakh:
        final = n % 10**5 == 0
        parts.append(_scale(lakh, "ఒక లక్ష", "లక్షలు", "లక్షల", final, form))
    if thousand:
        final = n % 1000 == 0
        parts.append(_scale(thousand, "వెయ్యి", "వేలు", "వేల", final, form))
    if hundred:
        final = n % 100 == 0
        if hundred == 1:
            parts.append("వంద" if final else "నూట")
        else:
            word = "వందలు" if final and form == "plain" else "వందల"
            parts.append(f"{_TE_0_19[hundred]} {word}")
    if rest:
        parts.append(_below_100(rest, form, compound=bool(parts)))
    return " ".join(parts)


def ordinal(n: int) -> str:
    """మొదటి, రెండవ, మూడవ, ..., ఇరవయ్యవ, వందవ."""
    if n == 1:
        return "మొదటి"
    words = cardinal(n)
    if words.endswith("ై"):
        return words[:-1] + "య్యవ"
    if words.endswith(("ు", "ి")):
        return words[:-1] + "వ"
    return words + "వ"


def half(n: int) -> str:
    """n and a half: ఒకటిన్నర (1.5), రెండున్నర (2.5), పదిన్నర (10.5)."""
    return _TE_0_19[n] + HALF_SUFFIX if n < 20 else cardinal(n) + HALF_SUFFIX


def year(n: int) -> str:
    # 1100-1999 already read as a count of hundreds (పంతొమ్మిది వందల తొంభై ఐదు).
    return cardinal(n)


def oblique_phrase(phrase: str) -> str:
    """Put a generated phrase into combining form: గంటలు -> గంటల, రూపాయలు -> రూపాయల."""
    return phrase[:-2] + "ల" if phrase.endswith("లు") else phrase


def merge_suffix(phrase: str, suffix: str) -> str:
    """Attach the dative కి/కు: గంటలు + కి -> గంటలకి, ఆరున్నర + కి -> ఆరున్నరకి."""
    return oblique_phrase(phrase) + suffix
