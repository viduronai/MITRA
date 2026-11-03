"""Business-scoped WhatsApp sending, built on ``outbox.deliver`` (24-hour window + templates).

All functions take a session already bound to ``business_id`` (RLS) and never commit; the
caller owns the transaction. Raw phone numbers are used only to send: rows keep an HMAC and
the last 4 digits. Owner/manager numbers come from ``app_user`` (they are users, not customers).

Entry points:

* ``send_customer_message`` — anything to a customer: an approved template name + named params,
  and optionally the free text to use instead while the 24-hour window is open.
* ``notify_owner`` — alerts, reports, approval cards to owners/managers (template per kind).
* ``send_staff_task`` — a staff hand-off / brief / call-back card (``staff_handoff``).
* ``send_text`` / ``send_buttons`` — free text only: sent inside the window, otherwise stored
  as ``blocked`` and the owner is told. Prefer the entry points above.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.logging import get_logger
from mitra_core.models import AppUser, ManagerSettings, Membership, WaMessage
from mitra_core.models.enums import MemberRole
from mitra_core.whatsapp.outbox import (
    ButtonSpec,
    as_lang,
    business_name,
    customer_language,
    deliver,
    record_inbound,
)
from mitra_core.whatsapp.provider import Document
from mitra_core.whatsapp.templates import STAFF_ACTIONS, Lang, alert_title, spec

log = get_logger(__name__)

# Instant alert kinds the owner can switch off in manager settings (MGR-05).
ALERT_KINDS = ("hot_lead", "angry", "vip", "payment_failed", "campaign_paused")
OWNER_ROLES = (MemberRole.OWNER, MemberRole.MANAGER)
APP_LINK_DEFAULT = "?from=whatsapp"

__all__ = ["ButtonSpec", "record_inbound"]


def app_suffix(path: str | None) -> str:
    """``/calls/123`` -> ``calls/123`` for the ``https://app.mitra.ai/{{1}}`` buttons."""
    cleaned = (path or "").strip().lstrip("/")
    return cleaned or APP_LINK_DEFAULT


async def send_text(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    to_phone: str,
    text: str,
    purpose: str = "customer",
    ref: dict[str, Any] | None = None,
    user_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> WaMessage | None:
    """Free text. ``None`` = dedupe hit. Outside the window the row is ``blocked``."""
    return await deliver(
        session,
        business_id,
        to_phone=to_phone,
        purpose=purpose,
        text=text,
        user_id=user_id,
        ref=ref,
        dedupe_key=dedupe_key,
    )


async def send_buttons(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    to_phone: str,
    text: str,
    buttons: list[ButtonSpec],
    purpose: str,
    ref: dict[str, Any] | None = None,
    user_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> WaMessage | None:
    return await deliver(
        session,
        business_id,
        to_phone=to_phone,
        purpose=purpose,
        text=text,
        buttons=buttons,
        user_id=user_id,
        ref=ref,
        dedupe_key=dedupe_key,
    )


async def send_customer_message(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    to_phone: str,
    template: str,
    params: Mapping[str, object],
    text: str | None = None,
    language: Lang | None = None,
    buttons: list[ButtonSpec] | None = None,
    url_suffix: str | None = None,
    document: Document | None = None,
    ref: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> WaMessage | None:
    """A message to a customer: ``text`` inside the 24-hour window (if given), else the
    approved ``template`` with named ``params``. ``business`` is filled in when omitted.

    ``buttons`` (payload, title) become the template's quick-reply payloads, in order.
    ``language`` defaults to the customer's remembered language. Check ``msg.status``.
    """
    values = dict(params)
    if "business" not in values:
        values["business"] = await business_name(session, business_id)
    return await deliver(
        session,
        business_id,
        to_phone=to_phone,
        purpose="customer",
        text=text,
        template=template,
        params=values,
        language=language or await customer_language(session, business_id, to_phone),
        buttons=buttons,
        url_suffix=url_suffix,
        document=document,
        ref=ref,
        dedupe_key=dedupe_key,
    )


async def send_template(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    to_phone: str,
    template: str,
    language: str = "en",
    params: dict[str, str] | None = None,
    purpose: str = "customer",
    ref: dict[str, Any] | None = None,
    url_suffix: str | None = None,
) -> WaMessage:
    """Always the template (no free-text alternative). ``business`` is filled in if omitted."""
    values: dict[str, object] = dict(params or {})
    if "business" in spec(template).params and "business" not in values:
        values["business"] = await business_name(session, business_id)
    msg = await deliver(
        session,
        business_id,
        to_phone=to_phone,
        purpose=purpose,
        template=template,
        params=values,
        language=as_lang(language),
        url_suffix=url_suffix,
        ref=ref,
    )
    assert msg is not None  # noqa: S101  (no dedupe key, so never a dedupe hit)
    return msg


async def manager_settings(session: AsyncSession, business_id: uuid.UUID) -> ManagerSettings:
    """The business's manager settings, created with defaults on first use."""
    await session.execute(
        insert(ManagerSettings).values(business_id=business_id).on_conflict_do_nothing()
    )
    settings = await session.get(ManagerSettings, business_id, populate_existing=True)
    assert settings is not None  # noqa: S101  (just inserted or already there)
    return settings


async def owner_recipients(
    session: AsyncSession, business_id: uuid.UUID, *, only: list[uuid.UUID] | None = None
) -> list[AppUser]:
    """Owners and managers of the business (optionally narrowed to ``only``)."""
    stmt = (
        select(AppUser)
        .join(Membership, Membership.user_id == AppUser.id)
        .where(Membership.business_id == business_id, Membership.role.in_(OWNER_ROLES))
        .order_by(Membership.role, Membership.created_at)
    )
    users = list(await session.scalars(stmt))
    if only:
        wanted = set(only)
        narrowed = [u for u in users if u.id in wanted]
        return narrowed or users
    return users


async def notify_owner(
    session: AsyncSession,
    business_id: uuid.UUID,
    kind: str,
    text: str,
    *,
    buttons: list[ButtonSpec] | None = None,
    ref: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    template: str | None = None,
    params: dict[str, object] | None = None,
    url_suffix: str | None = None,
    title: str | None = None,
) -> list[WaMessage]:
    """Message the business's owners/managers; returns the messages actually sent.

    ``text`` goes out as-is inside the 24-hour window. Outside it, ``template`` + ``params`` are
    used; without a template every kind except ``daily_report`` / ``approval`` maps to
    ``owner_alert`` (title from the kind, detail = ``text``, button = ``url_suffix``). Alert
    kinds in ``ALERT_KINDS`` respect the owner's switches; ``daily_report`` goes to the report
    recipients, everything else to the alert recipients. Each recipient gets their language.
    """
    settings = await manager_settings(session, business_id)
    if kind in ALERT_KINDS and kind not in settings.alert_kinds:
        return []
    report = kind == "daily_report"
    purpose = "report" if report else "approval" if kind == "approval" else "alert"
    only = settings.report_user_ids if report else settings.alert_user_ids
    business = await business_name(session, business_id)
    suffix = url_suffix or app_suffix((ref or {}).get("link"))
    sent: list[WaMessage] = []
    for user in await owner_recipients(session, business_id, only=list(only)):
        lang = as_lang(settings.language or user.preferred_locale)
        use_template, values = template, dict(params or {})
        if use_template is None and kind not in {"daily_report", "approval"}:
            use_template = "owner_alert"
            detail = values.get("detail", text)
            values = {"title": title or alert_title(kind, lang), "detail": detail}
        if use_template is not None:
            values.setdefault("business", business)
        msg = await deliver(
            session,
            business_id,
            to_phone=user.phone_e164,
            purpose=purpose,
            text=text,
            template=use_template,
            params=values,
            language=lang,
            buttons=buttons,
            url_suffix=suffix,
            user_id=user.id,
            ref={"kind": kind, **(ref or {})},
            dedupe_key=f"{kind}:{dedupe_key}" if dedupe_key else None,
        )
        if msg is not None and msg.status == "sent":
            sent.append(msg)
    log.info("whatsapp.notify_owner", business_id=str(business_id), kind=kind, sent=len(sent))
    return sent


async def _member_phone(session: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID) -> str:
    user = await session.scalar(
        select(AppUser)
        .join(Membership, Membership.user_id == AppUser.id)
        .where(Membership.business_id == business_id, AppUser.id == user_id)
    )
    if user is None:
        raise ValueError("user is not a member of this business")
    return user.phone_e164


async def send_staff_task(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    text: str,
    action: Literal["call_back", "meet", "help"],
    customer: str,
    brief: str,
    to_phone: str | None = None,
    user_id: uuid.UUID | None = None,
    language: Lang = "en",
    done_payload: str | None = None,
    ref: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> WaMessage | None:
    """TEAM-04 / CALL-19: a task card for one staff member (``staff_handoff`` outside the
    window, ``text`` inside it). ``done_payload`` is the "Done" button's payload."""
    phone = await _member_phone(session, business_id, user_id) if user_id else to_phone
    if not phone:
        raise ValueError("user_id or to_phone is required")
    payload = done_payload or f"task_done:{uuid.uuid4().hex[:12]}"
    return await deliver(
        session,
        business_id,
        to_phone=phone,
        purpose="staff",
        text=text,
        template="staff_handoff",
        params={
            "business": await business_name(session, business_id),
            "action": STAFF_ACTIONS[action][language],
            "customer": customer,
            "brief": brief,
        },
        language=language,
        buttons=[(payload, "Done")],
        user_id=user_id,
        ref=ref,
        dedupe_key=dedupe_key,
    )


async def notify_staff(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    text: str,
    user_id: uuid.UUID | None = None,
    to_phone: str | None = None,
    ref: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> WaMessage | None:
    """ACT-06: free text to one staff member (blocked outside the window; prefer
    ``send_staff_task``, which has a template)."""
    phone = await _member_phone(session, business_id, user_id) if user_id else to_phone
    if not phone:
        raise ValueError("user_id or to_phone is required")
    return await send_text(
        session,
        business_id,
        to_phone=phone,
        text=text,
        purpose="staff",
        ref=ref,
        user_id=user_id,
        dedupe_key=dedupe_key,
    )


async def send_heads_up(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    phone_e164: str,
    name: str | None,
    employee_id: uuid.UUID | None,
    eta_seconds: int,
    source: str,
) -> None:
    """NUM-07: "Hi Ravi, this is Sunrise Homes. We'll call you in about 2 minutes…".

    Always the template (a new lead has not written to us). An unknown name uses the
    per-language fallback from ``templates.NAME_FALLBACK``. Buttons: Call me later / Don't call
    me (the second records an opt-out, see ``manager.customers``).
    """
    minutes = max(1, round(eta_seconds / 60))
    await send_customer_message(
        session,
        business_id,
        to_phone=phone_e164,
        template="call_heads_up",
        params={"name": (name or "").strip(), "minutes": str(minutes)},
        buttons=[("call_later", "Call me later"), ("opt_out", "Don't call me")],
        ref={
            "kind": "heads_up",
            "source": source[:32],
            "employee_id": str(employee_id) if employee_id else None,
        },
    )


async def language_for(session: AsyncSession, business_id: uuid.UUID, phone: str) -> Lang:
    """Customer's language (exported for callers composing their own free text)."""
    return await customer_language(session, business_id, phone)
