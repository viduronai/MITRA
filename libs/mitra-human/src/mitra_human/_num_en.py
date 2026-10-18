"""English number words in the Indian system (lakh, crore) with British "and"."""

from __future__ import annotations

_ONES = tuple(
    """
    zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen
    fifteen sixteen seventeen eighteen nineteen
    """.split()
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_IRREGULAR_ORDINALS = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}

DIGITS: tuple[str, ...] = tuple(_ONES[:10])


def below_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, unit = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[unit]}" if unit else "")


def cardinal(n: int) -> str:
    if n < 0:
        raise ValueError("negative numbers are not supported")
    if n == 0:
        return "zero"
    crore, rest = divmod(n, 10**7)
    lakh, rest = divmod(rest, 10**5)
    thousand, rest = divmod(rest, 1000)
    hundred, rest = divmod(rest, 100)
    parts: list[str] = []
    if crore:
        parts.append(f"{cardinal(crore)} crore")
    if lakh:
        parts.append(f"{below_100(lakh)} lakh")
    if thousand:
        parts.append(f"{below_100(thousand)} thousand")
    if hundred:
        parts.append(f"{_ONES[hundred]} hundred")
    if rest:
        parts.append(("and " if parts else "") + below_100(rest))
    return " ".join(parts)


def ordinal(n: int) -> str:
    words = cardinal(n)
    cut = max(words.rfind(" "), words.rfind("-")) + 1
    head, last = words[:cut], words[cut:]
    if last in _IRREGULAR_ORDINALS:
        last = _IRREGULAR_ORDINALS[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return head + last


def half(n: int) -> str:
    return f"{cardinal(n)} and a half"


def year(n: int) -> str:
    if 2000 <= n <= 2099:
        rest = n - 2000
        return "two thousand" + (f" {below_100(rest)}" if rest else "")
    if 1100 <= n <= 1999:
        century, rest = divmod(n, 100)
        if rest == 0:
            return f"{below_100(century)} hundred"
        tail = f"oh {_ONES[rest]}" if rest < 10 else below_100(rest)
        return f"{below_100(century)} {tail}"
    return cardinal(n)
