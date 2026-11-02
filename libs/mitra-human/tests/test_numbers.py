"""Cardinal numbers in en/hi/te, through ``speakable`` and ``number_to_words``."""

from __future__ import annotations

import pytest

from mitra_human import Lang, number_to_words, speakable
from mitra_human._lang import BaseLang
from mitra_human.numwords import half, ordinal, year

# Hindi 1-99, typed out independently of the library table.
HINDI_1_99 = {
    1: "एक", 2: "दो", 3: "तीन", 4: "चार", 5: "पाँच", 6: "छह", 7: "सात", 8: "आठ", 9: "नौ",
    10: "दस", 11: "ग्यारह", 12: "बारह", 13: "तेरह", 14: "चौदह", 15: "पंद्रह", 16: "सोलह",
    17: "सत्रह", 18: "अठारह", 19: "उन्नीस", 20: "बीस", 21: "इक्कीस", 22: "बाईस", 23: "तेईस",
    24: "चौबीस", 25: "पच्चीस", 26: "छब्बीस", 27: "सत्ताईस", 28: "अट्ठाईस", 29: "उनतीस",
    30: "तीस", 31: "इकतीस", 32: "बत्तीस", 33: "तैंतीस", 34: "चौंतीस", 35: "पैंतीस",
    36: "छत्तीस", 37: "सैंतीस", 38: "अड़तीस", 39: "उनतालीस", 40: "चालीस", 41: "इकतालीस",
    42: "बयालीस", 43: "तैंतालीस", 44: "चवालीस", 45: "पैंतालीस", 46: "छियालीस",
    47: "सैंतालीस", 48: "अड़तालीस", 49: "उनचास", 50: "पचास", 51: "इक्यावन", 52: "बावन",
    53: "तिरेपन", 54: "चौवन", 55: "पचपन", 56: "छप्पन", 57: "सत्तावन", 58: "अट्ठावन",
    59: "उनसठ", 60: "साठ", 61: "इकसठ", 62: "बासठ", 63: "तिरसठ", 64: "चौंसठ", 65: "पैंसठ",
    66: "छियासठ", 67: "सड़सठ", 68: "अड़सठ", 69: "उनहत्तर", 70: "सत्तर", 71: "इकहत्तर",
    72: "बहत्तर", 73: "तिहत्तर", 74: "चौहत्तर", 75: "पचहत्तर", 76: "छिहत्तर", 77: "सतहत्तर",
    78: "अठहत्तर", 79: "उन्यासी", 80: "अस्सी", 81: "इक्यासी", 82: "बयासी", 83: "तिरासी",
    84: "चौरासी", 85: "पचासी", 86: "छियासी", 87: "सत्तासी", 88: "अट्ठासी", 89: "नवासी",
    90: "नब्बे", 91: "इक्यानवे", 92: "बानवे", 93: "तिरानवे", 94: "चौरानवे", 95: "पचानवे",
    96: "छियानवे", 97: "सत्तानवे", 98: "अट्ठानवे", 99: "निन्यानवे",
}  # fmt: skip


@pytest.mark.parametrize(("n", "word"), sorted(HINDI_1_99.items()))
def test_hindi_1_to_99(n: int, word: str) -> None:
    assert speakable(str(n), "hi") == word


BOUNDARIES = {
    "en": {
        0: "zero",
        100: "one hundred",
        101: "one hundred and one",
        999: "nine hundred and ninety-nine",
        1000: "one thousand",
        1001: "one thousand and one",
        99999: "ninety-nine thousand nine hundred and ninety-nine",
        100000: "one lakh",
        120000: "one lakh twenty thousand",
        1000000: "ten lakh",
        10000000: "one crore",
        999999999: "ninety-nine crore ninety-nine lakh ninety-nine thousand nine hundred"
        " and ninety-nine",
    },
    "hi": {
        0: "शून्य",
        100: "एक सौ",
        101: "एक सौ एक",
        999: "नौ सौ निन्यानवे",
        1000: "एक हज़ार",
        1001: "एक हज़ार एक",
        99999: "निन्यानवे हज़ार नौ सौ निन्यानवे",
        100000: "एक लाख",
        120000: "एक लाख बीस हज़ार",
        1000000: "दस लाख",
        10000000: "एक करोड़",
        999999999: "निन्यानवे करोड़ निन्यानवे लाख निन्यानवे हज़ार नौ सौ निन्यानवे",
    },
    "te": {
        0: "సున్నా",
        100: "వంద",
        101: "నూట ఒకటి",
        999: "తొమ్మిది వందల తొంభై తొమ్మిది",
        1000: "వెయ్యి",
        1001: "వెయ్యి ఒకటి",
        99999: "తొంభై తొమ్మిది వేల తొమ్మిది వందల తొంభై తొమ్మిది",
        100000: "ఒక లక్ష",
        120000: "ఒక లక్ష ఇరవై వేలు",
        1000000: "పది లక్షలు",
        10000000: "ఒక కోటి",
        999999999: "తొంభై తొమ్మిది కోట్ల తొంభై తొమ్మిది లక్షల తొంభై తొమ్మిది వేల తొమ్మిది వందల తొంభై తొమ్మిది",
    },
}
BOUNDARY_CASES = [(lang, n, w) for lang, table in BOUNDARIES.items() for n, w in table.items()]


@pytest.mark.parametrize(("lang", "n", "expected"), BOUNDARY_CASES)
def test_boundaries_via_speakable(lang: Lang, n: int, expected: str) -> None:
    assert speakable(str(n), lang) == expected


@pytest.mark.parametrize(("lang", "n", "expected"), BOUNDARY_CASES)
def test_boundaries_via_number_to_words(lang: Lang, n: int, expected: str) -> None:
    assert number_to_words(n, lang) == expected


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("99,99,99,999", "en", BOUNDARIES["en"][999999999]),
        ("99,99,99,999", "hi", "निन्यानवे करोड़ निन्यानवे लाख निन्यानवे हज़ार नौ सौ निन्यानवे"),
        ("1,20,000", "en", "one lakh twenty thousand"),
        ("120,000", "en", "one lakh twenty thousand"),
        ("2,50,00,000", "hi", "दो करोड़ पचास लाख"),
        ("21", "en", "twenty-one"),
        ("45", "en", "forty-five"),
        ("110", "en", "one hundred and ten"),
        ("1100", "te", "పదకొండు వందలు"),
        ("120", "te", "నూట ఇరవై"),
        ("200", "te", "రెండు వందలు"),
        ("201", "te", "రెండు వందల ఒకటి"),
        ("2000", "te", "రెండు వేలు"),
        ("2500", "te", "రెండు వేల ఐదు వందలు"),
        ("21000", "te", "ఇరవై ఒక్క వేలు"),
        ("200000", "te", "రెండు లక్షలు"),
        ("20000000", "te", "రెండు కోట్లు"),
        ("12000000", "te", "ఒక కోటి ఇరవై లక్షలు"),
        ("35", "te", "ముప్పై ఐదు"),
        ("19", "te", "పంతొమ్మిది"),
        ("18", "te", "పద్దెనిమిది"),
        ("90", "te", "తొంభై"),
        ("1,000,000,000", "en", "one hundred crore"),
    ],
)
def test_more_cardinals(text: str, lang: Lang, expected: str) -> None:
    assert speakable(text, lang) == expected


@pytest.mark.parametrize(
    ("n", "lang", "expected"),
    [
        (1, "en", "first"),
        (2, "en", "second"),
        (3, "en", "third"),
        (5, "en", "fifth"),
        (12, "en", "twelfth"),
        (20, "en", "twentieth"),
        (21, "en", "twenty-first"),
        (100, "en", "one hundredth"),
        (1, "hi", "पहला"),
        (4, "hi", "चौथा"),
        (6, "hi", "छठा"),
        (5, "hi", "पाँचवाँ"),
        (1, "te", "మొదటి"),
        (2, "te", "రెండవ"),
        (8, "te", "ఎనిమిదవ"),
        (20, "te", "ఇరవయ్యవ"),
        (100, "te", "వందవ"),
    ],
)
def test_ordinals(n: int, lang: BaseLang, expected: str) -> None:
    assert ordinal(n, lang) == expected


@pytest.mark.parametrize(
    ("n", "lang", "expected"),
    [
        (1, "hi", "डेढ़"),
        (2, "hi", "ढाई"),
        (3, "hi", "साढ़े तीन"),
        (1, "te", "ఒకటిన్నర"),
        (2, "te", "రెండున్నర"),
        (10, "te", "పదిన్నర"),
        (2, "en", "two and a half"),
    ],
)
def test_halves(n: int, lang: BaseLang, expected: str) -> None:
    assert half(n, lang) == expected


@pytest.mark.parametrize(
    ("n", "lang", "expected"),
    [
        (2026, "en", "two thousand twenty-six"),
        (2000, "en", "two thousand"),
        (1995, "en", "nineteen ninety-five"),
        (1905, "en", "nineteen oh five"),
        (1900, "en", "nineteen hundred"),
        (2026, "hi", "दो हज़ार छब्बीस"),
        (1995, "hi", "उन्नीस सौ पचानवे"),
        (2026, "te", "రెండు వేల ఇరవై ఆరు"),
        (1995, "te", "పంతొమ్మిది వందల తొంభై ఐదు"),
    ],
)
def test_years(n: int, lang: BaseLang, expected: str) -> None:
    assert year(n, lang) == expected


def test_number_to_words_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="unsupported language"):
        number_to_words(5, "ta")
    with pytest.raises(ValueError, match="negative"):
        number_to_words(-1, "en")


# 1100-1999 are a count of hundreds in spoken Telugu (confirmed by the founder);
# 1000-1099 keep వెయ్యి. Every Telugu numeral form is covered.
TELUGU_HUNDREDS: list[tuple[str, str]] = [
    # plain
    ("1100", "పదకొండు వందలు"),
    ("1101", "పదకొండు వందల ఒకటి"),
    ("1250", "పన్నెండు వందల యాభై"),
    ("1500", "పదిహేను వందలు"),
    ("1999", "పంతొమ్మిది వందల తొంభై తొమ్మిది"),
    ("1,800", "పద్దెనిమిది వందలు"),
    ("1000", "వెయ్యి"),
    ("1050", "వెయ్యి యాభై"),
    ("1099", "వెయ్యి తొంభై తొమ్మిది"),
    # before a noun (attributive)
    ("1100 రూపాయలు", "పదకొండు వందల రూపాయలు"),
    ("1500 మంది", "పదిహేను వందల మంది"),
    ("1101 రూపాయలు", "పదకొండు వందల ఒక్క రూపాయలు"),
    ("1050 రూపాయలు", "వెయ్యి యాభై రూపాయలు"),
    ("₹1500", "పదిహేను వందల రూపాయలు"),
    ("₹1,250", "పన్నెండు వందల యాభై రూపాయలు"),
    # before a postposition (oblique)
    ("1500 వరకు", "పదిహేను వందల వరకు"),
    ("1250 నుండి", "పన్నెండు వందల యాభై నుండి"),
    # కి / కు merge
    ("1500 కి", "పదిహేను వందలకి"),
    ("1100 కు", "పదకొండు వందలకు"),
    ("1250 కి", "పన్నెండు వందల యాభైకి"),
    ("₹1500 కి", "పదిహేను వందల రూపాయలకి"),
    # ranges
    ("1100-1500 రూపాయలు", "పదకొండు వందల నుండి పదిహేను వందల రూపాయలు"),
    ("₹1100–1500", "పదకొండు వందల నుండి పదిహేను వందల రూపాయల వరకు"),
    # outside the range: thousand / lakh forms unchanged
    ("11,500", "పదకొండు వేల ఐదు వందలు"),
    ("1,01,500", "ఒక లక్ష వెయ్యి ఐదు వందలు"),
    ("2100", "రెండు వేల వంద"),
]


@pytest.mark.parametrize(("text", "expected"), TELUGU_HUNDREDS)
def test_telugu_count_of_hundreds(text: str, expected: str) -> None:
    assert speakable(text, "te") == expected


def test_telugu_count_of_hundreds_number_to_words() -> None:
    assert number_to_words(1500, "te") == "పదిహేను వందలు"
    assert number_to_words(1500, "hi") == "एक हज़ार पाँच सौ"
    assert number_to_words(1500, "en") == "one thousand five hundred"
