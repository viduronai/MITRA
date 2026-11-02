"""Unknown-question inbox: questions callers asked that the employee could not answer become
knowledge gaps for the owner to teach (WORKFLOWS §4, "What they know" tab)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.service import utcnow
from mitra_core.knowledge.extract import guess_category
from mitra_core.models import Call
from mitra_core.schemas.knowledge import GapOut

WINDOW = timedelta(days=30)
MAX_GAPS = 10


async def unknown_question_gaps(session: AsyncSession, business_id: uuid.UUID) -> list[GapOut]:
    # TODO(inbox): mark questions answered / dismissed; today they age out after 30 days.
    rows = await session.execute(
        select(Call.id, Call.unknown_questions)
        .where(
            Call.business_id == business_id,
            Call.started_at >= utcnow() - WINDOW,
            func.jsonb_array_length(Call.unknown_questions) > 0,
        )
        .order_by(Call.started_at.desc())
        .limit(100)
    )
    seen: set[str] = set()
    gaps: list[GapOut] = []
    for call_id, questions in rows:
        for question in questions:
            text = str(question).strip()
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            gaps.append(
                GapOut(
                    category=guess_category(text),
                    key=text[:120],
                    question=text,
                    source="call",
                    call_id=call_id,
                )
            )
            if len(gaps) >= MAX_GAPS:
                return gaps
    return gaps
