"""WhatsApp messages from owners/managers -> Manager brain or approval decision (APPR-02).

A button tap only counts as an approval when ALL hold: the sender's number belongs to an owner
or manager of the approval's business (SECURITY DEFINER lookup), the tap answers (``context``)
the very card we sent to that same number, and the card's version is still current. Messages
from unknown numbers are dropped. TODO(CHAN-01): route customers' messages to the employee.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.approvals import decide, parse_button_id
from mitra_core.db import get_sessionmaker
from mitra_core.errors import AppError
from mitra_core.logging import get_logger
from mitra_core.manager.brain import converse
from mitra_core.manager.i18n import t
from mitra_core.manager.intents import Lang
from mitra_core.manager.planner import Planner, Transcriber
from mitra_core.models import WaMessage
from mitra_core.models.enums import MemberRole
from mitra_core.pii import hash_phone
from mitra_core.tenancy import TenantContext, set_tenant
from mitra_core.whatsapp.inbound import InboundMessage, Sender, resolve_sender
from mitra_core.whatsapp.service import record_inbound, send_buttons, send_text

log = get_logger(__name__)

Outcome = Literal["unknown_sender", "decided", "rejected", "answered", "ignored"]


def _lang(locale: str) -> Lang:
    return locale if locale in {"en", "hi", "te"} else "en"  # type: ignore[return-value]


async def _card_was_sent_to(
    session: AsyncSession, sender: Sender, phone: str, context_id: str | None, approval_id: str
) -> bool:
    if not context_id:
        return False
    found = await session.scalar(
        select(WaMessage.id).where(
            WaMessage.business_id == sender.business_id,
            WaMessage.direction == "out",
            WaMessage.provider_message_id == context_id,
            WaMessage.phone_hash == hash_phone(phone),
            WaMessage.ref["approval_id"].astext == approval_id,
        )
    )
    return found is not None


async def _button(
    session: AsyncSession, msg: InboundMessage, senders: list[Sender], provider: str, now: datetime
) -> Outcome:
    parsed = parse_button_id(msg.button_id or "")
    if parsed is None:
        return "ignored"
    approval_id, version, action = parsed
    for sender in senders:
        await set_tenant(
            session, TenantContext(user_id=sender.user_id, business_id=sender.business_id)
        )
        if not await _card_was_sent_to(
            session, sender, msg.from_phone, msg.context_id, str(approval_id)
        ):
            continue
        await record_inbound(
            session,
            sender.business_id,
            phone=msg.from_phone,
            user_id=sender.user_id,
            kind="button_reply",
            body=msg.text,
            provider=provider,
            provider_message_id=msg.message_id,
            ref={"approval_id": str(approval_id), "action": action},
        )
        lang = _lang(sender.locale)
        try:
            await decide(
                session,
                sender.business_id,
                approval_id,
                action=action,
                version=version,
                actor_user_id=sender.user_id,
                via="whatsapp",
                now=now,
            )
        except AppError as exc:
            await session.commit()  # keep the rejection in the approval log
            await send_text(
                session,
                sender.business_id,
                to_phone=msg.from_phone,
                text=t("stale", lang),
                purpose="manager",
                user_id=sender.user_id,
            )
            await session.commit()
            log.info("manager.button_rejected", code=exc.code)
            return "rejected"
        reply = t("done" if action == "approve" else "declined", lang)
        await send_text(
            session,
            sender.business_id,
            to_phone=msg.from_phone,
            text=reply,
            purpose="manager",
            user_id=sender.user_id,
        )
        await session.commit()
        return "decided"
    log.warning("manager.button_unverified")
    return "rejected"


async def handle_inbound(
    msg: InboundMessage,
    *,
    provider: str,
    planner: Planner,
    transcriber: Transcriber | None,
    now: datetime,
    audio: bytes | None = None,
    audio_mime: str = "audio/ogg",
    voice_transcript: str | None = None,
) -> Outcome:
    """Process one inbound message in its own transaction(s)."""
    async with get_sessionmaker()() as session:
        senders = await resolve_sender(session, msg.from_phone)
        await session.rollback()
        if not senders:
            log.info("manager.unknown_sender")
            return "unknown_sender"
        if msg.kind == "button_reply":
            return await _button(session, msg, senders, provider, now)

        # TODO(MGR-07): pick the business per conversation when one number manages several.
        sender = senders[0]
        await set_tenant(
            session, TenantContext(user_id=sender.user_id, business_id=sender.business_id)
        )
        text = msg.text
        if msg.kind == "voice":
            text = voice_transcript or ""
            if not text and audio is not None and transcriber is not None:
                text = await transcriber.transcribe(audio, audio_mime) or ""
        await record_inbound(
            session,
            sender.business_id,
            phone=msg.from_phone,
            user_id=sender.user_id,
            kind="voice" if msg.kind == "voice" else "text",
            body=text,
            provider=provider,
            provider_message_id=msg.message_id,
        )
        if not text.strip():
            await send_text(
                session,
                sender.business_id,
                to_phone=msg.from_phone,
                text=t("voice_unavailable", _lang(sender.locale)),
                purpose="manager",
                user_id=sender.user_id,
            )
            await session.commit()
            return "answered"
        reply = await converse(
            session,
            business_id=sender.business_id,
            user_id=sender.user_id,
            role=MemberRole(sender.role),
            channel="whatsapp",
            text=text,
            planner=planner,
            now=now,
        )
        if reply.buttons and reply.card:
            await send_buttons(
                session,
                sender.business_id,
                to_phone=msg.from_phone,
                text=reply.text,
                buttons=reply.buttons,
                purpose="manager",
                user_id=sender.user_id,
                ref={"approval_id": reply.card["approval_id"], "version": reply.card["version"]},
            )
        else:
            await send_text(
                session,
                sender.business_id,
                to_phone=msg.from_phone,
                text=reply.whatsapp_text(),
                purpose="manager",
                user_id=sender.user_id,
            )
        await session.commit()
        return "answered"
