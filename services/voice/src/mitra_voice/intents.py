"""Cheap text heuristics shared by the mock LLM and the latency predictor (no ML, no I/O)."""

from __future__ import annotations

import re
from typing import Literal

from mitra_voice.pack import Lang

Intent = Literal[
    "emergency",
    "opt_out",
    "booking",
    "price",
    "timings",
    "location",
    "services",
    "thanks",
    "unknown",
]

# Order matters: safety first; "can I book a site visit" is a booking, not a timings question.
_INTENT_PATTERNS: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    (
        "emergency",
        re.compile(
            r"\b(emergency|chest pain|can'?t breathe|not breathing|unconscious|bleeding|"
            r"heart attack|accident|faint(ed)?)\b"
        ),
    ),
    (
        "opt_out",
        re.compile(
            r"\b(don'?t call|do not call|stop calling|never call|remove my number|unsubscribe|"
            r"not interested)\b"
        ),
    ),
    ("booking", re.compile(r"\b(book|booking|appointment|slot|reserve|schedule|site visit)\b")),
    (
        "price",
        re.compile(r"\b(fee|fees|price|prices|cost|charge|charges|rate|how much|kitna|entha)\b"),
    ),
    ("timings", re.compile(r"\b(timing|timings|time|open|opening|hours|close|closing|when)\b")),
    ("location", re.compile(r"\b(where|location|located|address|directions|landmark)\b")),
    ("services", re.compile(r"\b(service|services|project|projects|offer|treat|treatment)\b")),
    ("thanks", re.compile(r"\b(thank|thanks|bye|dhanyavad|dhanyavadalu)\b")),
)

# Turns that need a tool call (availability lookup, booking) take noticeably longer.
_TOOL_INTENTS: frozenset[Intent] = frozenset({"booking"})


def classify(text: str) -> Intent:
    lowered = text.lower()
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(lowered):
            return intent
    return "unknown"


def needs_tool(text: str) -> bool:
    return classify(text) in _TOOL_INTENTS


def detect_lang(text: str, fallback: Lang = "en") -> Lang:
    """Script-based guess: Telugu or Devanagari script, else Latin text is read as English.

    Romanised Telugu/Hindi is read as English, which only affects number words in speech
    normalisation. TODO: use the STT's language tag once real STT is wired.
    """
    if any("ఀ" <= ch <= "౿" for ch in text):
        return "te"
    if any("ऀ" <= ch <= "ॿ" for ch in text):
        return "hi"
    if any(ch.isascii() and ch.isalpha() for ch in text):
        return "en"
    return fallback
