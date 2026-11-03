"""Approvals — "Ask me first" (APPR-01..06, WORKFLOWS §7).

Safety rules enforced here, not by callers:

* A decision names the ``version`` it saw; any owner edit bumps the version, so a stale card
  (an old WhatsApp button, a second browser tab) can never approve a changed payload.
* An approval is used once: the row is locked, must be ``pending``, and ``used_at`` is stamped
  before the kind's handler runs.
* Only an owner/manager membership, re-read from the database, can decide; ``via`` is ``app``
  or ``whatsapp`` (a signed, sender-verified button reply). There is deliberately no path from
  a phone call: the voice service may *request* approvals, never decide them.
* Timeouts apply the default action (APPR-04); every step is written to ``approval_event``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.approvals.edits import check_edit
from mitra_core.approvals.rules import get_rules
from mitra_core.clock import utcnow
from mitra_core.config import get_settings
from mitra_core.errors import AppError, not_found
from mitra_core.logging import get_logger
from mitra_core.models import Approval, ApprovalEvent, Business, Employee, Membership
from mitra_core.models.enums import MemberRole
from mitra_core.whatsapp import notify_owner

log = get_logger(__name__)

Action = Literal["approve", "decline"]
Via = Literal["app", "whatsapp"]
Handler = Callable[[AsyncSession, Approval], Awaitable[None]]

DECIDER_ROLES = frozenset({MemberRole.OWNER, MemberRole.MANAGER})
BUTTON_PREFIX = "appr"
MAX_PAYLOAD_BYTES = 16_000

_handlers: dict[str, Handler] = {}


def register_handler(kind: str, fn: Handler) -> None:
    """Run ``fn(session, approval)`` once after an approval of ``kind`` is decided or expires.

    ``approval.status`` is ``approved`` / ``declined`` / ``expired`` and ``approval.payload``
    is exactly the version that was approved. Runs inside the caller's transaction (in a
    savepoint): raise to mark the approval ``apply_error`` without undoing the decision.
    """
    _handlers[kind] = fn


def button_id(approval: Approval, action: Action) -> str:
    return f"{BUTTON_PREFIX}:{approval.id}:{approval.version}:{action}"


def parse_button_id(value: str) -> tuple[uuid.UUID, int, Action] | None:
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != BUTTON_PREFIX or parts[3] not in {"approve", "decline"}:
        return None
    try:
        action: Action = "approve" if parts[3] == "approve" else "decline"
        return uuid.UUID(parts[1]), int(parts[2]), action
    except ValueError:
        return None


def _log(
    session: AsyncSession,
    approval: Approval,
    event: str,
    *,
    actor: uuid.UUID | None = None,
    via: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        ApprovalEvent(
            business_id=approval.business_id,
            approval_id=approval.id,
            event=event,
            version=approval.version,
            actor_user_id=actor,
            via=via,
            detail=detail or {},
        )
    )


def _check_payload(payload: dict[str, Any]) -> None:
    if len(json.dumps(payload, default=str)) > MAX_PAYLOAD_BYTES:
        raise AppError(422, "payload_too_large", "Approval details are too large")


def card_text(approval: Approval, timezone: str = "Asia/Kolkata") -> str:
    link = f"{get_settings().app_base_url.rstrip('/')}/approvals/{approval.id}"
    lines = ["✅ Ask me first", approval.summary[:300]]
    if approval.expires_at is not None and approval.default_action:
        word = "approve" if approval.default_action == "approve" else "decline"
        local = approval.expires_at.astimezone(ZoneInfo(timezone))
        lines.append(f"If no reply by {local:%I:%M %p} I will {word}.")
    lines.append(f"Edit: {link}")
    return "\n".join(lines)


async def requester_name(session: AsyncSession, approval: Approval) -> str:
    """Who is asking, for the card: the AI employee's name when known, else "Mitra"."""
    kind, _, ident = approval.requested_by.partition(":")
    if kind == "employee" and ident:
        try:
            name = await session.scalar(
                select(Employee.name).where(
                    Employee.business_id == approval.business_id, Employee.id == uuid.UUID(ident)
                )
            )
        except ValueError:
            name = None
        if name:
            return name
    return "Mitra"


async def request_approval(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    kind: str,
    summary: str,
    payload: dict[str, Any],
    requested_by: str,
    expires_at: datetime | None = None,
    default_action: Action | None = None,
    notify: bool = True,
    now: datetime | None = None,
) -> Approval:
    """Create a pending approval and send the WhatsApp card (Approve / Decline buttons).

    ``expires_at`` / ``default_action`` fall back to the business's rule for ``kind``.
    """
    _check_payload(payload)
    now = now or utcnow()
    rule = (await get_rules(session, business_id)).get(kind)
    if expires_at is None and rule is not None and rule.timeout_minutes:
        expires_at = now + timedelta(minutes=rule.timeout_minutes)
    if (
        default_action is None
        and rule is not None
        and rule.default_action in {"approve", "decline"}
    ):
        default_action = "approve" if rule.default_action == "approve" else "decline"
    approval = Approval(
        id=uuid.uuid4(),
        business_id=business_id,
        kind=kind[:32],
        summary=summary.strip()[:500] or kind,
        payload=payload,
        version=1,
        status="pending",
        requested_by=requested_by[:120],
        expires_at=expires_at,
        default_action=default_action,
    )
    session.add(approval)
    await session.flush()
    _log(session, approval, "requested", detail={"requested_by": approval.requested_by})
    if notify:
        tz = await session.scalar(select(Business.timezone).where(Business.id == business_id))
        await notify_owner(
            session,
            business_id,
            "approval",
            card_text(approval, tz or "Asia/Kolkata"),
            buttons=[
                (button_id(approval, "approve"), "Approve"),
                (button_id(approval, "decline"), "Decline"),
            ],
            ref={"approval_id": str(approval.id), "version": approval.version},
            # Outside the owner's 24-hour window: the approved template, same payloads.
            template="approval_request",
            params={"employee": await requester_name(session, approval), "summary": summary},
        )
    await session.flush()
    log.info("approval.requested", business_id=str(business_id), kind=kind, id=str(approval.id))
    return approval


async def _locked(
    session: AsyncSession, business_id: uuid.UUID, approval_id: uuid.UUID
) -> Approval:
    approval = await session.scalar(
        select(Approval)
        .where(Approval.id == approval_id, Approval.business_id == business_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if approval is None:
        raise not_found("Approval")
    return approval


async def _require_decider(
    session: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    role = await session.scalar(
        select(Membership.role).where(
            Membership.business_id == business_id, Membership.user_id == user_id
        )
    )
    if role not in DECIDER_ROLES:
        raise AppError(403, "forbidden", "Only an owner or manager can decide approvals")


async def edit_approval(
    session: AsyncSession,
    business_id: uuid.UUID,
    approval_id: uuid.UUID,
    *,
    payload: dict[str, Any],
    summary: str | None,
    expected_version: int,
    actor_user_id: uuid.UUID,
) -> Approval:
    """Owner edits before approving (APPR-06). Bumps the version: older cards stop working."""
    _check_payload(payload)
    await _require_decider(session, business_id, actor_user_id)
    approval = await _locked(session, business_id, approval_id)
    if approval.status != "pending":
        raise AppError(409, "already_decided", "This request was already handled")
    if approval.version != expected_version:
        raise AppError(409, "stale_version", "This request changed; please review it again")
    before = approval.payload
    check_edit(approval.kind, before or {}, payload)
    approval.payload = payload
    if summary is not None and summary.strip():
        approval.summary = summary.strip()[:500]
    approval.version += 1
    _log(session, approval, "edited", actor=actor_user_id, via="app", detail={"before": before})
    await session.flush()
    return approval


async def _apply(session: AsyncSession, approval: Approval, now: datetime) -> None:
    approval.used_at = now
    handler = _handlers.get(approval.kind)
    if handler is None:
        return
    try:
        async with session.begin_nested():
            await handler(session, approval)
        _log(session, approval, "applied")
    except Exception as exc:
        approval.apply_error = f"{type(exc).__name__}: {exc}"[:300]
        _log(session, approval, "apply_failed", detail={"error": approval.apply_error})
        log.warning("approval.apply_failed", id=str(approval.id), error=type(exc).__name__)


async def decide(
    session: AsyncSession,
    business_id: uuid.UUID,
    approval_id: uuid.UUID,
    *,
    action: Action,
    version: int,
    actor_user_id: uuid.UUID,
    via: Via,
    note: str | None = None,
    now: datetime | None = None,
) -> Approval:
    """Approve or decline one pending approval at exactly ``version``. Single use."""
    if via not in {"app", "whatsapp"}:
        raise AppError(403, "forbidden", "Approvals can only be decided in the app or WhatsApp")
    now = now or utcnow()
    await _require_decider(session, business_id, actor_user_id)
    approval = await _locked(session, business_id, approval_id)
    if approval.status == "pending" and approval.expires_at and approval.expires_at <= now:
        await _expire(session, approval, now)
    if approval.status != "pending":
        _log(session, approval, "rejected_used", actor=actor_user_id, via=via)
        await session.flush()
        raise AppError(
            409, "already_decided", "This request was already handled", {"status": approval.status}
        )
    if approval.version != version:
        _log(
            session,
            approval,
            "rejected_stale",
            actor=actor_user_id,
            via=via,
            detail={"seen_version": version},
        )
        await session.flush()
        raise AppError(409, "stale_version", "This request changed; please review it again")
    approval.status = "approved" if action == "approve" else "declined"
    approval.decided_by = actor_user_id
    approval.decided_via = via
    approval.decided_at = now
    approval.decision_note = (note or "").strip()[:300] or None
    _log(session, approval, approval.status, actor=actor_user_id, via=via)
    await _apply(session, approval, now)
    await session.flush()
    return approval


async def _expire(session: AsyncSession, approval: Approval, now: datetime) -> None:
    if approval.default_action == "approve":
        approval.status = "approved"
    elif approval.default_action == "decline":
        approval.status = "declined"
    else:
        approval.status = "expired"
    approval.decided_via = "timeout"
    approval.decided_at = now
    _log(session, approval, "timed_out", via="timeout", detail={"result": approval.status})
    await _apply(session, approval, now)


async def expire_due(
    session: AsyncSession, business_id: uuid.UUID, now: datetime | None = None
) -> int:
    """APPR-04: apply the default to every pending approval past its deadline."""
    now = now or utcnow()
    due = list(
        await session.scalars(
            select(Approval)
            .where(
                Approval.business_id == business_id,
                Approval.status == "pending",
                Approval.expires_at.is_not(None),
                Approval.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
    )
    for approval in due:
        await _expire(session, approval, now)
    await session.flush()
    return len(due)


async def cancel(
    session: AsyncSession, business_id: uuid.UUID, approval_id: uuid.UUID, *, reason: str
) -> Approval:
    """The requester withdraws (e.g. the customer called back and settled it)."""
    approval = await _locked(session, business_id, approval_id)
    if approval.status == "pending":
        approval.status = "cancelled"
        approval.decided_at = utcnow()
        _log(session, approval, "cancelled", detail={"reason": reason[:200]})
        await session.flush()
    return approval
