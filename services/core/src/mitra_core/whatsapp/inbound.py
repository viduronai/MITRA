"""Inbound WhatsApp: Cloud API webhook parsing, signature check and sender resolution.

Supported message types: text, voice note (``audio``), and interactive button replies. A
button reply carries ``context_id`` (the id of our message it answers), which the approval
flow uses to bind a tap to the exact card that was sent to that same phone number.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

InboundKind = Literal["text", "voice", "button_reply"]


@dataclass(frozen=True, slots=True)
class InboundMessage:
    from_phone: str  # E.164 with "+"
    kind: InboundKind
    message_id: str | None = None
    text: str = ""
    button_id: str | None = None
    context_id: str | None = None
    media_id: str | None = None


@dataclass(frozen=True, slots=True)
class Sender:
    user_id: uuid.UUID
    business_id: uuid.UUID
    role: str
    locale: str


def verify_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    """Meta signs webhook bodies with ``X-Hub-Signature-256: sha256=<hex HMAC>``."""
    if not header or not app_secret or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def _e164(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"+{digits}"


def parse_cloud_webhook(payload: dict[str, Any]) -> list[InboundMessage]:
    """Extract messages from a Cloud API webhook body; unknown types and statuses are skipped."""
    out: list[InboundMessage] = []
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            for m in value.get("messages") or []:
                parsed = _parse_one(m)
                if parsed is not None:
                    out.append(parsed)
    return out


def _parse_one(m: dict[str, Any]) -> InboundMessage | None:
    sender = str(m.get("from") or "")
    if not sender:
        return None
    phone = _e164(sender)
    mid = m.get("id")
    context_id = (m.get("context") or {}).get("id")
    kind = m.get("type")
    if kind == "text":
        body = str((m.get("text") or {}).get("body") or "")[:2000]
        return InboundMessage(phone, "text", mid, text=body, context_id=context_id)
    if kind == "audio":
        media = (m.get("audio") or {}).get("id")
        return InboundMessage(phone, "voice", mid, media_id=media, context_id=context_id)
    if kind == "interactive":
        reply = (m.get("interactive") or {}).get("button_reply") or {}
        if reply.get("id"):
            return InboundMessage(
                phone,
                "button_reply",
                mid,
                text=str(reply.get("title") or ""),
                button_id=str(reply["id"])[:200],
                context_id=context_id,
            )
    if kind == "button":  # quick-reply button on a template
        button = m.get("button") or {}
        return InboundMessage(
            phone,
            "button_reply",
            mid,
            text=str(button.get("text") or ""),
            button_id=str(button.get("payload") or "")[:200] or None,
            context_id=context_id,
        )
    return None


async def resolve_sender(session: AsyncSession, phone: str) -> list[Sender]:
    """Owner/manager memberships for a phone number (SECURITY DEFINER, no tenant needed)."""
    rows = await session.execute(
        text("SELECT user_id, business_id, role, locale FROM wa_resolve_sender(:p)"), {"p": phone}
    )
    return [Sender(r.user_id, r.business_id, r.role, r.locale) for r in rows]
