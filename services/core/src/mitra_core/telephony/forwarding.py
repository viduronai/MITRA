"""Missed/busy call-forwarding codes per Indian operator (NUM-02, onboarding step 6).

Airtel, Vi and BSNL use the standard GSM MMI codes (3GPP TS 22.030: ``**67*`` busy, ``**61*``
no answer, ``**62*`` unreachable, ``##004#`` cancel all conditional). Jio uses its own star-4
codes (``*405*`` busy, ``*403*`` no answer, ``*409*`` unreachable, ``*413`` cancel). We only
forward *conditional* calls (busy / no answer / unreachable): the owner keeps answering their
own phone and Mitra picks up what they miss. Codes can change; the UI tells the owner to use the
"Test forwarding" button after dialling them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Operator = Literal["jio", "airtel", "vi", "bsnl"]
OPERATORS: tuple[Operator, ...] = ("jio", "airtel", "vi", "bsnl")
OPERATOR_NAMES: dict[Operator, str] = {
    "jio": "Jio",
    "airtel": "Airtel",
    "vi": "Vi",
    "bsnl": "BSNL",
}


@dataclass(frozen=True, slots=True)
class ForwardingCodes:
    operator: Operator
    name: str
    busy: str
    no_answer: str
    unreachable: str
    cancel: str


def dial_form(e164: str, *, mobile: bool = False) -> str:
    """The number as dialled from an Indian phone: +91 40 4123 4567 -> 04041234567.

    Mobiles are dialled as 10 digits. The digits alone cannot tell them apart (Vijayawada's
    0866 landlines and the 8xxxx mobile series share a first digit), so the caller says which.
    """
    if not e164.startswith("+91"):
        return e164
    national = e164[3:]
    return national if mobile else "0" + national


def codes_for(target_e164: str, *, mobile: bool = False) -> list[ForwardingCodes]:
    n = dial_form(target_e164, mobile=mobile)
    out = []
    for op in OPERATORS:
        if op == "jio":
            out.append(ForwardingCodes(op, "Jio", f"*405*{n}", f"*403*{n}", f"*409*{n}", "*413"))
        else:
            out.append(
                ForwardingCodes(
                    op,
                    OPERATOR_NAMES[op],
                    f"**67*{n}#",
                    f"**61*{n}#",
                    f"**62*{n}#",
                    "##004#",
                )
            )
    return out
