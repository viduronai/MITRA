"""WhatsApp the caller what the AI employee promised on the call (ACT-02, ACT-07, AUTO-03).

The voice service only says WHICH message (booking confirmation, location, a document, a
follow-up) and, for a booking, the time its own ``book_slot`` returned. Every link comes from
the business's CONFIRMED knowledge facts, never from the AI:

* a document = a confirmed fact whose value contains an ``https://….pdf`` link (key = its name,
  e.g. "Price list"), matched by name;
* the location = confirmed ``location`` facts: the address text and a Google Maps short link
  (``https://maps.app.goo.gl/<id>``) for the template's map button.

All sends go through ``send_customer_message`` (24-hour window, templates, opt-outs).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.labels import fmt_booking
from mitra_core.calls.queries import business_tz
from mitra_core.clock import utcnow
from mitra_core.models import Commitment, Contact, Fact
from mitra_core.models.enums import CommitmentStatus, FactCategory, FactStatus
from mitra_core.pii import hash_phone
from mitra_core.whatsapp import Document, send_customer_message
from mitra_core.whatsapp.outbox import business_name, customer_language
from mitra_core.whatsapp.team_messages import FOLLOW_UP_TOPIC
from mitra_core.whatsapp.templates import TemplateError, prepare, render

CallSendKind = Literal["booking_confirmation", "location", "document", "follow_up"]
SendStatus = Literal["sent", "blocked", "failed", "duplicate", "not_in_knowledge", "invalid"]

PDF_LINK = re.compile(r"https://[^\s<>\"']+?\.pdf\b", re.IGNORECASE)
MAPS_LINK = re.compile(r"https://maps\.app\.goo\.gl/([A-Za-z0-9_-]{4,64})")
_LINK = re.compile(r"https?://\S+")
# Quick-reply payloads per template, in button order (handled in manager/customers.py).
QUICK_REPLIES: dict[str, list[tuple[str, str]]] = {
    "booking_confirmation": [("change_time", "Change time")],
    "enquiry_follow_up": [("call_me", "Call me"), ("not_now", "Not now")],
}


@dataclass(slots=True)
class Knowledge:
    documents: list[tuple[str, str]] = field(default_factory=list)  # (name, pdf link)
    maps_suffix: str | None = None
    address: str | None = None


async def business_knowledge(session: AsyncSession, business_id: uuid.UUID) -> Knowledge:
    facts = await session.scalars(
        select(Fact).where(Fact.business_id == business_id, Fact.status == FactStatus.CONFIRMED)
    )
    out = Knowledge()
    for fact in facts:
        if (pdf := PDF_LINK.search(fact.value)) is not None:
            out.documents.append((fact.key, pdf.group(0)))
        if fact.category != FactCategory.LOCATION:
            continue
        if out.maps_suffix is None and (maps := MAPS_LINK.search(fact.value)) is not None:
            out.maps_suffix = maps.group(1)
        text = _LINK.sub("", fact.value).strip(" ,;-")
        if out.address is None and len(text) >= 8:
            out.address = text
    return out


def match_document(documents: list[tuple[str, str]], wanted: str) -> tuple[str, str] | None:
    """The document whose name contains (or is contained in) what the AI asked for."""
    w = " ".join(wanted.lower().split())
    if not w:
        return None
    for name, link in documents:
        n = " ".join(name.lower().split())
        if w in n or n in w:
            return name, link
    return None


async def _contact_name(session: AsyncSession, business_id: uuid.UUID, phone: str) -> str:
    name = await session.scalar(
        select(Contact.name).where(
            Contact.business_id == business_id, Contact.phone_hash == hash_phone(phone)
        )
    )
    return name or ""


async def next_appointment_words(
    session: AsyncSession, business_id: uuid.UUID, phone: str, now: datetime | None = None
) -> str | None:
    """The customer's next open appointment, e.g. "Tue 21 Oct, 6:15 pm" (business time)."""
    due = await session.scalar(
        select(Commitment.due_at)
        .join(Contact, Contact.id == Commitment.contact_id)
        .where(
            Commitment.business_id == business_id,
            Contact.phone_hash == hash_phone(phone),
            Commitment.kind == "appointment",
            Commitment.status == CommitmentStatus.OPEN,
            Commitment.due_at > (now or utcnow()),
        )
        .order_by(Commitment.due_at)
        .limit(1)
    )
    if due is None:
        return None
    tz: ZoneInfo = await business_tz(session, business_id)
    local = due.astimezone(tz)
    return fmt_booking(local.date(), local.time().replace(tzinfo=None))


def _outcome(msg: object) -> SendStatus:
    if msg is None:
        return "duplicate"
    status = str(getattr(msg, "status", "failed"))
    return status if status in {"sent", "blocked", "failed"} else "failed"  # type: ignore[return-value]


async def send_from_call(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    to_phone: str,
    kind: CallSendKind,
    client_ref: str,
    document: str | None = None,
    topic: str | None = None,
    when: str | None = None,
) -> SendStatus:
    """Send one in-call promise. Idempotent per ``client_ref`` (e.g. ``call:<id>:wa:1``)."""
    lang = await customer_language(session, business_id, to_phone)
    business = await business_name(session, business_id)
    know = await business_knowledge(session, business_id)
    name = await _contact_name(session, business_id, to_phone)
    ref = {"kind": f"call_{kind}", "client_ref": client_ref[:120]}
    url_suffix: str | None = None
    doc: Document | None = None
    if kind == "booking_confirmation":
        if not when or not when.strip():
            return "invalid"
        template, params = "booking_confirmation", {"name": name, "when": when}
        url_suffix = know.maps_suffix  # no map link on file -> free text only (window)
    elif kind == "location":
        if know.maps_suffix is None or know.address is None:
            return "not_in_knowledge"
        template, params = "share_location", {"address": know.address}
        url_suffix = know.maps_suffix
    elif kind == "document":
        found = match_document(know.documents, document or "")
        if found is None:
            return "not_in_knowledge"
        template, params = "share_document", {"document": found[0]}
        doc = Document(found[1], found[1].rsplit("/", 1)[-1][:120] or "document.pdf")
    else:
        template, params = (
            "enquiry_follow_up",
            {"name": name, "topic": topic or FOLLOW_UP_TOPIC[lang]},
        )
    try:
        text = render(template, lang, prepare(template, lang, {"business": business, **params}))
    except TemplateError:
        return "invalid"
    usable = not (template == "booking_confirmation" and url_suffix is None)
    if not usable:
        from mitra_core.whatsapp import deliver  # free text inside the window, else blocked

        msg = await deliver(
            session, business_id, to_phone=to_phone, purpose="customer", text=text,
            ref=ref, dedupe_key=client_ref[:160],
        )  # fmt: skip
        return _outcome(msg)
    msg = await send_customer_message(
        session,
        business_id,
        to_phone=to_phone,
        template=template,
        params=params,
        text=text,
        language=lang,
        buttons=QUICK_REPLIES.get(template),
        url_suffix=url_suffix,
        document=doc,
        ref=ref,
        dedupe_key=client_ref[:160],
    )
    return _outcome(msg)
