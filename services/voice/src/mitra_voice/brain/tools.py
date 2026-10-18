"""In-call tools (TRD §5) as Gemini function declarations, executed locally.

Step 3b simulates them against the employee pack: a fake calendar is built from the pack's
timings facts (working hours per weekday, slot length from the booking policy), with a few slots
deterministically "taken" so availability looks real. Every call is recorded as an action in the
evals contract (``book_slot``, ``transfer_to_human``, ...). Real integrations (calendar, WhatsApp
templates, telephony transfer, suppression list) replace :class:`ToolExecutor`'s bodies later.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from google.genai import types

from mitra_voice.pack import EmployeePack

IST = timezone(timedelta(hours=5, minutes=30), "IST")
Clock = Callable[[], datetime]

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DATE = {"type": "string", "description": "Date as YYYY-MM-DD (resolve 'tomorrow' etc. first)."}
_TIME = {"type": "string", "description": "24-hour time HH:MM, e.g. 18:30."}


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _s(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


# name -> (description, JSON schema). Names match the evals ActionName contract.
TOOL_SPECS: dict[str, tuple[str, dict[str, Any]]] = {
    "check_availability": (
        "Look up free appointment / site-visit slots on a date. Call it before confirming any "
        "time, unless the caller has already accepted a slot you offered.",
        _obj(
            {
                "date": _DATE,
                "time": {**_TIME, "description": "Preferred 24-hour time HH:MM, if any."},
                "part_of_day": {"type": "string", "enum": ["morning", "afternoon", "evening"]},
            },
            ["date"],
        ),
    ),
    "book_slot": (
        "Book an appointment or site visit. Call it as soon as the caller agrees to a date and "
        "time; name and other details are optional and can be added later.",
        _obj(
            {
                "date": _DATE,
                "time": _TIME,
                "name": _s("Caller or patient name, if known."),
                "age": _s("Patient age, if known."),
                "with_whom": _s("Doctor / project / service, if known."),
                "notes": _s("Anything else, e.g. pickup needed."),
            },
            ["date", "time"],
        ),
    ),
    "reschedule": (
        "Move the caller's existing booking to a new date and time.",
        _obj(
            {
                "new_date": _DATE,
                "new_time": _TIME,
                "current_booking": _s("What the caller said about the existing booking."),
            },
            ["new_date", "new_time"],
        ),
    ),
    "cancel": (
        "Cancel the caller's existing booking. Only when they clearly ask to cancel.",
        _obj({"current_booking": _s("What the caller said about the booking.")}),
    ),
    "send_whatsapp_template": (
        "Send the caller a WhatsApp message: booking confirmation, location pin, project "
        "details/brochure, report link, or a follow-up note.",
        _obj(
            {
                "template": {
                    "type": "string",
                    "enum": [
                        "booking_confirmation",
                        "location",
                        "details",
                        "report_link",
                        "follow_up",
                    ],
                },
                "details": _s("Short summary of what to send."),
            },
            ["template"],
        ),
    ),
    "transfer_to_human": (
        "Transfer the call to a staff member (front desk / sales manager). Use when the caller "
        "asks for a person, or for anything you must not handle.",
        _obj({"reason": _s("Why the caller needs a person.")}, ["reason"]),
    ),
    "alert_staff": (
        "Alert the doctor / staff about something that needs a human: a medical question for the "
        "doctor, a report question, an urgent issue.",
        _obj(
            {
                "reason": _s("What staff should know."),
                "urgency": {"type": "string", "enum": ["normal", "urgent", "emergency"]},
            },
            ["reason"],
        ),
    ),
    "schedule_callback": (
        "Promise a follow-up: the team will confirm something you don't know (missing fact) and "
        "call back or WhatsApp, or the doctor will call back.",
        _obj(
            {
                "topic": _s("What needs to be confirmed or discussed."),
                "when": _s("When the caller wants the callback, if said."),
            },
            ["topic"],
        ),
    ),
    "opt_out": (
        "The caller does not want any more calls: suppress their number.",
        _obj({}),
    ),
    "end_call": (
        "End the call after saying goodbye.",
        _obj({"reason": _s("Why the call ends.")}),
    ),
    "record_field": (
        "Save a lead detail the caller shared: budget, preferred_location, bedrooms, "
        "purchase_timeline, name, purpose.",
        _obj({"field": _s("Field name."), "value": _s("Value as the caller said it.")}, ["field"]),
    ),
}


def gemini_tools() -> list[Any]:
    """The tool list for ``GenerateContentConfig(tools=...)``."""
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=name, description=desc, parameters_json_schema=schema
                )
                for name, (desc, schema) in TOOL_SPECS.items()
            ]
        )
    ]


def openai_tools() -> list[dict[str, Any]]:
    """The same tools for OpenAI-compatible chat completions (Groq)."""
    return [
        {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": schema},
        }
        for name, (desc, schema) in TOOL_SPECS.items()
    ]


# --- simulated calendar ---------------------------------------------------------------------------

_RANGE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*(?:to|-|\u2013|until|till)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?",
    re.IGNORECASE,
)
_DAY_SPAN = re.compile(
    r"(" + "|".join(_WEEKDAYS) + r")s?\s*(?:to|-|\u2013)\s*(" + "|".join(_WEEKDAYS) + r")"
)
_DAY = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")s?\b")
_SLOT_MINUTES = re.compile(r"(\d{1,3})[- ]?min(?:ute)?s?\b.{0,10}slot", re.IGNORECASE)


def _to_minutes(hour: str, minute: str | None, ampm: str) -> int:
    h = int(hour) % 12 + (12 if ampm.lower() == "p" else 0)
    return h * 60 + int(minute or 0)


def _days_of(text: str) -> set[int]:
    lowered = text.lower()
    if re.search(r"every ?day|daily|all days|7 days", lowered):
        return set(range(7))
    days: set[int] = set()
    for a, b in _DAY_SPAN.findall(lowered):
        i, j = _WEEKDAYS.index(a), _WEEKDAYS.index(b)
        days.update(range(i, j + 1) if i <= j else [*range(i, 7), *range(0, j + 1)])
    days.update(_WEEKDAYS.index(d) for d in _DAY.findall(lowered))
    return days or set(range(7))


@dataclass(frozen=True, slots=True)
class Calendar:
    hours: dict[int, list[tuple[int, int]]]  # weekday -> [(start_min, end_min)]
    slot_minutes: int

    @classmethod
    def from_pack(cls, pack: EmployeePack) -> Calendar:
        hours: dict[int, list[tuple[int, int]]] = {d: [] for d in range(7)}
        for fact in pack.facts:
            if fact.category != "timings":
                continue
            ranges = [
                (_to_minutes(h1, m1, a1), _to_minutes(h2, m2, a2))
                for h1, m1, a1, h2, m2, a2 in _RANGE.findall(fact.value)
            ]
            for day in _days_of(f"{fact.key} {fact.value}"):
                hours[day].extend(r for r in ranges if r[0] < r[1])
        if not any(hours.values()):  # no parseable timings: a plain office week
            hours = {d: [(600, 1080)] if d < 6 else [] for d in range(7)}
        slot = 15 if pack.industry == "clinic" else 60
        for fact in pack.facts:
            if m := _SLOT_MINUTES.search(fact.value):
                slot = max(5, min(240, int(m.group(1))))
        return cls(hours={d: sorted(r) for d, r in hours.items()}, slot_minutes=slot)

    def slots(self, day: date) -> list[int]:
        out: list[int] = []
        for start, end in self.hours[day.weekday()]:
            out.extend(range(start, end - self.slot_minutes + 1, self.slot_minutes))
        return out


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hours_text(ranges: list[tuple[int, int]]) -> str:
    return ", ".join(f"{_fmt(a)}-{_fmt(b)}" for a, b in ranges) or "closed"


_PARTS = {"morning": (0, 720), "afternoon": (720, 1020), "evening": (1020, 1440)}


def parse_date(value: str, today: date) -> date | None:
    v = value.strip().lower()
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        pass
    if v in {"today", "aaj"}:
        return today
    if v in {"tomorrow", "kal"}:
        return today + timedelta(days=1)
    if v in {"day after tomorrow", "parso", "parson"}:
        return today + timedelta(days=2)
    for i, name in enumerate(_WEEKDAYS):
        if name in v:
            ahead = (i - today.weekday()) % 7 or (7 if "next" in v else 0)
            return today + timedelta(days=ahead)
    return None


def parse_time(value: str | None) -> int | None:
    if not value:
        return None
    v = value.strip().lower().replace(".", "")
    if m := re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])m?", v):
        return _to_minutes(m.group(1), m.group(2), m.group(3))
    if m := re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", v):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if 0 <= h < 24 and 0 <= mi < 60:
            return h * 60 + mi
    return None


# --- executor -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    result: dict[str, Any]


@dataclass
class ToolExecutor:
    """Runs the simulated tools for one call and remembers what happened."""

    pack: EmployeePack
    clock: Clock = field(default=lambda: datetime.now(IST))
    calls: list[ToolCall] = field(default_factory=list)
    bookings: list[dict[str, Any]] = field(default_factory=list)
    end_call: bool = False

    def __post_init__(self) -> None:
        self.calendar = Calendar.from_pack(self.pack)
        self._prefix = "".join(w[0] for w in self.pack.business_name.split()[:2]).upper() or "MT"

    @property
    def escalate_to(self) -> str:
        for rule in self.pack.behaviour.transfer_when:
            if rule.startswith("the caller needs "):
                return rule.removeprefix("the caller needs ")
        return "our staff"

    def _taken(self, day: date, minute: int) -> bool:
        """About 1 in 7 slots is already booked, the same ones every run."""
        digest = hashlib.sha256(f"{self.pack.business_id}|{day}|{minute}".encode()).digest()
        return digest[0] % 7 == 0

    def _free(self, day: date) -> list[int]:
        now = self.clock()
        booked = {(b["date"], b["time"]) for b in self.bookings}
        return [
            m
            for m in self.calendar.slots(day)
            if not self._taken(day, m)
            and (day.isoformat(), _fmt(m)) not in booked
            and (day > now.date() or m > now.hour * 60 + now.minute)
        ]

    def _availability(
        self, date_s: str, time_s: str | None, part: str | None = None
    ) -> dict[str, Any]:
        today = self.clock().date()
        day = parse_date(date_s, today)
        if day is None:
            return {"error": f"could not understand the date {date_s!r}; ask the caller"}
        if day < today:
            return {"error": "that date is in the past"}
        info: dict[str, Any] = {
            "date": day.isoformat(),
            "weekday": _WEEKDAYS[day.weekday()].title(),
            "hours": _hours_text(self.calendar.hours[day.weekday()]),
        }
        free = self._free(day)
        if not free:
            info["available"] = False
            info["note"] = "closed or fully booked that day; offer the next open day"
            return info
        wanted = parse_time(time_s)
        if part in _PARTS:
            lo, hi = _PARTS[part]
            free_part = [m for m in free if lo <= m < hi] or free
        else:
            free_part = free
        if wanted is not None:
            info["requested_time"] = _fmt(wanted)
            info["available"] = wanted in free
            nearest = sorted(free_part, key=lambda m: abs(m - wanted))[:3]
            if not info["available"]:
                info["alternatives"] = [_fmt(m) for m in sorted(nearest)]
        else:
            info["available"] = True
            info["free_slots"] = [_fmt(m) for m in free_part[:4]]
        return info

    def execute(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        args = dict(args or {})
        handler = getattr(self, f"_tool_{name}", None)
        if name not in TOOL_SPECS or handler is None:
            result: dict[str, Any] = {"error": f"unknown tool {name}"}
        else:
            try:
                result = handler(args)
            except Exception as exc:  # a tool bug must never kill the call
                result = {
                    "error": f"{type(exc).__name__}: tool failed, apologise and offer a callback"
                }
        self.calls.append(ToolCall(name=name, args=args, result=result))
        return result

    # Tool bodies (simulated).

    def _tool_check_availability(self, a: dict[str, Any]) -> dict[str, Any]:
        return self._availability(str(a.get("date", "")), a.get("time"), a.get("part_of_day"))

    def _book(self, date_s: str, time_s: str, extra: dict[str, Any]) -> dict[str, Any]:
        info = self._availability(date_s, time_s)
        if "error" in info:
            return info
        if not info.get("available"):
            return {**info, "status": "unavailable"}
        booking = {
            "booking_id": f"{self._prefix}-{1001 + len(self.bookings)}",
            "date": info["date"],
            "weekday": info["weekday"],
            "time": info["requested_time"],
            **{k: v for k, v in extra.items() if v},
        }
        self.bookings.append(booking)
        return {"status": "booked", **booking}

    def _tool_book_slot(self, a: dict[str, Any]) -> dict[str, Any]:
        extra = {k: a.get(k) for k in ("name", "age", "with_whom", "notes")}
        return self._book(str(a.get("date", "")), str(a.get("time", "")), extra)

    def _tool_reschedule(self, a: dict[str, Any]) -> dict[str, Any]:
        result = self._book(
            str(a.get("new_date", "")),
            str(a.get("new_time", "")),
            {"previous": a.get("current_booking")},
        )
        if result.get("status") == "booked":
            result["status"] = "rescheduled"
        return result

    def _tool_cancel(self, a: dict[str, Any]) -> dict[str, Any]:
        return {"status": "cancelled", "policy": "free up to the clinic's cancellation window"}

    def _tool_send_whatsapp_template(self, a: dict[str, Any]) -> dict[str, Any]:
        return {"status": "queued", "template": a.get("template", "follow_up")}

    def _tool_transfer_to_human(self, a: dict[str, Any]) -> dict[str, Any]:
        return {"status": "transferring", "to": self.escalate_to}

    def _tool_alert_staff(self, a: dict[str, Any]) -> dict[str, Any]:
        return {"status": "alerted", "to": self.escalate_to}

    def _tool_schedule_callback(self, a: dict[str, Any]) -> dict[str, Any]:
        return {"status": "scheduled", "by": "the team, today", "channel": "WhatsApp or call"}

    def _tool_opt_out(self, a: dict[str, Any]) -> dict[str, Any]:
        return {"status": "suppressed"}

    def _tool_end_call(self, a: dict[str, Any]) -> dict[str, Any]:
        self.end_call = True
        return {"status": "ending"}

    def _tool_record_field(self, a: dict[str, Any]) -> dict[str, Any]:
        return {"status": "saved"}

    def today_line(self) -> str:
        now = self.clock()
        return (
            f"Now: {_WEEKDAYS[now.weekday()].title()} {now.date().isoformat()}, "
            f"{now.strftime('%H:%M')} IST."
        )

    def log_lines(self) -> list[str]:
        """Compact memory of earlier tool results, for the next turn's prompt."""
        lines = []
        for call in self.calls[-8:]:
            shown = {k: v for k, v in call.result.items() if k not in {"hours"}}
            lines.append(f"- {call.name}({_short(call.args)}) -> {_short(shown)}")
        return lines


def _short(d: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in d.items() if v not in (None, ""))[:200]


__all__ = [
    "IST",
    "TOOL_SPECS",
    "Calendar",
    "Clock",
    "ToolCall",
    "ToolExecutor",
    "gemini_tools",
    "openai_tools",
    "parse_date",
    "parse_time",
]
