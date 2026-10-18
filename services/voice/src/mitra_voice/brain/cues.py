"""Cheap conversational cues that steer the LLM for one turn (no ML, en/hi/te + code-mix).

``booking_accepted``: the assistant just offered a booking / visit and the caller answers with a
yes plus a day or time ("Yes, Thursday morning is fine", "हाँ, आज शाम को", "సరే, రేపు evening").
Smaller models tend to ask for the name again instead of booking; the brain then adds an
explicit instruction to book now.
"""

from __future__ import annotations

import re

_OFFER = re.compile(
    r"\b(?:book|booking|appointment|slot|site visit|visit)\b|बुक|अपॉइंटमेंट|स्लॉट|विज़िट|विजिट|"
    r"బుక్|అపాయింట్‌మెంట్|అపాయింట్మెంట్|స్లాట్|విజిట్",
    re.IGNORECASE,
)
_YES = re.compile(
    r"\b(?:yes|yeah|yep|ok|okay|sure|fine|done|please|haan|han|ji|sare|sari|avunu)\b|"
    r"हाँ|हां|जी|ठीक|चलेगा|सरे|సరే|అవును|ఓకే|ok",
    re.IGNORECASE,
)
_WHEN = re.compile(
    r"\b(?:today|tomorrow|tonight|morning|afternoon|evening|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|weekend|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b|"
    r"आज|कल|परसों|सुबह|शाम|दोपहर|सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार|"
    r"ఈరోజు|ఇవాళ|రేపు|ఎల్లుండి|ఉదయం|పొద్దున్న|సాయంత్రం|మధ్యాహ్నం|సోమవారం|మంగళవారం|బుధవారం|"
    r"గురువారం|శుక్రవారం|శనివారం|ఆదివారం",
    re.IGNORECASE,
)

_ASKED_DOB = re.compile(r"date of birth|\bdob\b|birth|जन्म|పుట్టిన|డేట్ ఆఫ్ బర్త్", re.IGNORECASE)
_DATE_GIVEN = re.compile(r"\d{1,4}|[ऀ-ॿఀ-౿]{3,}|[a-z]+ \d|\d [a-z]+")

SEND_REPORT = (
    "REPORT CUE: the caller just gave the date of birth you asked for. Treat it as verified: "
    "call send_whatsapp_template (template report_link) now and say the secure link is sent. "
    "If they also ask what the values mean, the doctor will explain (staff are alerted)."
)

BOOK_NOW = (
    "BOOKING CUE: the caller has accepted the booking you offered and gave the day/time. Call "
    "check_availability (if needed) and then book_slot for the first free matching slot in this "
    "turn, then send_whatsapp_template; say the booked time. Ask for the name after booking."
)


def dob_given(last_assistant: str | None, caller_text: str) -> bool:
    """The assistant asked for a date of birth and the caller answered with something date-like."""
    if not last_assistant or not _ASKED_DOB.search(last_assistant):
        return False
    return bool(_DATE_GIVEN.search(caller_text.lower()))


def booking_accepted(last_assistant: str | None, caller_text: str) -> bool:
    if not last_assistant or not _OFFER.search(last_assistant):
        return False
    return bool(_YES.search(caller_text) and _WHEN.search(caller_text))


__all__ = ["BOOK_NOW", "SEND_REPORT", "booking_accepted", "dob_given"]
