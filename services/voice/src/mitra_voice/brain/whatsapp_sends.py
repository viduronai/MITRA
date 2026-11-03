"""The ``send_whatsapp_template`` tool body (ACT-02 / ACT-07): only what the business has.

The AI picks WHICH message; it never supplies a link:

* ``booking_confirmation`` needs a booking made on THIS call (``book_slot`` / ``reschedule``);
  the time comes from that tool's result, not from the model.
* ``location`` needs a confirmed location fact with a Google Maps short link.
* ``document`` (``details`` is the old name) needs a confirmed fact holding a ``https://….pdf``
  link whose name matches what the caller asked for (the price list, the brochure).
* ``follow_up`` takes a short topic.
* ``report_link``: lab reports are per patient, not business knowledge, so nothing is sent
  automatically; the team shares the report (the reply says so).

Accepted messages are handed to core after the call (``transports.whatsapp_sends``); core
re-checks the business's knowledge and picks the link itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from typing import Any

from mitra_voice.pack import Fact

MAX_SENDS = 3
PDF_LINK = re.compile(r"https://[^\s<>\"']+?\.pdf\b", re.IGNORECASE)
MAPS_LINK = re.compile(r"https://maps\.app\.goo\.gl/[A-Za-z0-9_-]{4,64}")
KINDS = ("booking_confirmation", "location", "document", "follow_up")

SPEC: tuple[str, dict[str, Any]] = (
    "Send the caller a WhatsApp message after this call. Choose WHICH message only; never say "
    "or invent a link. booking_confirmation: only after book_slot/reschedule succeeded on this "
    "call. location: the business's own map link. document: a document the business has (use "
    "its name from the facts, e.g. 'price list'). follow_up: a short topic.",
    {
        "type": "object",
        "properties": {
            "template": {
                "type": "string",
                "enum": [
                    "booking_confirmation",
                    "location",
                    "document",
                    "details",
                    "report_link",
                    "follow_up",
                ],
            },
            "document": {"type": "string", "description": "Name of the document to send."},
            "topic": {"type": "string", "description": "Follow-up topic, e.g. '2BHK in Kondapur'."},
            "details": {"type": "string", "description": "Short summary of what to send."},
        },
        "required": ["template"],
    },
)


def documents(facts: Iterable[Fact]) -> list[str]:
    """Names of the documents the business can send (facts holding a PDF link)."""
    return [f.key for f in facts if PDF_LINK.search(f.value)]


def has_map(facts: Iterable[Fact]) -> bool:
    return any(f.category == "location" and MAPS_LINK.search(f.value) for f in facts)


def _match(names: list[str], wanted: str) -> str | None:
    w = " ".join(wanted.lower().split())
    if not w:
        return None
    for name in names:
        n = " ".join(name.lower().split())
        if w in n or n in w:
            return name
    return None


def booking_words(booking: dict[str, Any]) -> str | None:
    """{"date": "2026-10-21", "time": "18:15"} -> "Wed 21 Oct, 6:15 pm"."""
    try:
        day = date.fromisoformat(str(booking.get("date")))
        hour, minute = (int(x) for x in str(booking.get("time")).split(":")[:2])
    except (TypeError, ValueError):
        return None
    clock = f"{hour % 12 or 12}:{minute:02d} {'am' if hour < 12 else 'pm'}"
    return f"{day:%a} {day.day} {day:%b}, {clock}"


def send_whatsapp(
    a: dict[str, Any],
    *,
    facts: list[Fact],
    booking: dict[str, Any] | None,
    already_sent: int,
) -> dict[str, Any]:
    template = str(a.get("template") or "")
    if template == "details":
        template = "document"
    if template == "report_link":
        return {
            "status": "not_sent",
            "error": "report links are shared by the team, not sent automatically. Say the "
            "team will WhatsApp the report shortly.",
        }
    if template not in KINDS:
        return {"error": f"template must be one of {', '.join(KINDS)}"}
    if already_sent >= MAX_SENDS:
        return {"status": "not_sent", "error": "enough WhatsApp messages on this call"}
    out: dict[str, Any] = {"ok": True, "status": "will_send", "kind": template}
    if template == "booking_confirmation":
        when = booking_words(booking) if booking else None
        if when is None:
            return {"status": "not_sent", "error": "book the slot first (book_slot)"}
        out["when"] = when
    elif template == "location":
        if not has_map(facts):
            return {
                "status": "not_sent",
                "error": "no map link on file; say the address from the facts instead",
            }
    elif template == "document":
        names = documents(facts)
        name = _match(names, str(a.get("document") or a.get("details") or ""))
        if name is None:
            return {
                "status": "not_sent",
                "error": "that document is not on file; never promise it",
                "available": names[:10],
            }
        out["document"] = name
    else:
        out["topic"] = " ".join(str(a.get("topic") or a.get("details") or "").split())[:100]
    out["channel"] = "WhatsApp, right after this call"
    return out
