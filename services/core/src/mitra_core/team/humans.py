"""Calls with humans: the escalation ladder (CALL-06/19), hand-off cards and live supervision.

* :func:`ladder` - who to ring, in order (staff A -> B -> owner), with ring timeouts, and the
  callback promise the AI makes if nobody answers.
* :func:`create_card` - the message taken when nobody answered, sent to staff on WhatsApp.
* :func:`append_turn` / :func:`take_instructions` - the live transcript stream and the private
  supervisor instructions (CALL-13/18) the voice service picks up during the call.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import (
    AppUser,
    Business,
    Call,
    HandoffCard,
    Membership,
    StaffMember,
    SupervisorAction,
)
from mitra_core.models.enums import CallStatus, MemberRole
from mitra_core.team import ports

CALLBACK_WITHIN = timedelta(hours=2)
DAY_START, DAY_END = time(10, 0), time(19, 0)
MAX_LIVE_TURNS = 400
MAX_TURN_CHARS = 2_000
MAX_LADDER = 5
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    phone_e164: str
    ring_timeout_s: int
    is_owner: bool


def callback_promise(now: datetime, tz: str) -> tuple[datetime, str, str]:
    """When staff will call back: within 2 h in the day, else tomorrow 10 am (local).

    Returns (UTC instant, "HH:MM" local, "today" | "tomorrow").
    """
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    target = local + CALLBACK_WITHIN
    if local.time() < DAY_START:
        target = datetime.combine(local.date(), DAY_START, zone) + CALLBACK_WITHIN
    elif target.time() > DAY_END or target.date() != local.date():
        target = datetime.combine(local.date() + timedelta(days=1), DAY_START, zone)
    day = "today" if target.date() == local.date() else "tomorrow"
    return target.astimezone(now.tzinfo), target.strftime("%H:%M"), day


async def ladder(session: AsyncSession, business_id: uuid.UUID) -> list[Step]:
    """Staff on the ladder by position, then the owner (staff row, else the owner login)."""
    rows = list(
        await session.scalars(
            select(StaffMember)
            .where(StaffMember.business_id == business_id, StaffMember.active.is_(True))
            .where(StaffMember.ladder_position.is_not(None) | StaffMember.is_owner.is_(True))
            .order_by(StaffMember.is_owner, StaffMember.ladder_position.nulls_last())
        )
    )
    steps = [Step(s.name, s.phone_e164, s.ring_timeout_s, s.is_owner) for s in rows]
    if not any(s.is_owner for s in steps):
        owner = await session.scalar(
            select(AppUser)
            .join(Membership, Membership.user_id == AppUser.id)
            .where(Membership.business_id == business_id, Membership.role == MemberRole.OWNER)
            .limit(1)
        )
        if owner is not None and owner.phone_e164 not in {s.phone_e164 for s in steps}:
            steps.append(Step(owner.name or "Owner", owner.phone_e164, 25, True))
    return steps[:MAX_LADDER]


def card_text(card: HandoffCard, when_local: str, day: str) -> str:
    who = f"…{card.caller_last4}" if card.caller_last4 else "A caller"
    return (
        f"Missed transfer: {who} wanted a person ({card.reason}).\n"
        f"Message: {card.message}\n"
        f"We promised a call back by {when_local} {day}."
    )[:1000]


async def create_card(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    employee_id: uuid.UUID,
    call_id: uuid.UUID | None,
    caller_phone: str | None,
    reason: str,
    message: str,
    attempts: list[dict[str, Any]],
    now: datetime,
) -> HandoffCard:
    """Hand-off card + WhatsApp to the ladder, so a real person calls back as promised."""
    business = await session.get(Business, business_id)
    tz = business.timezone if business else "Asia/Kolkata"
    callback_by, when_local, day = callback_promise(now, tz)
    contact_id = None
    if caller_phone:
        from mitra_core.calls.service import upsert_contact

        contact_id = (await upsert_contact(session, business_id, caller_phone)).id
    card = HandoffCard(
        business_id=business_id,
        call_id=call_id,
        contact_id=contact_id,
        employee_id=employee_id,
        caller_last4=caller_phone[-4:] if caller_phone else None,
        reason=_CONTROL.sub(" ", reason)[:300] or "wanted a person",
        message=_CONTROL.sub(" ", message)[:1000] or "(no message)",
        callback_by=callback_by,
        attempts=attempts[:MAX_LADDER],
        status="open",
        created_at=now,
    )
    session.add(card)
    await session.flush()
    text = card_text(card, when_local, day)
    for step in (await ladder(session, business_id))[:3]:
        await ports.send_whatsapp(session, business_id, step.phone_e164, text, kind="handoff_card")
    return card


# --- live calls ----------------------------------------------------------------------------------


def clean_text(value: str, limit: int) -> str:
    return _CONTROL.sub(" ", value).strip()[:limit]


async def append_turn(session: AsyncSession, call: Call, role: str, text: str) -> bool:
    """Append one live turn (the final transcript replaces these when the call ends)."""
    if call.status != CallStatus.LIVE or len(call.transcript) >= MAX_LIVE_TURNS:
        return False
    turn = {"role": "user" if role == "user" else "assistant", "text": clean_text(text, 2000)}
    call.transcript = [*call.transcript, turn]
    return True


async def take_instructions(
    session: AsyncSession, business_id: uuid.UUID, call_id: uuid.UUID, now: datetime
) -> list[dict[str, Any]]:
    """Undelivered whispers / takeovers for this call, marked delivered (at most once)."""
    rows = list(
        await session.scalars(
            select(SupervisorAction)
            .where(SupervisorAction.business_id == business_id)
            .where(SupervisorAction.call_id == call_id)
            .where(SupervisorAction.kind.in_(("whisper", "takeover")))
            .where(SupervisorAction.delivered_at.is_(None))
            .order_by(SupervisorAction.created_at)
            .with_for_update(skip_locked=True)
        )
    )
    out: list[dict[str, Any]] = []
    for action in rows:
        item: dict[str, Any] = {"id": str(action.id), "kind": action.kind, "text": action.text}
        if action.kind == "takeover" and action.user_id is not None:
            user = await session.get(AppUser, action.user_id)
            item["phone_e164"] = user.phone_e164 if user else None
            item["name"] = user.name if user else None
        out.append(item)
    if rows:
        await session.execute(
            update(SupervisorAction)
            .where(SupervisorAction.id.in_([r.id for r in rows]))
            .values(delivered_at=now)
        )
    return out
