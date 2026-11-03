"""WhatsApp messages from customers (not owners/managers) on Mitra's shared number.

* Every message is stored for the businesses that wrote to that number (it reopens their
  24-hour window). Which businesses: ``wa_customer_businesses`` (SECURITY DEFINER), i.e. the one
  whose message was replied to, else all that messaged the number in the last 30 days.
* "STOP", "Don't call me" and the Hindi / Telugu equivalents (script and romanised), or the
  heads-up's "Don't call me" button, record an opt-out for everything (CMP-06, same
  ``opt_out`` table the call-time compliance check reads) and get a one-line confirmation in
  the customer's language.
* TODO(CHAN-01): any other message should go to the AI employee for an answer.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.db import get_sessionmaker
from mitra_core.logging import get_logger
from mitra_core.manager.buttons import REPLIES, act
from mitra_core.manager.intents import detect_language
from mitra_core.models import OptOut
from mitra_core.pii import hash_phone
from mitra_core.telephony.enums import OptOutSource
from mitra_core.tenancy import TenantContext, set_tenant
from mitra_core.whatsapp.inbound import InboundMessage
from mitra_core.whatsapp.outbox import business_name, customer_language, deliver, record_inbound
from mitra_core.whatsapp.templates import Lang

log = get_logger(__name__)

CustomerOutcome = Literal["unknown_sender", "recorded", "opted_out", "acted"]
OPT_OUT_PAYLOAD = "opt_out"

# Whole-message words (exact match after normalising).
_STOP_WORDS = frozenset({"stop", "stop all", "unsubscribe", "opt out", "optout", "स्टॉप", "స్టాప్"})
# Phrases anywhere in the message.
_STOP_PHRASES = (
    # English
    "don't call me",
    "dont call me",
    "do not call me",
    "don't call",
    "do not call",
    "stop calling",
    "stop messaging",
    "no more calls",
    "no more messages",
    "don't message me",
    # Hindi (script + romanised)
    "कॉल मत करो",
    "call मत करो",
    "कॉल मत करना",
    "call मत करना",
    "कॉल मत कीजिए",
    "फोन मत करो",
    "फ़ोन मत करो",
    "कॉल बंद करो",
    "मैसेज मत भेजो",
    "call mat karo",
    "call mat karna",
    "call mat kijiye",
    "call mat kariye",
    "phone mat karo",
    "mat call karo",
    "call band karo",
    # Telugu (script + romanised)
    "call చేయకండి",
    "కాల్ చేయకండి",
    "call చెయ్యకండి",
    "కాల్ చెయ్యకండి",
    "ఫోన్ చేయకండి",
    "కాల్ వద్దు",
    "call వద్దు",
    "call cheyakandi",
    "call cheyyakandi",
    "call cheyakandi please",
    "call cheyaku",
    "call cheyyaku",
    "phone cheyakandi",
    "call vaddu",
)
_SPACE = re.compile(r"\s+")
_EDGE_PUNCT = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)

CONFIRM: dict[Lang, str] = {
    "en": "Done. {business} will not call or message you again.",
    "hi": "ठीक है। {business} अब आपको call या message नहीं करेगा।",
    "te": "సరే. {business} ఇకపై మీకు call లేదా message చేయదు.",
}


def is_opt_out(message: str) -> bool:
    """True for STOP / don't call me in en / hi / te (script or romanised)."""
    norm = _SPACE.sub(" ", message.replace("’", "'").lower()).strip()  # noqa: RUF001 (curly apostrophe)
    bare = _EDGE_PUNCT.sub("", norm)
    if bare in _STOP_WORDS:
        return True
    return any(phrase in norm for phrase in _STOP_PHRASES)


async def record_opt_out(session: AsyncSession, business_id: object, phone: str) -> bool:
    """Opt out of every purpose (idempotent, like the telephony opt-out endpoint).

    Returns True when a new row was written.
    """
    phone_hash = hash_phone(phone)
    existing = await session.scalar(
        select(OptOut.id).where(
            OptOut.business_id == business_id,
            OptOut.phone_hash == phone_hash,
            OptOut.purpose.is_(None),
        )
    )
    if existing is not None:
        return False
    session.add(
        OptOut(
            business_id=business_id,
            phone_hash=phone_hash,
            purpose=None,
            source=OptOutSource.WHATSAPP,
        )
    )
    await session.flush()
    return True


async def handle_customer_inbound(
    msg: InboundMessage, *, provider: str, now: datetime
) -> CustomerOutcome:
    """Store the message for its businesses; honour an opt-out. Own transactions."""
    phone_hash = hash_phone(msg.from_phone)
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            text("SELECT business_id FROM wa_customer_businesses(:h, :c)"),
            {"h": phone_hash, "c": msg.context_id},
        )
        businesses = [r.business_id for r in rows]
        await session.rollback()
    if not businesses:
        log.info("whatsapp.unknown_customer")
        return "unknown_sender"
    wants_out = msg.button_id == OPT_OUT_PAYLOAD or (
        msg.kind != "button_reply" and is_opt_out(msg.text)
    )
    acted = False
    for business_id in businesses:
        async with get_sessionmaker()() as session:
            await set_tenant(session, TenantContext(business_id=business_id))
            await record_inbound(
                session,
                business_id,
                phone=msg.from_phone,
                user_id=None,
                kind=msg.kind,
                body=msg.text,
                provider=provider,
                provider_message_id=msg.message_id,
                purpose="customer",
                ref={"button": msg.button_id} if msg.button_id else None,
            )
            lang: Lang = (
                detect_language(msg.text)
                if msg.kind != "button_reply" and msg.text.strip()
                else await customer_language(session, business_id, msg.from_phone)
            )
            name = await business_name(session, business_id)
            reply: str | None = None
            if wants_out:
                await record_opt_out(session, business_id, msg.from_phone)
                reply, kind = CONFIRM[lang].format(business=name or "We"), "opt_out_confirmation"
            else:
                done = await act(
                    session,
                    business_id,
                    phone=msg.from_phone,
                    payload=msg.button_id,
                    text=msg.text,
                    context_id=msg.context_id,
                    message_id=msg.message_id,
                    now=now,
                )
                if done is not None:
                    key, values = done
                    reply = REPLIES[key][lang].format(business=name or "We", **values)
                    kind, acted = f"button_{key}", True
            if reply is not None:
                await deliver(
                    session,
                    business_id,
                    to_phone=msg.from_phone,
                    purpose="customer",
                    text=reply,
                    ref={"kind": kind},
                    now=now,
                )
            await session.commit()
    log.info("whatsapp.customer_message", businesses=len(businesses), opted_out=wants_out)
    if wants_out:
        return "opted_out"
    return "acted" if acted else "recorded"
