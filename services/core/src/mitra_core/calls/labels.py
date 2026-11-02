"""Owner-readable labels for in-call actions and booking times (English; the web app localises
the surrounding UI, these are short data strings like "Booked Tue 21 Oct, 6:15 pm")."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

_TEMPLATES = {
    "booking_confirmation": "booking confirmation",
    "location": "location",
    "price_list": "price list",
    "brochure": "brochure",
    "follow_up": "follow-up",
}


def parse_booking(args: dict[str, Any], result: dict[str, Any]) -> tuple[date, time] | None:
    """The booked date/time from a ``book_slot`` / ``reschedule`` result, if well-formed."""
    raw_date = str(result.get("date") or args.get("date") or args.get("new_date") or "")
    raw_time = str(
        result.get("time")
        or result.get("requested_time")
        or args.get("time")
        or args.get("new_time")
        or ""
    )
    try:
        day = date.fromisoformat(raw_date[:10])
    except ValueError:
        return None
    for fmt in ("%H:%M", "%I:%M %p", "%I %p", "%I:%M%p"):
        try:
            return day, datetime.strptime(raw_time.strip().upper(), fmt).time()  # noqa: DTZ007
        except ValueError:
            continue
    return None


def fmt_time(t: time) -> str:
    hour = t.hour % 12 or 12
    suffix = "am" if t.hour < 12 else "pm"
    return f"{hour}:{t.minute:02d} {suffix}" if t.minute else f"{hour} {suffix}"


def fmt_day(d: date) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def fmt_booking(d: date, t: time) -> str:
    return f"{fmt_day(d)}, {fmt_time(t)}"


def is_ok(result: dict[str, Any]) -> bool:
    return "error" not in result and result.get("status") not in {"unavailable", "failed"}


def action_label(name: str, args: dict[str, Any], result: dict[str, Any]) -> str:
    booking = parse_booking(args, result)
    if name in {"book_slot", "reschedule"}:
        if not is_ok(result):
            return "Tried to book (slot not available)"
        verb = "Rescheduled to" if name == "reschedule" else "Booked"
        return f"{verb} {fmt_booking(*booking)}" if booking else verb
    if name == "send_whatsapp_template":
        template = _TEMPLATES.get(str(args.get("template", "")), "message")
        return f"WhatsApp sent: {template}"
    if name == "transfer_to_human":
        return "Transferred to a person"
    if name == "alert_staff":
        return f"Alerted staff: {str(args.get('reason', ''))[:80]}".rstrip(": ")
    if name == "schedule_callback":
        return f"Callback scheduled: {str(args.get('topic', ''))[:80]}".rstrip(": ")
    if name == "opt_out":
        return "Number opted out of calls"
    if name == "cancel":
        return "Appointment cancelled"
    if name == "record_field":
        return f"Noted {args.get('field', 'a detail')}: {args.get('value', '')}".strip(": ")
    if name == "check_availability":
        return "Checked availability"
    if name == "end_call":
        return "Ended the call"
    return name.replace("_", " ").capitalize()


# Actions worth showing to the owner under "Actions taken" (lookups are noise).
VISIBLE_ACTIONS = frozenset(
    {
        "book_slot",
        "reschedule",
        "cancel",
        "send_whatsapp_template",
        "transfer_to_human",
        "alert_staff",
        "schedule_callback",
        "opt_out",
        "record_field",
    }
)
