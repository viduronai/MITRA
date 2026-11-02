"""Manager commands (MGR-03) and coaching (MGR-04): always a confirm card first.

A command becomes an approval (kind ``manager_command`` or ``behaviour_update``) that the owner
confirms in the app or with a WhatsApp button; the handler registered here then acts. Outbound
calls go through the dialer queue (``dialer.queue.enqueue_call``), which re-checks compliance
right before dialling.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core import simulation
from mitra_core.approvals import register_handler, request_approval
from mitra_core.calls.queries import business_tz
from mitra_core.logging import get_logger
from mitra_core.manager import tools
from mitra_core.manager.i18n import PERIOD, RESULT, t, word
from mitra_core.manager.intents import Intent
from mitra_core.models import Approval, Call, Contact, Employee
from mitra_core.models.enums import CallResult, EmployeeStatus

log = get_logger(__name__)

MAX_LIST_CALL = 200
MAX_BEHAVIOUR_ITEMS = 20
_TIME = re.compile(r"^(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?\s*(?P<ampm>am|pm|a\.m\.|p\.m\.)?", re.I)


class CommandError(ValueError):
    """The command cannot be drafted; ``message`` is already in the owner's language."""


@dataclass(slots=True)
class Draft:
    approval: Approval
    text: str


def parse_when(said: str, now_local: datetime) -> datetime:
    """'5' / '5:30' / '5 pm' / '17:00' -> the next such moment (local). Bare 1-7 means pm."""
    m = _TIME.match(said.strip().lower())
    if not m:
        return now_local + timedelta(hours=1)
    hour, minute = int(m.group("h")), int(m.group("m") or 0)
    ampm = (m.group("ampm") or "").replace(".", "")
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm and 1 <= hour <= 7:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return now_local + timedelta(hours=1)
    moment = datetime.combine(now_local.date(), time(hour, minute), tzinfo=now_local.tzinfo)
    return moment if moment > now_local else moment + timedelta(days=1)


async def _default_employee(session: AsyncSession, business_id: uuid.UUID) -> Employee | None:
    staff = await tools.employees(session, business_id)
    working = [e for e in staff if e.status == EmployeeStatus.WORKING]
    if working:
        return working[0]
    return staff[0] if staff else None


async def _requester(
    session: AsyncSession,
    business_id: uuid.UUID,
    kind: str,
    summary: str,
    payload: dict[str, Any],
    user_id: uuid.UUID,
) -> Approval:
    # notify=False: the card is shown in the thread the owner is typing in (app or WhatsApp).
    return await request_approval(
        session,
        business_id,
        kind=kind,
        summary=summary,
        payload=payload,
        requested_by=f"manager:{user_id}",
        notify=False,
    )


async def draft(
    session: AsyncSession, business_id: uuid.UUID, intent: Intent, user_id: uuid.UUID, now: datetime
) -> Draft:
    lang = intent.lang
    if intent.name in {"pause", "resume"}:
        emp = await tools.find_employee(session, business_id, intent.query)
        if emp is None:
            raise CommandError(t("no_employee", lang, query=intent.query))
        text = t(
            "confirm_pause" if intent.name == "pause" else "confirm_resume", lang, name=emp.name
        )
        payload: dict[str, Any] = {
            "action": f"{intent.name}_employee",
            "employee_id": str(emp.id),
            "employee_name": emp.name,
        }
        return Draft(
            await _requester(session, business_id, "manager_command", text, payload, user_id), text
        )

    if intent.name == "callback":
        contacts = await tools.find_contacts(session, business_id, intent.query)
        if not contacts:
            raise CommandError(t("customer_none", lang, query=intent.query))
        contact = contacts[0][0]
        tz = await business_tz(session, business_id)
        due = parse_when(intent.when, now.astimezone(tz))
        last_emp = await session.scalar(
            select(Call.employee_id)
            .where(Call.business_id == business_id, Call.contact_id == contact.id)
            .order_by(Call.started_at.desc())
            .limit(1)
        )
        emp = (
            (await session.get(Employee, last_emp))
            if last_emp
            else await _default_employee(session, business_id)
        )
        if emp is None:
            raise CommandError(t("team_none", lang))
        when = f"{due:%I:%M %p, %a %d %b}"
        text = t(
            "confirm_callback",
            lang,
            employee=emp.name,
            name=contact.name or intent.query,
            when=when,
        )
        payload = {
            "action": "callback",
            "contact_id": str(contact.id),
            "contact_name": contact.name,
            "employee_id": str(emp.id),
            "not_before": due.isoformat(),
        }
        return Draft(
            await _requester(session, business_id, "manager_command", text, payload, user_id), text
        )

    if intent.name == "call_list":
        results = [CallResult(r) for r in intent.results if r in CallResult._value2member_map_]
        rows = await tools.calls_with_result(session, business_id, results, intent.period, now)
        contact_ids = list(dict.fromkeys(str(c.contact_id) for c, _ in rows if c.contact_id))[
            :MAX_LIST_CALL
        ]
        labels = ", ".join(word(RESULT, r.value, lang) for r in results)
        period = word(PERIOD, intent.period, lang)
        if not contact_ids:
            raise CommandError(t("call_list_none", lang, period=period, results=labels))
        emp = await _default_employee(session, business_id)
        if emp is None:
            raise CommandError(t("team_none", lang))
        text = t(
            "confirm_call_list",
            lang,
            count=len(contact_ids),
            period=period,
            results=labels,
            employee=emp.name,
        )
        payload = {
            "action": "call_list",
            "contact_ids": contact_ids,
            "employee_id": str(emp.id),
            "results": [r.value for r in results],
            "period": intent.period,
        }
        return Draft(
            await _requester(session, business_id, "manager_command", text, payload, user_id), text
        )

    if intent.name == "coach":
        emp = (
            await tools.find_employee(session, business_id, intent.query) if intent.query else None
        ) or await _default_employee(session, business_id)
        if emp is None:
            raise CommandError(t("team_none", lang))
        note = intent.text[:200]
        text = t("confirm_coach", lang, name=emp.name, note=note)
        payload = {
            "employee_id": str(emp.id),
            "employee_name": emp.name,
            "list": simulation.behaviour_list_for(note),
            "note": note,
        }
        return Draft(
            await _requester(session, business_id, "behaviour_update", text, payload, user_id), text
        )

    raise CommandError(t("help", lang))


# --- handlers (run once, after the owner confirms) ------------------------------------------


async def _employee(session: AsyncSession, approval: Approval) -> Employee:
    emp = await session.scalar(
        select(Employee).where(
            Employee.business_id == approval.business_id,
            Employee.id == uuid.UUID(str(approval.payload["employee_id"])),
        )
    )
    if emp is None:
        raise LookupError("employee no longer exists")
    return emp


async def _phone_for(session: AsyncSession, contact: Contact) -> str | None:
    try:
        from mitra_core.team.ports import contact_phone
    except ImportError:  # pragma: no cover - team module not installed
        return None
    return await contact_phone(session, contact)


async def _enqueue(
    session: AsyncSession,
    approval: Approval,
    contact_id: str,
    employee_id: uuid.UUID,
    not_before: datetime | None,
) -> bool:
    from mitra_core.dialer.queue import EnqueueError, enqueue_call

    contact = await session.scalar(
        select(Contact).where(
            Contact.business_id == approval.business_id, Contact.id == uuid.UUID(contact_id)
        )
    )
    if contact is None:
        return False
    phone = await _phone_for(session, contact)
    if phone is None:
        return False
    try:
        await enqueue_call(
            session,
            approval.business_id,
            employee_id=employee_id,
            phone_e164=phone,
            purpose="service",
            # The voice brief reads lead_name / callback_note (dialer contract).
            variables={
                "lead_name": contact.name or "",
                "callback_note": "Owner asked to call back",
            },
            source="manager",
            not_before=not_before,
            dedupe_key=f"manager:{approval.id}:{contact.id}",
        )
    except EnqueueError as exc:
        log.warning("manager.enqueue_refused", reason=str(exc)[:120])
        return False
    return True


async def handle_command(session: AsyncSession, approval: Approval) -> None:
    if approval.status != "approved":
        return
    action = approval.payload.get("action")
    if action in {"pause_employee", "resume_employee"}:
        emp = await _employee(session, approval)
        emp.status = EmployeeStatus.PAUSED if action == "pause_employee" else EmployeeStatus.WORKING
        return
    if action == "callback":
        emp = await _employee(session, approval)
        due = datetime.fromisoformat(str(approval.payload["not_before"]))
        if not await _enqueue(session, approval, str(approval.payload["contact_id"]), emp.id, due):
            raise LookupError("no dialable number for this customer")
        return
    if action == "call_list":
        emp = await _employee(session, approval)
        ids = [str(i) for i in approval.payload.get("contact_ids") or []][:MAX_LIST_CALL]
        queued = 0
        for contact_id in ids:
            queued += await _enqueue(session, approval, contact_id, emp.id, None)
        approval.payload = {**approval.payload, "queued": queued}
        if queued == 0:
            raise LookupError("no dialable numbers in this list")
        return
    raise ValueError(f"unknown manager action {action!r}")


async def handle_behaviour_update(session: AsyncSession, approval: Approval) -> None:
    """MGR-04: add the owner's coaching line to the employee's behaviour lists."""
    if approval.status != "approved":
        return
    emp = await _employee(session, approval)
    list_name = str(approval.payload.get("list") or "ask_for")
    if list_name not in {"ask_for", "never_say", "transfer_when"}:
        raise ValueError("unknown behaviour list")
    note = str(approval.payload.get("note") or "").strip()[:200]
    if not note:
        raise ValueError("empty coaching note")
    behaviour: dict[str, Any] = {k: list(v) for k, v in emp.behaviour.items()}
    items: list[str] = behaviour.setdefault(list_name, [])
    if note not in items:
        if len(items) >= MAX_BEHAVIOUR_ITEMS:
            raise ValueError("behaviour list is full")
        items.append(note)
    emp.behaviour = behaviour


register_handler("manager_command", handle_command)
register_handler("behaviour_update", handle_behaviour_update)
