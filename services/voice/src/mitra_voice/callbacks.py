"""Outbound-call context and callbacks (CALL-05, CALL-15).

- :func:`resolve_callback_time`: the ``schedule_callback`` tool's ``when_iso`` / ``when`` -> a
  concrete IST time (``tomorrow 5 pm``, ``in 2 hours``, ``kal shaam``); default two hours ahead.
- :func:`call_brief`: a campaign row's script variables (``{lead_name}``, ``{interest}``) as a
  short brief for the employee's prompt, and :func:`fill` substitutes them into a greeting.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from mitra_voice.brain.tools import IST, parse_date, parse_time

DEFAULT_DELAY = timedelta(hours=2)
_IN = re.compile(r"\bin\s+(\d{1,2})\s*(hour|hr|minute|min)", re.IGNORECASE)
_TIME_IN_TEXT = re.compile(r"(\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?)", re.IGNORECASE)
_PARTS = {
    "morning": 10 * 60,
    "subah": 10 * 60,
    "afternoon": 14 * 60,
    "evening": 18 * 60,
    "shaam": 18 * 60,
    "night": 20 * 60,
}
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{0,39})\}")
MAX_BRIEF_CHARS = 600


def resolve_callback_time(args: dict[str, object], now: datetime) -> datetime:
    """Never in the past; a bare time already gone today means tomorrow."""
    now = now.astimezone(IST)
    iso = str(args.get("when_iso") or "").strip()
    if iso:
        try:
            at = datetime.fromisoformat(iso)
            at = at.replace(tzinfo=IST) if at.tzinfo is None else at.astimezone(IST)
            return max(at, now + timedelta(minutes=5))
        except ValueError:
            pass
    text = str(args.get("when") or "").strip().lower()
    if not text:
        return now + DEFAULT_DELAY
    if m := _IN.search(text):
        n = int(m.group(1))
        return now + (timedelta(hours=n) if m.group(2).startswith("h") else timedelta(minutes=n))
    day = None
    for phrase in ("day after tomorrow", "parso", "tomorrow", "kal", "today", "aaj"):
        if phrase in text:
            day = parse_date(phrase, now.date())
            break
    if day is None:
        day = parse_date(text, now.date())
    minute = None
    for token in _TIME_IN_TEXT.findall(text):
        minute = parse_time(token.replace(" ", ""))
        if minute is not None:
            break
    if minute is None:
        minute = next((v for k, v in _PARTS.items() if k in text), None)
    if day is None and minute is None:
        return now + DEFAULT_DELAY
    day = day or now.date()
    at = datetime.combine(day, time(0), tzinfo=IST) + timedelta(minutes=minute or 11 * 60)
    if at <= now:
        at += timedelta(days=1)
    return at


def fmt_when(at: datetime) -> str:
    local = at.astimezone(IST)
    hour = local.hour % 12 or 12
    suffix = "am" if local.hour < 12 else "pm"
    clock = f"{hour}:{local.minute:02d} {suffix}" if local.minute else f"{hour} {suffix}"
    return f"{local.strftime('%a %d %b').replace(' 0', ' ')}, {clock}"


def fill(text: str, variables: dict[str, str]) -> str:
    """``{lead_name}`` -> the row's value; unknown placeholders are dropped, never spoken."""
    out = _PLACEHOLDER.sub(lambda m: variables.get(m.group(1), ""), text)
    return re.sub(r"\s+([,.!?])", lambda m: m.group(1), re.sub(r"\s{2,}", " ", out)).strip()


def call_brief(purpose: str, variables: dict[str, str]) -> str | None:
    if not variables and purpose != "callback":
        return None
    lines = ["This is an OUTBOUND call you are making (you called them)."]
    if purpose == "callback":
        lines.append("They asked to be called back; start by reminding them why you are calling.")
    name = variables.get("lead_name")
    if name:
        lines.append(f"You are calling {name}.")
    note = variables.get("callback_note")
    if note:
        lines.append(f"Callback topic: {note}.")
    extra = [
        f"{k.replace('_', ' ')}: {v}"
        for k, v in variables.items()
        if k not in {"lead_name", "callback_note"} and v
    ]
    if extra:
        lines.append("From the calling list: " + "; ".join(extra) + ".")
    return " ".join(lines)[:MAX_BRIEF_CHARS]
