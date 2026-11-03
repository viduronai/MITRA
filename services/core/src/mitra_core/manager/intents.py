"""Owner message -> intent (WORKFLOWS §8). Deterministic rules for te / hi / en (incl. Tenglish
and Hinglish); an optional LLM planner (``planner.py``) may fill the same ``Intent`` instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Lang = Literal["en", "hi", "te"]
IntentName = Literal[
    "summary",
    "attention",
    "bookings",
    "search",
    "customer",
    "wallet",
    "unknown_questions",
    "team",
    "pause",
    "resume",
    "callback",
    "call_list",
    "coach",
    "payment_link",
    "payments",
    "help",
    "unknown",
]
QUESTION_INTENTS = frozenset(
    {
        "summary",
        "attention",
        "bookings",
        "search",
        "customer",
        "wallet",
        "unknown_questions",
        "team",
        "help",
        "payments",
        "unknown",
    }
)
COMMAND_INTENTS = frozenset({"pause", "resume", "callback", "call_list", "coach", "payment_link"})


@dataclass(slots=True)
class Intent:
    name: IntentName
    lang: Lang = "en"
    period: Literal["today", "yesterday", "week"] = "today"
    query: str = ""  # search term, customer name or employee name
    when: str = ""  # callback time as said ("5", "5:30 pm")
    results: list[str] = field(default_factory=list)  # call_list filter
    day_offset: int = 0  # bookings: 0 today, 1 tomorrow
    text: str = ""  # coaching instruction; payment link purpose
    amount_paise: int = 0  # payment link amount


_TE_SCRIPT = re.compile(r"[ఀ-౿]")
_HI_SCRIPT = re.compile(r"[ऀ-ॿ]")
_HI_WORDS = re.compile(
    r"\b(kya|kitne|kitni|kal|aaj|batao|hai|hain|kaun|mujhe|karo|agli baar|hafte)\b"
)
_TE_WORDS = re.compile(
    r"\b(enni|ninna|repu|eroju|ivala|cheppu|undi|emi|evaru|chey|cheyyi|vaaram)\b"
)


def detect_language(text: str) -> Lang:
    if _TE_SCRIPT.search(text):
        return "te"
    if _HI_SCRIPT.search(text):
        return "hi"
    low = text.lower()
    te, hi = len(_TE_WORDS.findall(low)), len(_HI_WORDS.findall(low))
    if te > hi:
        return "te"
    if hi > te:
        return "hi"
    return "en"


def _has(low: str, *words: str) -> bool:
    return any(w in low for w in words)


def _period(low: str) -> Literal["today", "yesterday", "week"]:
    if _has(low, "week", "hafte", "हफ्ते", "सप्ताह", "vaaram", "వారం"):
        return "week"
    if _has(low, "yesterday", "ninna", "నిన్న", "कल रात", "beeta kal", "बीते कल"):
        return "yesterday"
    return "today"


_COACH = re.compile(
    r"^\s*(?:tell\s+(?P<emp>\w+)\s+(?:to\s+)?)?(?P<body>(?:next time|from now on|always|never|"
    r"agli baar|aage se|hamesha|kabhi mat|inka nunchi|ikapai|eppudu|అగ్లీ|ఇకపై|ఎప్పుడూ|अगली बार|"
    r"आगे से|हमेशा).*)$",
    re.IGNORECASE,
)
_PAUSE = re.compile(r"\b(?:pause|stop|hold|rok(?:o|do)?)\s+(?P<name>[A-Za-z]\w*)", re.IGNORECASE)
_RESUME = re.compile(r"\b(?:resume|unpause|restart|start)\s+(?P<name>[A-Za-z]\w*)", re.IGNORECASE)
_CALLBACK = re.compile(
    r"\bcall\s+(?P<name>[A-Za-z]\w*)\s+back(?:\s+(?:at|by)\s+(?P<when>[\w: .]+))?"
    r"|\bcall\s*back\s+(?P<name2>[A-Za-z]\w*)(?:\s+(?:at|by)\s+(?P<when2>[\w: .]+))?",
    re.IGNORECASE,
)
_AMOUNT = r"(?:₹|rs\.?|inr|rupees)?\s*(?P<amt>\d[\d,]*(?:\.\d{1,2})?)\s*(?:rupees|rs)?"
_PAY_LINK = re.compile(
    r"send\s+(?:a\s+)?payment\s+link\s+(?:to\s+)?(?P<name2>[A-Za-z]\w*)\s+(?:for|of)\s+"
    + _AMOUNT
    + r"|send\s+(?P<name>[A-Za-z]\w*)\s+(?:a\s+)?payment\s+link\s+(?:for|of)\s+"
    + _AMOUNT.replace("amt", "amt2"),
    re.IGNORECASE,
)
_PAY_PURPOSE = re.compile(r"\b(?:for|towards)\s+(?P<purpose>[^\d₹].{1,120}?)[?.!]*$", re.I)
_CALL_LIST = re.compile(r"\bcall\s+(?:all|every(?:one|body)?|the)\b", re.IGNORECASE)
_SEARCH = re.compile(
    r"\b(?:who|anyone|anybody|kaun|evaru)\b.*?\b(?:called|asked|call kiya|phone chesaru)\b"
    r"(?:\s+(?:about|for|regarding|ke baare mein))?\s+(?P<q>.+?)[?.!]*$",
    re.IGNORECASE,
)
_CUSTOMER = re.compile(
    r"\b(?:tell me about|what about|details of|who is)\s+(?P<name>[A-Za-z][\w ]{1,40}?)[?.!]*$",
    re.IGNORECASE,
)

_RESULT_WORDS = {
    "maybe": ["interested", "call_back"],
    "interested": ["interested"],
    "call back": ["call_back"],
    "callback": ["call_back"],
    "missed": ["missed"],
    "not interested": ["not_interested"],
}


# Money questions (who paid / what's pending / how much collected), en / hi / te.
_PAY_WORDS = (
    "paid", "payment", "collect", "revenue", "earned", "pending payment", "dues", "owe", "unpaid",
    "पेमेंट", "भुगतान", "पैसे", "पैसा", "बकाया", "किसने pay", "kisne pay", "paisa", "paise",
    "bakaya", "पेड", "పేమెంట్", "డబ్బు", "కట్టారు", "కట్టలేదు", "చెల్లించ", "బాకీ", "వసూలు",
    "dabbulu", "kattaru", "vasool",
)  # fmt: skip
_PAY_PENDING = (
    "pending", "due", "owe", "unpaid", "not paid", "yet to pay", "बकाया", "बाकी", "baki",
    "bakaya", "नहीं दिया", "బాకీ", "కట్టలేదు", "ఇంకా", "pending",
)  # fmt: skip
_PAY_COLLECTED = (
    "collect", "revenue", "earned", "how much", "total", "कितना", "कितने", "जमा", "kitna", "ఎంత",
    "వసూలు", "vasool", "enta",
)  # fmt: skip
# A call summary needs a word about calls or "what happened"; otherwise the answer is "unknown".
_SUMMARY_WORDS = (
    "call", "happen", "how did", "how was", "report", "summary", "update",
    "कॉल", "हुआ", "hua", "हाल", "కాల్", "ఏమైంది", "జరిగింది", "emaindi", "jarigindi",
)  # fmt: skip


def _payment_question(low: str) -> str | None:
    if not _has(low, *_PAY_WORDS):
        return None
    if _has(low, *_PAY_PENDING):
        return "pending"
    if _has(low, *_PAY_COLLECTED):
        return "collected"
    return "paid"


def parse(text: str) -> Intent:
    lang = detect_language(text)
    raw = " ".join(text.split())[:500]
    low = raw.lower()

    if m := _PAY_LINK.search(raw):
        amount = (m.group("amt") or m.group("amt2") or "0").replace(",", "")
        rest = raw[m.end() :]
        purpose = _PAY_PURPOSE.search(rest)
        return Intent(
            "payment_link",
            lang,
            query=m.group("name") or m.group("name2") or "",
            amount_paise=round(float(amount) * 100),
            text=purpose.group("purpose").strip() if purpose else "",
        )
    if kind := _payment_question(low):
        return Intent("payments", lang, period=_period(low), text=kind)
    if m := _COACH.match(raw):
        return Intent("coach", lang, query=m.group("emp") or "", text=m.group("body").strip()[:200])
    if m := _CALLBACK.search(raw):
        name = m.group("name") or m.group("name2") or ""
        when = (m.group("when") or m.group("when2") or "").strip()
        return Intent("callback", lang, query=name, when=when)
    if _CALL_LIST.search(raw):
        results: list[str] = []
        for word, mapped in _RESULT_WORDS.items():
            if re.search(rf"\b{word}\b", low):
                results = mapped
        return Intent(
            "call_list", lang, period=_period(low), results=results or ["interested", "call_back"]
        )
    if (m := _PAUSE.search(raw)) and m.group("name").lower() not in {"all", "everyone"}:
        return Intent("pause", lang, query=m.group("name"))
    if m := _RESUME.search(raw):
        return Intent("resume", lang, query=m.group("name"))
    if m := _SEARCH.search(raw):
        return Intent("search", lang, query=m.group("q").strip()[:80])
    if _has(low, "visit", "booking", "booked", "appointment", "బుకింగ్", "అపాయింట్", "अपॉइंटमेंट", "बुकिंग"):
        tomorrow = _has(low, "tomorrow", "kal ", "repu", "రేపు", "कल")
        if not _has(low, "how many booked", "booked today"):
            return Intent("bookings", lang, day_offset=1 if tomorrow else 0)
    if _has(
        low,
        "attention",
        "needs me",
        "need me",
        "needs my",
        "urgent",
        "dhyan",
        "ध्यान",
        "గమనించ",
        "important",
    ):
        return Intent("attention", lang)
    if _has(low, "balance", "wallet", "minutes left", "money left", "recharge", "बैलेंस", "బ్యాలెన్స్"):
        return Intent("wallet", lang)
    if _has(
        low,
        "couldn't answer",
        "could not answer",
        "unknown question",
        "didn't know",
        "did not know",
        "missing answer",
    ):
        return Intent("unknown_questions", lang, period=_period(low))
    if _has(low, "team", "employees", "who is working", "staff status"):
        return Intent("team", lang)
    if m := _CUSTOMER.search(raw):
        return Intent("customer", lang, query=m.group("name").strip())
    if _has(low, "help", "what can you do", "madad", "సహాయం", "मदद"):
        return Intent("help", lang)
    if _has(low, *_SUMMARY_WORDS):
        return Intent("summary", lang, period=_period(low))
    # Never answer a different question: say so and suggest what works.
    return Intent("unknown", lang)
