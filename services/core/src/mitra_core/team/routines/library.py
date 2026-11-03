"""Ready-made routines per industry (AUTO-03). ``role`` picks which employee runs it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mitra_core.models.enums import Industry

EVERY_DAY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass(frozen=True, slots=True)
class LibraryRoutine:
    id: str
    name: str
    industries: tuple[Industry, ...]
    roles: tuple[str, ...]  # preferred team roles / base roles, first match wins
    trigger: dict[str, Any]
    goal: str
    audience: str | None = None
    verb: str = "call"


_ALL = (Industry.CLINIC, Industry.REAL_ESTATE, Industry.EDUCATION, Industry.OTHER)

LIBRARY: tuple[LibraryRoutine, ...] = (
    LibraryRoutine(
        "confirm_tomorrow",
        "Confirm tomorrow's appointments",
        (Industry.CLINIC, Industry.OTHER),
        ("reminder_caller", "receptionist"),
        {"type": "schedule", "days": EVERY_DAY, "time": "18:00"},
        "confirm",
        "tomorrows_appointments",
    ),
    LibraryRoutine(
        "no_show_recovery",
        "No-show recovery",
        (Industry.CLINIC, Industry.EDUCATION),
        ("reminder_caller", "receptionist", "counsellor"),
        {"type": "event", "event": "appointment.no_show", "delay_minutes": 60},
        "rebook",
    ),
    LibraryRoutine(
        "missed_call_rescue",
        "Call back missed callers",
        _ALL,
        ("receptionist", "lead_caller"),
        {"type": "event", "event": "call.missed", "delay_minutes": 2},
        "follow_up",
    ),
    LibraryRoutine(
        "visit_reminder",
        "Remind tomorrow's site visits",
        (Industry.REAL_ESTATE,),
        ("visit_coordinator", "reminder_caller"),
        {"type": "schedule", "days": EVERY_DAY, "time": "18:00"},
        "confirm",
        "tomorrows_appointments",
    ),
    LibraryRoutine(
        "hot_lead_follow_up",
        "Follow up interested leads",
        (Industry.REAL_ESTATE, Industry.EDUCATION),
        ("sales_assistant", "counsellor", "lead_caller"),
        {"type": "schedule", "days": ["mon", "wed", "fri"], "time": "11:00"},
        "follow_up",
        "interested_not_booked",
    ),
    LibraryRoutine(
        "emi_reminder",
        "Payment failed: EMI / fee reminder",
        (Industry.REAL_ESTATE, Industry.EDUCATION),
        ("payment_caller",),
        {"type": "event", "event": "payment.failed", "delay_minutes": 60},
        "collect_payment",
    ),
    LibraryRoutine(
        "payment_reminder",
        "Payment reminder",
        _ALL,
        ("payment_caller", "reminder_caller", "receptionist"),
        # Payments has already sent a WhatsApp reminder with the link; one polite call a day
        # later, inside calling hours and the usual frequency caps (dialer compliance).
        {"type": "event", "event": "payment.overdue", "delay_minutes": 24 * 60},
        "collect_payment",
    ),
    LibraryRoutine(
        "booking_thanks",
        "Thank-you message after a booking",
        _ALL,
        ("receptionist", "visit_coordinator", "counsellor"),
        {"type": "event", "event": "booking.made", "delay_minutes": 5},
        "confirm",
        verb="whatsapp",
    ),
    LibraryRoutine(
        "win_back",
        "Win back quiet customers",
        (Industry.CLINIC, Industry.EDUCATION),
        ("follow_up_caller", "feedback_caller", "reminder_caller"),
        {"type": "schedule", "days": ["mon"], "time": "11:00"},
        "recover",
        "inactive_customers",
    ),
)

LIBRARY_BY_ID = {r.id: r for r in LIBRARY}


def library_for(industry: Industry) -> list[LibraryRoutine]:
    return [r for r in LIBRARY if industry in r.industries]
