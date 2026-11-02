"""Call ingest (voice -> core) and the post-call pipeline (WORKFLOWS §4).

Post-call processing runs in-process after the end report is committed (FastAPI background
task). TODO(temporal): move ``process_call`` into a Temporal workflow with per-step retries
(recording upload, batch STT, actions such as Sheet rows / CRM / WhatsApp, handoff rules,
quality scoring, usage ledger, WhatsApp alerts). Every step here is idempotent: re-running it
for the same call replaces the rows it derived from that call.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.calls.labels import action_label, is_ok
from mitra_core.calls.summarizer import (
    ActionRecord,
    CallAnalysis,
    CallInput,
    Summarizer,
    Turn,
)
from mitra_core.db import tenant_session
from mitra_core.logging import get_logger
from mitra_core.models import (
    Business,
    Call,
    CallAction,
    Commitment,
    Contact,
    InteractionSummary,
    MemoryFact,
)
from mitra_core.models.enums import (
    CallResult,
    CallStatus,
    CommitmentStatus,
    MemoryStatus,
    Sentiment,
)
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.schemas.call import CallEndIn, CallerCard, CallStartIn, MemoryItem
from mitra_core.tenancy import TenantContext

log = get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def flatten_transcript(turns: list[dict[str, object]]) -> str:
    return "\n".join(str(t.get("text", "")) for t in turns).lower()


async def upsert_contact(session: AsyncSession, business_id: uuid.UUID, phone: str) -> Contact:
    digest = hash_phone(phone)
    await session.execute(
        insert(Contact)
        .values(business_id=business_id, phone_hash=digest, phone_last4=phone_last4(phone))
        .on_conflict_do_nothing(index_elements=["business_id", "phone_hash"])
    )
    contact = await session.scalar(
        select(Contact).where(Contact.business_id == business_id, Contact.phone_hash == digest)
    )
    assert contact is not None  # noqa: S101  (just inserted or already there)
    return contact


async def caller_card(
    session: AsyncSession, contact: Contact, *, exclude_call: uuid.UUID | None = None
) -> CallerCard:
    """Memory card for call start: facts (not expired), last 5 summaries, open promises."""
    now = utcnow()
    facts = await session.scalars(
        select(MemoryFact)
        .where(MemoryFact.contact_id == contact.id)
        .where((MemoryFact.expires_at.is_(None)) | (MemoryFact.expires_at > now))
        .order_by(MemoryFact.status, MemoryFact.updated_at.desc())
        .limit(20)
    )
    summaries = await session.scalars(
        select(InteractionSummary.summary)
        .where(InteractionSummary.contact_id == contact.id)
        .order_by(InteractionSummary.created_at.desc())
        .limit(5)
    )
    commitments = await session.scalars(
        select(Commitment.description)
        .where(Commitment.contact_id == contact.id, Commitment.status == CommitmentStatus.OPEN)
        .order_by(Commitment.due_at.nulls_last())
        .limit(5)
    )
    prior = await session.scalar(
        select(Call.id)
        .where(Call.contact_id == contact.id, Call.id != (exclude_call or uuid.uuid4()))
        .limit(1)
    )
    return CallerCard(
        contact_id=contact.id,
        name=contact.name,
        language=contact.language,
        returning=prior is not None,
        memory=[MemoryItem(key=f.key, value=f.value, status=f.status.value) for f in facts],
        recent_summaries=list(summaries),
        open_commitments=list(commitments),
    )


async def start_call(
    session: AsyncSession, business_id: uuid.UUID, body: CallStartIn
) -> tuple[Call, Contact | None, bool]:
    """Create the call row (idempotent on ``body.id``). Returns (call, contact, created)."""
    existing = await session.scalar(
        select(Call).where(Call.id == body.id, Call.business_id == business_id)
    )
    if existing is not None:
        contact = await session.get(Contact, existing.contact_id) if existing.contact_id else None
        return existing, contact, False
    contact = (
        await upsert_contact(session, business_id, body.caller_phone) if body.caller_phone else None
    )
    call = Call(
        id=body.id,
        business_id=business_id,
        employee_id=body.employee_id,
        contact_id=contact.id if contact else None,
        direction=body.direction,
        status=CallStatus.LIVE,
        phone_last4=contact.phone_last4 if contact else None,
        external_ref=body.external_ref,
        language=body.language,
        started_at=body.started_at,
    )
    session.add(call)
    await session.flush()
    return call, contact, True


async def end_call(session: AsyncSession, call: Call, body: CallEndIn) -> bool:
    """Store the end report. Returns False (no-op) if the call already ended (a retry)."""
    if call.status != CallStatus.LIVE:
        return False
    transcript = [t.model_dump(exclude_none=True) for t in body.transcript]
    call.status = CallStatus.ENDED
    call.ended_at = body.ended_at
    call.duration_seconds = max(0, round((body.ended_at - call.started_at).total_seconds()))
    call.transcript = transcript
    call.transcript_text = flatten_transcript(transcript)
    call.language = body.language or call.language
    call.latency_stats = body.latency_stats
    call.usage = body.usage
    call.recording_uri = body.recording_uri
    call.transcript_uri = body.transcript_uri
    # Hints for post-call processing (kept until the analysis replaces them).
    call.result = body.result
    call.fields = dict(body.fields)
    call.unknown_questions = list(body.unknown_questions)
    for seq, action in enumerate(body.actions):
        session.add(
            CallAction(
                business_id=call.business_id,
                call_id=call.id,
                seq=seq,
                name=action.name,
                args=action.args,
                result=action.result,
                ok=is_ok(action.result),
                created_at=body.ended_at,
            )
        )
    await session.flush()
    return True


def _alerts(call: Call, analysis: CallAnalysis, actions: list[CallAction]) -> list[dict[str, str]]:
    who = call.fields.get("name") or (f"…{call.phone_last4}" if call.phone_last4 else "A caller")
    alerts: list[dict[str, str]] = []
    if analysis.result == CallResult.INTERESTED:
        alerts.append({"kind": "hot_lead", "message": f"Hot lead: {who} is interested"})
    if analysis.sentiment == Sentiment.NEGATIVE:
        alerts.append({"kind": "angry", "message": f"{who} sounded upset"})
    for a in actions:
        if a.name == "alert_staff" and a.args.get("urgency") in {"urgent", "emergency"}:
            reason = str(a.args.get("reason") or "needs a person")[:120]
            alerts.append({"kind": "urgent", "message": f"Urgent: {reason}"})
        elif not a.ok and a.name not in {"check_availability"}:
            label = action_label(a.name, a.args, a.result)
            alerts.append({"kind": "failed_action", "message": f"Did not work: {label}"})
    if analysis.unknown_questions:
        first = analysis.unknown_questions[0]
        more = len(analysis.unknown_questions) - 1
        suffix = f" (+{more} more)" if more else ""
        alerts.append(
            {"kind": "unknown_question", "message": f'Could not answer: "{first}"{suffix}'}
        )
    return alerts


async def apply_analysis(
    session: AsyncSession, call: Call, analysis: CallAnalysis, actions: list[CallAction]
) -> None:
    call.summary = analysis.summary
    call.result = analysis.result
    call.fields = analysis.fields
    call.sentiment = analysis.sentiment
    call.next_step = analysis.next_step
    call.unknown_questions = analysis.unknown_questions
    call.alerts = _alerts(call, analysis, actions)
    call.status = CallStatus.PROCESSED
    call.processed_at = utcnow()

    # Re-runs replace what this call produced before.
    await session.execute(delete(Commitment).where(Commitment.call_id == call.id))
    await session.execute(delete(InteractionSummary).where(InteractionSummary.call_id == call.id))
    for c in analysis.commitments:
        session.add(
            Commitment(
                business_id=call.business_id,
                contact_id=call.contact_id,
                call_id=call.id,
                employee_id=call.employee_id,
                kind=c.kind,
                description=c.description,
                due_at=c.due_at,
                status=CommitmentStatus.OPEN,
            )
        )
    if call.contact_id is None:
        return
    contact = await session.get(Contact, call.contact_id)
    if contact is None:
        return
    session.add(
        InteractionSummary(
            business_id=call.business_id,
            contact_id=contact.id,
            call_id=call.id,
            summary=analysis.summary,
            created_at=call.ended_at or utcnow(),
        )
    )
    if contact.name is None and analysis.fields.get("name"):
        contact.name = analysis.fields["name"][:120]
    if call.language is not None:
        contact.language = call.language
    existing = {
        f.key: f
        for f in await session.scalars(
            select(MemoryFact).where(MemoryFact.contact_id == contact.id)
        )
    }
    for m in analysis.memory:
        fact = existing.get(m.key)
        if fact is None:
            fact = MemoryFact(
                business_id=call.business_id,
                contact_id=contact.id,
                key=m.key,
                value=m.value,
                status=m.status,
                confidence=m.confidence,
                expires_at=m.expires_at,
                source_call_id=call.id,
            )
            session.add(fact)
            existing[m.key] = fact
            continue
        # A guess never overwrites what the customer (or owner) confirmed.
        if fact.status == MemoryStatus.CONFIRMED and m.status == MemoryStatus.INFERRED:
            continue
        fact.value, fact.status = m.value, m.status
        fact.confidence, fact.expires_at = m.confidence, m.expires_at
        fact.source_call_id = call.id


async def _send_owner_alerts(session: AsyncSession, call: Call) -> None:
    """MGR-05 WhatsApp alerts (deduped per call). Never fails the processed call."""
    from mitra_core.manager.alerts import alerts_for_call  # lazy: manager imports calls

    try:
        await alerts_for_call(session, call)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        log.warning("call.alerts_failed", call_id=str(call.id), exc_type=type(exc).__name__)


async def process_call(call_id: uuid.UUID, business_id: uuid.UUID, summarizer: Summarizer) -> None:
    """Analyse an ended call and update memory. Safe to re-run."""
    async with tenant_session(TenantContext(business_id=business_id)) as session:
        call = await session.scalar(
            select(Call).where(Call.id == call_id, Call.business_id == business_id)
        )
        if call is None or call.status == CallStatus.LIVE or call.ended_at is None:
            return
        business = await session.get(Business, business_id)
        actions = list(
            await session.scalars(
                select(CallAction).where(CallAction.call_id == call.id).order_by(CallAction.seq)
            )
        )
        hint = call.result if call.status == CallStatus.ENDED else None
        data = CallInput(
            transcript=[
                Turn(role="user" if t.get("role") == "user" else "assistant", text=str(t["text"]))
                for t in call.transcript
                if t.get("text")
            ],
            actions=[ActionRecord(a.name, a.args, a.result, a.ok) for a in actions],
            direction=call.direction,
            language=call.language.value if call.language else None,
            ended_at=call.ended_at,
            timezone=business.timezone if business else "Asia/Kolkata",
            result_hint=hint,
            fields_hint={k: str(v) for k, v in call.fields.items()},
            unknown_hint=list(call.unknown_questions),
        )
        analysis = await summarizer.analyze(data)
        await apply_analysis(session, call, analysis, actions)
        await session.commit()
        await _send_owner_alerts(session, call)
        log.info(
            "call.processed",
            call_id=str(call.id),
            business_id=str(business_id),
            result=analysis.result.value,
            memory=len(analysis.memory),
            unknown=len(analysis.unknown_questions),
        )
        from mitra_core.team.hooks import after_call_processed  # hand-offs, events (TEAM)

        await after_call_processed(session, call.id)


async def run_post_call(call_id: uuid.UUID, business_id: uuid.UUID, summarizer: Summarizer) -> None:
    """Background-task entry: never raises (the call stays ``ended`` and can be re-processed)."""
    try:
        await process_call(call_id, business_id, summarizer)
    except Exception as exc:
        log.error("call.process_failed", call_id=str(call_id), exc_type=type(exc).__name__)
