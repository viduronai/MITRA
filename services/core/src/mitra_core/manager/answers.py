"""Answers to owner questions (MGR-02): every number and name comes from a ``tools`` result."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.queries import business_tz
from mitra_core.config import get_settings
from mitra_core.manager import tools
from mitra_core.manager.i18n import PERIOD, RESULT, STATUS, t, word
from mitra_core.manager.intents import Intent, Lang

RESULT_ORDER = (
    "booked",
    "interested",
    "call_back",
    "transferred",
    "not_interested",
    "info_only",
    "missed",
)


@dataclass(slots=True)
class Answer:
    text: str
    links: list[dict[str, str]] = field(default_factory=list)


def _link(path: str) -> str:
    return get_settings().app_base_url.rstrip("/") + path


def _rupees(paise: int) -> str:
    rupees, rest = divmod(paise, 100)
    return f"₹{rupees:,}" + (f".{rest:02d}" if rest else "")


async def summary_lines(
    session: AsyncSession, business_id: uuid.UUID, period: tools.Period, lang: Lang, now: datetime
) -> list[str]:
    stats = await tools.call_stats(session, business_id, period, now)
    label = word(PERIOD, period, lang)
    if stats.total == 0:
        return [t("summary_none", lang, period=label)]
    parts = [
        f"{stats.by_result[r]} {word(RESULT, r, lang)}"
        for r in RESULT_ORDER
        if stats.by_result.get(r)
    ]
    lines = [t("summary_head", lang, period=label, total=stats.total)]
    if parts:
        lines.append(" · ".join(parts))
    if stats.unknown_questions:
        lines.append(t("unknown_line", lang, count=stats.unknown_questions))
    return lines


async def attention_lines(
    session: AsyncSession, business_id: uuid.UUID, lang: Lang, now: datetime
) -> tuple[list[str], list[dict[str, str]]]:
    items = await tools.needs_attention(session, business_id, now)
    if not items:
        return [t("attention_none", lang)], []
    lines = [t("attention_head", lang, count=len(items))]
    links: list[dict[str, str]] = []
    for item in items[:4]:
        lines.append(f"• {item.message[:120]}")
        if item.approval_id:
            links.append({"label": item.message[:60], "href": f"/approvals/{item.approval_id}"})
        elif item.call_id:
            links.append({"label": item.message[:60], "href": f"/calls/{item.call_id}"})
    return lines, links


async def answer(
    session: AsyncSession, business_id: uuid.UUID, intent: Intent, now: datetime
) -> Answer:
    lang = intent.lang
    if intent.name == "summary":
        lines = await summary_lines(session, business_id, intent.period, lang, now)
        return Answer("\n".join(lines), [{"label": "calls", "href": "/calls"}])
    if intent.name == "attention":
        lines, links = await attention_lines(session, business_id, lang, now)
        return Answer("\n".join(lines), links)
    if intent.name == "bookings":
        day = await tools.local_date(session, business_id, now, intent.day_offset)
        rows = await tools.bookings_on(session, business_id, day)
        tz = await business_tz(session, business_id)
        label = f"{day:%a %d %b}"
        if not rows:
            return Answer(t("bookings_none", lang, day=label))
        lines = [t("bookings_head", lang, day=label, count=len(rows))]
        for commitment, who in rows[:5]:
            at = commitment.due_at.astimezone(tz) if commitment.due_at else None
            lines.append(f"• {at:%I:%M %p} {who}" if at else f"• {who}")
        return Answer("\n".join(lines))
    if intent.name == "search":
        found = await tools.search_calls(session, business_id, intent.query, now)
        if not found:
            return Answer(t("search_none", lang, query=intent.query))
        lines = [t("search_head", lang, count=len(found), query=intent.query)]
        lines += [f"• {c.who}: {(c.summary or '')[:80]}" for c in found]
        return Answer(
            "\n".join(lines), [{"label": c.who, "href": f"/calls/{c.call_id}"} for c in found]
        )
    if intent.name == "customer":
        contacts = await tools.find_contacts(session, business_id, intent.query)
        if not contacts:
            return Answer(t("customer_none", lang, query=intent.query))
        lines = [f"• {c.name}: {(s or '')[:100]}" for c, s in contacts]
        return Answer(
            "\n".join(lines),
            [{"label": c.name or "", "href": f"/customers/{c.id}"} for c, _ in contacts],
        )
    if intent.name == "wallet":
        paise = await tools.wallet_paise(session, business_id)
        if paise is None:
            return Answer(t("wallet_none", lang))
        return Answer(
            t("wallet", lang, amount=_rupees(paise)),
            [{"label": "billing", "href": "/more/billing"}],
        )
    if intent.name == "unknown_questions":
        questions = await tools.unknown_questions(session, business_id, intent.period, now)
        label = word(PERIOD, intent.period, lang)
        if not questions:
            return Answer(t("unknown_none", lang, period=label))
        return Answer(
            "\n".join([t("unknown_head", lang, period=label), *[f"• {q[:100]}" for q in questions]])
        )
    if intent.name == "team":
        staff = await tools.employees(session, business_id)
        if not staff:
            return Answer(t("team_none", lang))
        return Answer(
            "\n".join(
                t("team_line", lang, name=e.name, status=word(STATUS, e.status.value, lang))
                for e in staff
            ),
            [{"label": "team", "href": "/team"}],
        )
    if intent.name == "payments":
        return await _payments(session, business_id, intent, now)
    if intent.name == "unknown":
        return Answer(t("unknown", lang))
    return Answer(t("help", lang))


async def _payments(
    session: AsyncSession, business_id: uuid.UUID, intent: Intent, now: datetime
) -> Answer:
    """Who paid / what's pending / how much came in, from the payment requests only."""
    lang, link = intent.lang, [{"label": "payments", "href": "/payments"}]
    label = word(PERIOD, intent.period, lang)
    if intent.text == "pending":
        open_ = await tools.payments_pending(session, business_id)
        if not open_:
            return Answer(t("pending_none", lang), link)
        total = _rupees(sum(p.amount_paise for p in open_))
        lines = [t("pending_head", lang, count=len(open_), amount=total)]
        for p in open_[:5]:
            flag = f" ({t('says_paid', lang)})" if p.says_paid else ""
            lines.append(f"• {p.who}: {_rupees(p.amount_paise)} · {p.purpose[:40]}{flag}")
        return Answer("\n".join(lines), link)
    paid = await tools.payments_paid(session, business_id, intent.period, now)
    total = _rupees(sum(p.amount_paise for p in paid))
    if intent.text == "collected":
        return Answer(t("collected", lang, period=label, amount=total, count=len(paid)), link)
    if not paid:
        return Answer(t("paid_none", lang, period=label), link)
    lines = [t("paid_head", lang, period=label, count=len(paid), amount=total)]
    lines += [f"• {p.who}: {_rupees(p.amount_paise)} · {p.purpose[:40]}" for p in paid[:5]]
    return Answer("\n".join(lines), link)


def with_links(answer: Answer, lang: Lang) -> str:
    """WhatsApp text: the answer plus one "Open in app" link (07-SCREENS §6)."""
    if not answer.links:
        return answer.text
    return answer.text + "\n" + t("open_app", lang, link=_link(answer.links[0]["href"]))
