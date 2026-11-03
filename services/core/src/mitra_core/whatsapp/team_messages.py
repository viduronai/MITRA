"""AI-team WhatsApp messages (team module): which approved template each one uses.

* Staff briefs, hand-off cards, escalations -> ``staff_handoff`` with a "Done" button whose
  payload names the task or card (``done:task:<id>`` / ``done:card:<id>``).
* Customer follow-ups -> by the task: ``remind_appointment`` -> ``appointment_reminder`` (the
  customer's next open appointment); report / payment tasks -> free text only (their own flows
  send templates); everything else -> ``enquiry_follow_up`` with "Call me" / "Not now".

``text`` is what goes out inside the 24-hour window.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import WaMessage
from mitra_core.whatsapp.outbox import customer_language, deliver
from mitra_core.whatsapp.service import send_customer_message, send_staff_task
from mitra_core.whatsapp.templates import Lang

# Follow-up topic when the caller did not give one (the template says "...about {{topic}}").
FOLLOW_UP_TOPIC: dict[Lang, str] = {
    "en": "your recent call",
    "hi": "आपकी पिछली call",
    "te": "మీ గత call",
}
_STAFF_ACTION_BY_KIND: dict[str, Literal["call_back", "meet", "help"]] = {
    "handoff_card": "call_back",
    "team_escalation": "call_back",
    "team_visit": "meet",
}
# Tasks whose customer message has no template of its own here (their modules send one).
_TEXT_ONLY_TASKS = frozenset({"send_report", "collect_payment"})


async def send_team_message(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    to_phone: str,
    text: str,
    kind: str,
    task: str | None = None,
    ref_id: str | None = None,
    customer: str | None = None,
    name: str | None = None,
    topic: str | None = None,
) -> WaMessage | None:
    """Send one AI-team message the right way; ``ref_id`` = the follow-up task / card id."""
    ref = {"kind": kind, "task": task, "ref_id": ref_id}
    if kind != "team_follow_up":
        target = "card" if kind == "handoff_card" else "task"
        return await send_staff_task(
            session,
            business_id,
            to_phone=to_phone,
            text=text,
            action=_STAFF_ACTION_BY_KIND.get(kind, "help"),
            customer=customer or "a customer",
            brief=text,
            done_payload=f"done:{target}:{ref_id}" if ref_id else None,
            ref=ref,
        )
    if task in _TEXT_ONLY_TASKS:
        return await deliver(
            session, business_id, to_phone=to_phone, purpose="customer", text=text, ref=ref
        )
    if task == "remind_appointment":
        from mitra_core.manager.customer_sends import next_appointment_words  # manager -> us

        when = await next_appointment_words(session, business_id, to_phone)
        if when is None:  # nothing booked to remind about: free text inside the window only
            return await deliver(
                session, business_id, to_phone=to_phone, purpose="customer", text=text, ref=ref
            )
        return await send_customer_message(
            session,
            business_id,
            to_phone=to_phone,
            template="appointment_reminder",
            params={"when": when},
            text=text,
            buttons=[("ill_come", "I'll come"), ("change_time", "Change time")],
            ref=ref,
        )
    lang = await customer_language(session, business_id, to_phone)
    suffix = f":task:{ref_id}" if ref_id else ""
    return await send_customer_message(
        session,
        business_id,
        to_phone=to_phone,
        template="enquiry_follow_up",
        params={"name": name or "", "topic": topic or FOLLOW_UP_TOPIC[lang]},
        text=text,
        language=lang,
        buttons=[(f"call_me{suffix}", "Call me"), (f"not_now{suffix}", "Not now")],
        ref=ref,
    )
