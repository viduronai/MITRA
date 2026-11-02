"""The typed routine spec behind the sentence builder (AUTO-01/02, TRD section 9).

"Every [weekday] at [6 pm], [call] [tomorrow's appointments] to [confirm]" compiles to::

    {"trigger": {"type": "schedule", "days": ["mon", ...], "time": "18:00"},
     "audience": "tomorrows_appointments",
     "action": {"verb": "call", "employee_id": "...", "goal": "confirm"},
     "approval_over": 25}

Owners never see the JSON; the web app renders the sentence in their language.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import Field, StringConstraints, field_validator, model_validator

from mitra_core.schemas.common import RequestModel

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
EventName = Literal[
    "lead.created", "call.missed", "appointment.no_show", "booking.made", "payment.failed"
]
EVENTS: tuple[str, ...] = EventName.__args__  # type: ignore[attr-defined]
Audience = Literal[
    "tomorrows_appointments",
    "todays_appointments",
    "no_shows_yesterday",
    "interested_not_booked",
    "callbacks_due",
    "missed_callers_today",
    "inactive_customers",
]
AUDIENCES: tuple[str, ...] = Audience.__args__  # type: ignore[attr-defined]
Goal = Literal["confirm", "remind", "follow_up", "collect_payment", "feedback", "recover", "rebook"]
GOAL_TASK: dict[str, str] = {
    "confirm": "remind_appointment",
    "remind": "remind_appointment",
    "follow_up": "follow_up",
    "collect_payment": "collect_payment",
    "feedback": "feedback",
    "recover": "call_back",
    "rebook": "book_visit",
}
HHMM = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
DEFAULT_APPROVAL_OVER = 25


class ScheduleTrigger(RequestModel):
    type: Literal["schedule"] = "schedule"
    days: list[Weekday] = Field(min_length=1, max_length=7)
    time: HHMM

    @field_validator("days")
    @classmethod
    def _unique_sorted(cls, days: list[Weekday]) -> list[Weekday]:
        return [d for d in WEEKDAYS if d in set(days)]


class EventTrigger(RequestModel):
    type: Literal["event"] = "event"
    event: EventName
    delay_minutes: int = Field(default=0, ge=0, le=7 * 24 * 60)


class RoutineAction(RequestModel):
    verb: Literal["call", "whatsapp"] = "call"
    employee_id: uuid.UUID
    goal: Goal


class RoutineSpec(RequestModel):
    trigger: Annotated[ScheduleTrigger | EventTrigger, Field(discriminator="type")]
    # Event routines contact the person the event is about; the audience is ignored.
    audience: Audience | None = None
    action: RoutineAction
    approval_over: int = Field(default=DEFAULT_APPROVAL_OVER, ge=0, le=10_000)

    @model_validator(mode="after")
    def _audience_for_schedules(self) -> Self:
        if isinstance(self.trigger, ScheduleTrigger) and self.audience is None:
            raise ValueError("a scheduled routine needs an audience")
        # New leads are called by the lead source's own instant call (CALL-03, Connect screen);
        # a routine may only add a WhatsApp, so a lead is never called twice.
        if (
            isinstance(self.trigger, EventTrigger)
            and self.trigger.event == "lead.created"
            and self.action.verb == "call"
        ):
            raise ValueError("new leads are already called by their lead source; use WhatsApp")
        return self


def next_run(spec: RoutineSpec, after: datetime, tz: str) -> datetime | None:
    """The next scheduled time strictly after ``after`` (UTC-aware), or None for events."""
    trigger = spec.trigger
    if not isinstance(trigger, ScheduleTrigger):
        return None
    zone = ZoneInfo(tz)
    local = after.astimezone(zone)
    hour, minute = (int(x) for x in trigger.time.split(":"))
    for offset in range(8):
        day: date = local.date() + timedelta(days=offset)
        if WEEKDAYS[day.weekday()] not in trigger.days:
            continue
        at = datetime.combine(day, time(hour, minute), zone)
        if at > local:
            return at.astimezone(after.tzinfo)
    return None  # pragma: no cover - 8 days always contain a chosen weekday


_AUDIENCE_WORDS = {
    "tomorrows_appointments": "tomorrow's appointments",
    "todays_appointments": "today's appointments",
    "no_shows_yesterday": "yesterday's no-shows",
    "interested_not_booked": "interested people who haven't booked",
    "callbacks_due": "people we promised to call back",
    "missed_callers_today": "today's missed callers",
    "inactive_customers": "customers not heard from in 30 days",
}
_EVENT_WORDS = {
    "lead.created": "a new lead arrives",
    "call.missed": "a call is missed",
    "appointment.no_show": "someone misses their appointment",
    "booking.made": "a booking is made",
    "payment.failed": "a payment fails",
}
_GOAL_WORDS = {
    "confirm": "confirm",
    "remind": "remind them",
    "follow_up": "follow up",
    "collect_payment": "collect the payment",
    "feedback": "ask for feedback",
    "recover": "win them back",
    "rebook": "book a new time",
}


def sentence(spec: RoutineSpec, employee_name: str) -> str:
    """English rendering for logs, WhatsApp drafts and the API (the web localises its own)."""
    verb = "calls" if spec.action.verb == "call" else "WhatsApps"
    goal = _GOAL_WORDS[spec.action.goal]
    trigger = spec.trigger
    if isinstance(trigger, ScheduleTrigger):
        days = "day" if len(trigger.days) == 7 else ", ".join(d.title() for d in trigger.days)
        who = _AUDIENCE_WORDS[spec.audience or "tomorrows_appointments"]
        return f"Every {days} at {trigger.time}, {employee_name} {verb} {who} to {goal}."
    delay = f" after {trigger.delay_minutes} min" if trigger.delay_minutes else ""
    return f"When {_EVENT_WORDS[trigger.event]}, {employee_name} {verb} them{delay} to {goal}."
