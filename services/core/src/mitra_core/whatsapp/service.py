"""Business-scoped WhatsApp sending: every message is stored in ``wa_message`` (tenant table).

All functions take a session already bound to ``business_id`` (RLS) and never commit; the
caller owns the transaction. Raw phone numbers are used only to send: rows keep an HMAC and
the last 4 digits. Owner/manager numbers come from ``app_user`` (they are users, not customers).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.logging import get_logger
from mitra_core.models import AppUser, ManagerSettings, Membership, WaMessage
from mitra_core.models.enums import MemberRole
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.whatsapp.provider import Button, SendResult, get_provider

log = get_logger(__name__)

# Instant alert kinds the owner can switch off in manager settings (MGR-05).
ALERT_KINDS = ("hot_lead", "angry", "vip", "payment_failed", "campaign_paused")
OWNER_ROLES = (MemberRole.OWNER, MemberRole.MANAGER)

ButtonSpec = tuple[str, str]  # (id, title)


async def _store(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    phone: str,
    kind: str,
    purpose: str,
    body: str,
    result: SendResult,
    provider: str,
    user_id: uuid.UUID | None = None,
    template: str | None = None,
    params: dict[str, str] | None = None,
    buttons: list[Button] | None = None,
    ref: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> WaMessage:
    msg = WaMessage(
        id=uuid.uuid4(),
        business_id=business_id,
        direction="out",
        kind=kind,
        purpose=purpose,
        user_id=user_id,
        phone_hash=hash_phone(phone),
        phone_last4=phone_last4(phone),
        body=body,
        template=template,
        params=params or {},
        buttons=[{"id": b.id, "title": b.title} for b in buttons or []],
        ref=ref or {},
        provider=provider,
        provider_message_id=result.message_id,
        status="sent" if result.ok else "failed",
        dedupe_key=dedupe_key,
    )
    session.add(msg)
    await session.flush()
    return msg


async def _already_sent(
    session: AsyncSession, business_id: uuid.UUID, phone: str, dedupe_key: str
) -> bool:
    found = await session.scalar(
        select(WaMessage.id).where(
            WaMessage.business_id == business_id,
            WaMessage.phone_hash == hash_phone(phone),
            WaMessage.dedupe_key == dedupe_key,
        )
    )
    return found is not None


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
    """Free-form text. Returns ``None`` when ``dedupe_key`` was already used for this number."""
    if dedupe_key and await _already_sent(session, business_id, to_phone, dedupe_key):
        return None
    provider = get_provider()
    result = await provider.send_text(to_phone, text)
    return await _store(
        session,
        business_id,
        phone=to_phone,
        kind="text",
        purpose=purpose,
        body=text,
        result=result,
        provider=provider.name,
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
    if dedupe_key and await _already_sent(session, business_id, to_phone, dedupe_key):
        return None
    provider = get_provider()
    specs = [Button(id=i, title=t) for i, t in buttons]
    result = await provider.send_buttons(to_phone, text, specs)
    return await _store(
        session,
        business_id,
        phone=to_phone,
        kind="buttons",
        purpose=purpose,
        body=text,
        result=result,
        provider=provider.name,
        user_id=user_id,
        buttons=specs,
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
) -> WaMessage:
    """An approved template (needed outside the 24-hour window). ``params`` keep their order."""
    provider = get_provider()
    values = list((params or {}).values())
    result = await provider.send_template(to_phone, template, language, values)
    body = f"[{template}] " + " · ".join(values)
    return await _store(
        session,
        business_id,
        phone=to_phone,
        kind="template",
        purpose=purpose,
        body=body,
        result=result,
        provider=provider.name,
        template=template,
        params=params,
        ref=ref,
    )


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
) -> list[WaMessage]:
    """Message the business's owners/managers (alerts, approvals, reports, campaign news).

    Alert kinds in ``ALERT_KINDS`` respect the owner's switches; ``daily_report`` goes to the
    report recipients, everything else to the alert recipients.
    """
    settings = await manager_settings(session, business_id)
    if kind in ALERT_KINDS and kind not in settings.alert_kinds:
        return []
    report = kind == "daily_report"
    purpose = "report" if report else "approval" if kind == "approval" else "alert"
    only = settings.report_user_ids if report else settings.alert_user_ids
    sent: list[WaMessage] = []
    for user in await owner_recipients(session, business_id, only=list(only)):
        key = f"{kind}:{dedupe_key}" if dedupe_key else None
        full_ref = {"kind": kind, **(ref or {})}
        if buttons:
            msg = await send_buttons(
                session,
                business_id,
                to_phone=user.phone_e164,
                text=text,
                buttons=buttons,
                purpose=purpose,
                ref=full_ref,
                user_id=user.id,
                dedupe_key=key,
            )
        else:
            msg = await send_text(
                session,
                business_id,
                to_phone=user.phone_e164,
                text=text,
                purpose=purpose,
                ref=full_ref,
                user_id=user.id,
                dedupe_key=key,
            )
        if msg is not None:
            sent.append(msg)
    log.info("whatsapp.notify_owner", business_id=str(business_id), kind=kind, sent=len(sent))
    return sent


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
    """ACT-06: message one staff member (a member of the business, or a given number)."""
    phone = to_phone
    if user_id is not None:
        user = await session.scalar(
            select(AppUser)
            .join(Membership, Membership.user_id == AppUser.id)
            .where(Membership.business_id == business_id, AppUser.id == user_id)
        )
        if user is None:
            raise ValueError("user is not a member of this business")
        phone = user.phone_e164
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


async def record_inbound(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    phone: str,
    user_id: uuid.UUID | None,
    kind: str,
    body: str,
    provider: str,
    provider_message_id: str | None,
    ref: dict[str, Any] | None = None,
) -> WaMessage:
    msg = WaMessage(
        id=uuid.uuid4(),
        business_id=business_id,
        direction="in",
        kind=kind,
        purpose="manager",
        user_id=user_id,
        phone_hash=hash_phone(phone),
        phone_last4=phone_last4(phone),
        body=body,
        ref=ref or {},
        provider=provider,
        provider_message_id=provider_message_id,
        status="received",
    )
    session.add(msg)
    await session.flush()
    return msg


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
    """NUM-07: "Hi Ravi, Sunrise Homes will call you in 2 min about your enquiry" (template)."""
    from mitra_core.models import Business  # local: keeps this module's imports minimal

    business = await session.scalar(select(Business.name).where(Business.id == business_id))
    minutes = max(1, round(eta_seconds / 60))
    await send_template(
        session,
        business_id,
        to_phone=phone_e164,
        template="call_heads_up",
        params={
            "name": (name or "").strip()[:60] or "there",
            "business": business or "",
            "minutes": str(minutes),
        },
        purpose="customer",
        ref={"source": source[:32], "employee_id": str(employee_id) if employee_id else None},
    )
