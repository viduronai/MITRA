"""Hindi number words (Devanagari), Indian system.

TODO: native-speaker review for hi/te tables.

Hindi 0-99 are irregular, so they are an explicit table rather than tens + units.
Spellings follow standard Hindi: nukta in हज़ार, chandrabindu in पाँच, छह (not छः).
"""

from __future__ import annotations

_HI_0_99: tuple[str, ...] = tuple(
    """
    शून्य एक दो तीन चार पाँच छह सात आठ नौ
    दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस
    बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस
    तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस
    चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास
    पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ
    साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर
    सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी
    अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी
    नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे
    """.split()
)

DIGITS: tuple[str, ...] = _HI_0_99[:10]
# Telecallers say "ज़ीरो" when reading phone numbers, not "शून्य".
PHONE_DIGITS: tuple[str, ...] = ("ज़ीरो", *_HI_0_99[1:10])

_HALVES = {1: "डेढ़", 2: "ढाई"}
_ORDINALS = {1: "पहला", 2: "दूसरा", 3: "तीसरा", 4: "चौथा", 6: "छठा"}


def below_100(n: int) -> str:
    return _HI_0_99[n]


def cardinal(n: int) -> str:
    if n < 0:
        raise ValueError("negative numbers are not supported")
    if n < 100:
        return _HI_0_99[n]
    crore, rest = divmod(n, 10**7)
    lakh, rest = divmod(rest, 10**5)
    thousand, rest = divmod(rest, 1000)
    hundred, rest = divmod(rest, 100)
    parts: list[str] = []
    if crore:
        parts.append(f"{cardinal(crore)} करोड़")
    if lakh:
        parts.append(f"{_HI_0_99[lakh]} लाख")
    if thousand:
        parts.append(f"{_HI_0_99[thousand]} हज़ार")
    if hundred:
        parts.append(f"{_HI_0_99[hundred]} सौ")
    if rest:
        parts.append(_HI_0_99[rest])
    return " ".join(parts)


def ordinal(n: int) -> str:
    """Masculine ordinal (पहला, दूसरा, ..., पाँचवाँ)."""
    return _ORDINALS.get(n) or f"{cardinal(n)}वाँ"


def half(n: int) -> str:
    """n and a half: डेढ़ (1.5), ढाई (2.5), साढ़े तीन (3.5) ..."""
    return _HALVES.get(n) or f"साढ़े {cardinal(n)}"


def year(n: int) -> str:
    if 1100 <= n <= 1999 and n % 100:
        century, rest = divmod(n, 100)
        return f"{_HI_0_99[century]} सौ {_HI_0_99[rest]}"
    return cardinal(n)
