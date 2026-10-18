"""Simulated test calls (until the voice pipeline exists): status timeline, a scripted
transcript built from the business's confirmed facts, and the rule for owner corrections."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from mitra_core.models.enums import FactCategory, Industry, TestCallStatus

SECONDS_PER_STATE = 2.0
_ORDER = (
    TestCallStatus.QUEUED,
    TestCallStatus.RINGING,
    TestCallStatus.CONNECTED,
    TestCallStatus.COMPLETED,
)
COMPLETED_AFTER_SECONDS = SECONDS_PER_STATE * (len(_ORDER) - 1)

KnownFact = tuple[FactCategory, str, str]


def status_at(created_at: datetime, now: datetime) -> TestCallStatus:
    elapsed = max(0.0, (now - created_at).total_seconds())
    return _ORDER[min(len(_ORDER) - 1, int(elapsed // SECONDS_PER_STATE))]


def visible_transcript(lines: list[dict[str, Any]], status: TestCallStatus) -> list[dict[str, Any]]:
    """Nothing before pick-up, the first half while connected, everything once completed."""
    if status in (TestCallStatus.QUEUED, TestCallStatus.RINGING):
        return []
    if status == TestCallStatus.CONNECTED:
        return lines[: math.ceil(len(lines) / 2)]
    return lines


# --- transcript ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Question:
    topic: str
    ask: str
    category: FactCategory
    answer: str  # format string with {key}, {key_lc} (lowercased) and {value}
    unknown: str
    keywords: tuple[str, ...] = ()

    def find(self, facts: list[KnownFact]) -> KnownFact | None:
        candidates = [f for f in facts if f[0] == self.category]
        for fact in candidates:
            text = f"{fact[1]} {fact[2]}".lower()
            if any(k in text for k in self.keywords):
                return fact
        return candidates[0] if candidates and not self.keywords else None


_TIMINGS = _Question(
    "timings",
    "And what are your timings?",
    FactCategory.TIMINGS,
    "Our timings are {value}.",
    "Let me double-check today's timings with the team and message you on WhatsApp.",
)
_LOCATION = _Question(
    "location",
    "Where exactly are you located?",
    FactCategory.LOCATION,
    "We're at {value}.",
    "I'll send you the exact location on WhatsApp right after this call.",
    keywords=("address", "location", "road", "street", "nagar", "colony", "near", "landmark"),
)

_SCRIPTS: dict[Industry | None, tuple[tuple[_Question, ...], str, str]] = {
    Industry.CLINIC: (
        (
            _Question(
                "consultation fee",
                "Hi, what is the consultation fee?",
                FactCategory.PRICES,
                "The {key_lc} is {value}.",
                "That's a good question. Let me confirm the exact fee with the doctor's team "
                "and call you back shortly.",
                keywords=("consult", "fee"),
            ),
            _TIMINGS,
            _LOCATION,
        ),
        "Would you like me to book an appointment for you?",
        "Yes, tomorrow morning if possible.",
    ),
    Industry.REAL_ESTATE: (
        (
            _Question(
                "price range",
                "Hi, I saw your ad. What is the price range?",
                FactCategory.PRICES,
                "{key}: {value}.",
                "Prices depend on the unit, so let me get you the latest price sheet on WhatsApp.",
            ),
            _Question(
                "projects",
                "Which projects do you have right now?",
                FactCategory.SERVICES,
                "Right now we have {value}.",
                "Let me share our current project list with you on WhatsApp.",
                keywords=("project", "villa", "apartment", "flat", "plot", "bhk"),
            ),
            _Question(
                "site-visit timings",
                "Can I come for a site visit this weekend?",
                FactCategory.TIMINGS,
                "Of course! {key}: {value}.",
                "I'll check the site-visit slots and confirm a time with you on WhatsApp.",
                keywords=("visit",),
            ),
        ),
        "Shall I book a site visit for you?",
        "Yes, Saturday afternoon works.",
    ),
    None: (
        (
            _Question(
                "services",
                "Hi, what services do you offer?",
                FactCategory.SERVICES,
                "We offer {value}.",
                "Let me have the team share the full list of services with you.",
            ),
            _Question(
                "prices",
                "How much does it cost?",
                FactCategory.PRICES,
                "{key}: {value}.",
                "I'll confirm the exact price with the team and get back to you.",
            ),
            _TIMINGS,
        ),
        "Is there anything else I can help you with?",
        "No, that's all. Thanks!",
    ),
}


@dataclass(frozen=True, slots=True)
class Script:
    transcript: list[dict[str, Any]]
    summary: str


def build_transcript(
    *,
    business_name: str,
    industry: Industry,
    employee_name: str,
    greeting: str | None,
    ask_for: list[str],
    facts: list[KnownFact],
) -> Script:
    questions, offer, accept = _SCRIPTS.get(industry, _SCRIPTS[None])
    turns: list[tuple[Literal["employee", "caller"], str]] = [
        (
            "employee",
            greeting
            or f"Namaste! Thank you for calling {business_name}. This is {employee_name}, "
            "how can I help you today?",
        )
    ]
    missing: list[str] = []
    for question in questions:
        turns.append(("caller", question.ask))
        fact = question.find(facts)
        if fact is None:
            missing.append(question.topic)
            turns.append(("employee", question.unknown))
        else:
            _, key, value = fact
            answer = question.answer.format(key=key, key_lc=key.lower(), value=value.rstrip("."))
            turns.append(("employee", answer[:1].upper() + answer[1:]))
    turns.append(("employee", offer))
    turns.append(("caller", accept))
    if ask_for:
        turns.append(
            ("employee", f"Sure. Before I go ahead, could you share {_join(ask_for[:2])}?")
        )
        turns.append(("caller", "Yes, of course. I'll share that."))
    turns.append(
        (
            "employee",
            f"Wonderful, I've noted that and the team will confirm on WhatsApp. "
            f"Thank you for calling {business_name}!",
        )
    )

    transcript: list[dict[str, Any]] = []
    at_ms = 0
    for speaker, text in turns:
        transcript.append({"speaker": speaker, "text": text, "at_ms": at_ms})
        at_ms += 900 + 55 * len(text)
    answered = len(questions) - len(missing)
    summary = (
        f"Simulated call: the caller asked about {_join([q.topic for q in questions])}. "
        f"{employee_name} answered {answered} of {len(questions)} from confirmed facts"
    )
    summary += f"; still to teach: {_join(missing)}." if missing else "."
    return Script(transcript=transcript, summary=summary)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# --- corrections --------------------------------------------------------------------------------

_KNOWLEDGE_RE = re.compile(
    r"₹|\b(rs|inr|rupees?|price[sd]?|pricing|fees?|cost|charges?|time|timings?|hours?|"
    r"open(s|ing)?|clos(e|es|ed|ing))\b",
    re.IGNORECASE,
)
_LEAD_IN_RE = re.compile(
    r"^(please\s+)?(say|tell\s+(them|callers|customers|patients|people)|mention|update|"
    r"remember)(\s+that)?\s+",
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"\s+(?:is|are|=)\s+|\s*:\s*", re.IGNORECASE)
_NEGATIVE_RE = re.compile(r"^(please\s+)?(don'?t|do\s+not|never|avoid|stop)\b", re.IGNORECASE)


def applies_to_knowledge(text: str) -> bool:
    return bool(_KNOWLEDGE_RE.search(text))


def parse_fact(text: str) -> tuple[str, str]:
    """``"Say the consultation fee is ₹500"`` -> ``("Consultation fee", "₹500")``."""
    body = _LEAD_IN_RE.sub("", text.strip()).strip()
    body = re.sub(r"^(the|our)\s+", "", body, flags=re.IGNORECASE)
    parts = _SPLIT_RE.split(body, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        key, value = parts[0].strip(" .,"), parts[1].strip(" .")
    else:
        key, value = "Note", body.strip(" .")
    key = key[:120]
    return key[:1].upper() + key[1:], value[:500]


def behaviour_list_for(text: str) -> Literal["never_say", "ask_for"]:
    return "never_say" if _NEGATIVE_RE.search(text.strip()) else "ask_for"
