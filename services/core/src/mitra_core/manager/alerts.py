"""Instant WhatsApp alerts to the owner (MGR-05): hot lead, angry customer, VIP caller, failed
payment, campaign auto-paused. Each alert is deduped per (recipient, kind, subject), so a
re-processed call or a repeated campaign pause never pings the owner twice.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.config import get_settings
from mitra_core.logging import get_logger
from mitra_core.manager.intents import Lang
from mitra_core.models import Call, Commitment, Contact, MemoryFact
from mitra_core.models.enums import MemoryStatus
from mitra_core.whatsapp import manager_settings
from mitra_core.whatsapp import notify_owner as wa_notify_owner

log = get_logger(__name__)

TITLES: dict[str, dict[str, str]] = {
    "hot_lead": {"en": "🔥 Hot lead", "hi": "🔥 गरम लीड", "te": "🔥 హాట్ లీడ్"},
    "angry": {"en": "⚠️ Upset customer", "hi": "⚠️ नाराज़ ग्राहक", "te": "⚠️ కోపంగా ఉన్న కస్టమర్"},
    "vip": {"en": "⭐ VIP caller", "hi": "⭐ VIP कॉलर", "te": "⭐ VIP కాలర్"},
    "payment_failed": {"en": "💳 Payment failed", "hi": "💳 पेमेंट फेल", "te": "💳 పేమెంట్ విఫలం"},
    "campaign_paused": {
        "en": "⏸️ List calling paused",
        "hi": "⏸️ लिस्ट कॉलिंग रुकी",
        "te": "⏸️ లిస్ట్ కాలింగ్ ఆగింది",
    },
    "urgent": {"en": "🚨 Urgent", "hi": "🚨 ज़रूरी", "te": "🚨 అత్యవసరం"},
}
# Call alert kinds (calls.service._alerts) that become instant WhatsApp alerts.
CALL_ALERT_KINDS = {"hot_lead": "hot_lead", "angry": "angry", "urgent": "urgent"}
VIP_KEYS = ("vip", "is_vip")


def _lang(value: Any) -> Lang:
    return value if value in {"en", "hi", "te"} else "en"


async def send_alert(
    session: AsyncSession,
    business_id: uuid.UUID,
    kind: str,
    *,
    detail: str,
    link: str | None = None,
    ref: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    max_len: int = 400,
) -> int:
    """Format and send one alert; returns how many owners/managers were messaged."""
    settings = await manager_settings(session, business_id)
    lang = _lang(settings.language.value if settings.language else None)
    title = TITLES.get(kind, {}).get(lang) or TITLES.get(kind, {}).get("en") or kind
    lines = [title, detail.strip()[:max_len]]
    if link:
        lines.append(get_settings().app_base_url.rstrip("/") + link)
    sent = await wa_notify_owner(
        session, business_id, kind, "\n".join(lines), ref=ref, dedupe_key=dedupe_key
    )
    return len(sent)


async def notify_owner(
    session: AsyncSession,
    business_id: uuid.UUID,
    *,
    kind: str,
    title: str,
    body: str,
    link: str | None = None,
) -> None:
    """Adapter for ``dialer.hooks.alert_owner`` (campaign auto-pause and friends)."""
    await send_alert(
        session,
        business_id,
        kind,
        detail=f"{title}\n{body}" if title else body,
        link=link,
        dedupe_key=f"{title}:{body}"[:150],
    )


async def alerts_for_call(session: AsyncSession, call: Call) -> int:
    """Turn a processed call's alerts into WhatsApp alerts (plus VIP callers). Idempotent."""
    sent = 0
    link = f"/calls/{call.id}"
    for alert in call.alerts:
        kind = CALL_ALERT_KINDS.get(str(alert.get("kind")))
        if kind is None:
            continue
        message = str(alert.get("message") or "")
        if call.summary:
            message = f"{message}\n{call.summary[:200]}"
        if kind == "urgent":
            # The team's escalation brief is deduped against this alert, so this one message
            # must carry the full picture: what the caller told us and what was promised.
            message += await _urgent_context(session, call)
        sent += await send_alert(
            session,
            call.business_id,
            kind,
            detail=message,
            link=link,
            ref={"call_id": str(call.id)},
            dedupe_key=f"call:{call.id}",
            max_len=1000 if kind == "urgent" else 400,
        )
    if call.contact_id is not None:
        vip = await session.scalar(
            select(MemoryFact.value).where(
                MemoryFact.business_id == call.business_id,
                MemoryFact.contact_id == call.contact_id,
                MemoryFact.key.in_(VIP_KEYS),
            )
        )
        if vip and vip.strip().lower() not in {"no", "false", "0"}:
            name = await session.scalar(select(Contact.name).where(Contact.id == call.contact_id))
            sent += await send_alert(
                session,
                call.business_id,
                "vip",
                detail=f"{name or 'A VIP customer'} called. {call.summary or ''}"[:300],
                link=link,
                ref={"call_id": str(call.id)},
                dedupe_key=f"call:{call.id}",
            )
    return sent


async def _urgent_context(session: AsyncSession, call: Call) -> str:
    """Collected fields, confirmed customer memory and promises made, as extra alert lines."""
    known = {str(k): str(v) for k, v in (call.fields or {}).items() if v not in (None, "")}
    if call.contact_id is not None:
        facts = await session.execute(
            select(MemoryFact.key, MemoryFact.value)
            .where(
                MemoryFact.business_id == call.business_id,
                MemoryFact.contact_id == call.contact_id,
                MemoryFact.status == MemoryStatus.CONFIRMED,
            )
            .order_by(MemoryFact.updated_at.desc())
            .limit(6)
        )
        for key, value in facts:
            known.setdefault(key, value)
    lines: list[str] = []
    if known:
        lines.append("Knows: " + "; ".join(f"{k}: {v}" for k, v in list(known.items())[:6]))
    promised = list(
        await session.scalars(
            select(Commitment.description)
            .where(Commitment.business_id == call.business_id, Commitment.call_id == call.id)
            .limit(3)
        )
    )
    if promised:
        lines.append("Promised: " + "; ".join(promised))
    return "".join(f"\n{line}" for line in lines)
