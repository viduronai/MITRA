"""The one place that decides HOW a WhatsApp message goes out (Meta's 24-hour rule).

* Inside 24 hours of the recipient's last message to this business: free-form text (with
  reply buttons when given), in the words the caller wrote.
* Outside it: the approved template named by the caller (``templates.py``), named parameters
  flattened, quick-reply payloads and URL suffix filled in.
* Outside it with no template: NOT sent. The row is stored as ``blocked`` and the owner is told
  (unless the blocked message was itself for the owner, to avoid loops).
* Customers who opted out (CMP-06) get nothing, except the confirmation of that opt-out.

The window is tracked per business and recipient from ``wa_message`` inbound rows. Meta's real
window is per recipient on Mitra's shared number, so this is stricter than Meta, never looser.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import utcnow
from mitra_core.config import get_settings
from mitra_core.logging import get_logger
from mitra_core.models import Business, Contact, OptOut, WaMessage
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.whatsapp.provider import (
    Button,
    Document,
    SendResult,
    TemplateMessage,
    get_provider,
)
from mitra_core.whatsapp.templates import LANGUAGES, Lang, prepare, render, spec

log = get_logger(__name__)

WINDOW = timedelta(hours=24)
OWNER_PURPOSES = frozenset({"alert", "report", "approval", "manager"})
ButtonSpec = tuple[str, str]  # (id / payload, title)


def app_url_base() -> str:
    """Base of the app links in templates ("Open in Mitra"): the ``app_base_url`` setting."""
    return get_settings().app_base_url.rstrip("/") + "/"


def as_lang(value: object) -> Lang:
    text = str(getattr(value, "value", value) or "")
    for lang in LANGUAGES:
        if text == lang:
            return lang
    return "en"


async def last_inbound_at(
    session: AsyncSession, business_id: uuid.UUID, phone_hash: str
) -> datetime | None:
    return await session.scalar(
        select(func.max(WaMessage.created_at)).where(
            WaMessage.business_id == business_id,
            WaMessage.phone_hash == phone_hash,
            WaMessage.direction == "in",
        )
    )


async def window_open(
    session: AsyncSession, business_id: uuid.UUID, phone: str, now: datetime | None = None
) -> bool:
    last = await last_inbound_at(session, business_id, hash_phone(phone))
    return last is not None and last > (now or utcnow()) - WINDOW


async def opted_out(session: AsyncSession, business_id: uuid.UUID, phone: str) -> bool:
    """Opted out of everything (``purpose`` NULL): no calls and no WhatsApp from us."""
    found = await session.scalar(
        select(OptOut.id).where(
            OptOut.business_id == business_id,
            OptOut.phone_hash == hash_phone(phone),
            OptOut.purpose.is_(None),
        )
    )
    return found is not None


async def customer_language(session: AsyncSession, business_id: uuid.UUID, phone: str) -> Lang:
    """The customer's language from memory, else the business's first language, else en."""
    lang = await session.scalar(
        select(Contact.language).where(
            Contact.business_id == business_id, Contact.phone_hash == hash_phone(phone)
        )
    )
    if lang is not None:
        return as_lang(lang)
    langs = await session.scalar(select(Business.languages).where(Business.id == business_id))
    return as_lang((langs or ["en"])[0])


async def business_name(session: AsyncSession, business_id: uuid.UUID) -> str:
    return await session.scalar(select(Business.name).where(Business.id == business_id)) or ""


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


async def _store(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    phone: str,
    kind: str,
    purpose: str,
    body: str,
    status: str,
    provider: str,
    result: SendResult | None = None,
    user_id: uuid.UUID | None = None,
    template: str | None = None,
    params: dict[str, Any] | None = None,
    buttons: list[dict[str, Any]] | None = None,
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
        buttons=buttons or [],
        ref=ref or {},
        provider=provider,
        provider_message_id=result.message_id if result else None,
        status=status,
        dedupe_key=dedupe_key,
    )
    session.add(msg)
    await session.flush()
    return msg


def _status(result: SendResult) -> str:
    return "sent" if result.ok else "failed"


async def deliver(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    to_phone: str,
    purpose: str,
    text: str | None = None,
    template: str | None = None,
    params: dict[str, object] | None = None,
    language: Lang | None = None,
    buttons: list[ButtonSpec] | None = None,
    url_suffix: str | None = None,
    document: Document | None = None,
    user_id: uuid.UUID | None = None,
    ref: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    now: datetime | None = None,
) -> WaMessage | None:
    """Send one message the right way. ``None`` = this ``dedupe_key`` was already used.

    ``buttons`` are (payload, title): free-form reply buttons inside the window, and the
    template's quick-reply payloads (same order) outside it. Check ``msg.status``: ``sent``,
    ``failed`` (provider error) or ``blocked`` (window closed with no template, or opted out).
    """
    if dedupe_key and await _already_sent(session, business_id, to_phone, dedupe_key):
        return None
    provider = get_provider()
    ref = dict(ref or {})
    common: dict[str, Any] = {
        "phone": to_phone,
        "purpose": purpose,
        "user_id": user_id,
        "dedupe_key": dedupe_key,
    }
    if (
        purpose not in OWNER_PURPOSES
        and ref.get("kind") != "opt_out_confirmation"
        and await opted_out(session, business_id, to_phone)
    ):
        return await _store(
            session, business_id, kind="text", body=text or "", status="blocked",
            provider=provider.name, ref=ref | {"blocked": "opted_out"}, **common,
        )  # fmt: skip

    if text and await window_open(session, business_id, to_phone, now):
        if buttons:
            specs = [Button(id=i, title=t) for i, t in buttons]
            result = await provider.send_buttons(to_phone, text, specs)
            stored = [{"id": b.id, "title": b.title} for b in specs]
            return await _store(
                session, business_id, kind="buttons", body=text, status=_status(result),
                provider=provider.name, result=result, buttons=stored, ref=ref, **common,
            )  # fmt: skip
        result = await provider.send_text(to_phone, text)
        return await _store(
            session, business_id, kind="text", body=text, status=_status(result),
            provider=provider.name, result=result, ref=ref, **common,
        )  # fmt: skip

    if template is None:
        log.warning("whatsapp.blocked_window", business_id=str(business_id), purpose=purpose)
        msg = await _store(
            session, business_id, kind="text", body=text or "", status="blocked",
            provider=provider.name, ref=ref | {"blocked": "window_closed"}, **common,
        )  # fmt: skip
        if purpose not in OWNER_PURPOSES:
            await _surface_blocked(session, business_id, msg)
        return msg

    s = spec(template)
    lang = language or (
        await customer_language(session, business_id, to_phone) if purpose == "customer" else "en"
    )
    values = prepare(template, lang, params or {})
    payloads = [i for i, _ in buttons] if buttons and s.quick_replies else []
    message = TemplateMessage(template, lang, values, payloads, url_suffix, document)
    result = await provider.send_template(to_phone, message)
    titles = [b.title for b in s.quick_replies]
    stored_buttons: list[dict[str, Any]] = [
        {"id": p, "title": t} for p, t in zip(payloads, titles, strict=False)
    ]
    link = s.dynamic_url
    if link is not None and url_suffix:
        base = link.url_base or app_url_base()
        stored_buttons.append({"url": f"{base}{url_suffix}", "title": link.title})
    return await _store(
        session, business_id, kind="template", body=render(template, lang, values),
        status=_status(result), provider=provider.name, result=result, template=template,
        params={"language": lang, **values}, buttons=stored_buttons, ref=ref, **common,
    )  # fmt: skip


async def _surface_blocked(session: AsyncSession, business_id: uuid.UUID, msg: WaMessage) -> None:
    """Tell the owner a customer/staff message could not go out (once per recipient per day)."""
    from mitra_core.whatsapp.service import notify_owner  # service imports this module

    kind = str(msg.ref.get("kind") or msg.purpose).replace("_", " ")
    detail = (
        f"A {kind} message to …{msg.phone_last4} was not sent: they have not messaged "
        "in 24 hours and no approved template fits."
    )
    day = (msg.created_at or utcnow()).date().isoformat()
    try:
        async with session.begin_nested():
            await notify_owner(
                session,
                business_id,
                "whatsapp_blocked",
                detail,
                url_suffix="more/whatsapp",
                dedupe_key=f"blocked:{msg.phone_hash[:16]}:{day}",
            )
    except Exception as exc:
        log.warning("whatsapp.surface_failed", error=type(exc).__name__)


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
    purpose: str = "manager",
    ref: dict[str, Any] | None = None,
) -> WaMessage:
    """Store an inbound message; this (re)opens the 24-hour window for that number."""
    msg = WaMessage(
        id=uuid.uuid4(),
        business_id=business_id,
        direction="in",
        kind=kind,
        purpose=purpose,
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
