"""Dialer queue + worker: enqueue/dedupe, compliance gate, retry ladder, concurrency, callbacks."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.db import tenant_session
from mitra_core.dialer.enums import JobStatus
from mitra_core.dialer.queue import EnqueueError, cancel_jobs, enqueue_call
from mitra_core.dialer.sealing import SealError, seal, unseal
from mitra_core.models.campaign import OutboundJob
from mitra_core.telephony.enums import AttemptOutcome
from mitra_core.tenancy import TenantContext
from tests.dialer_helpers import (
    MONDAY_MORNING,
    SVC,
    PendingDialer,
    configure,
    consent,
    morning_clock,
    tenant,
    tick,
)
from tests.helpers import FakeClock

PHONE = "+919876500001"


def test_seal_roundtrip_and_tamper() -> None:
    sealed = seal(PHONE)
    assert PHONE not in sealed
    assert unseal(sealed) == PHONE
    assert seal(PHONE) != sealed  # random nonce
    broken = sealed[:-3] + ("A" if sealed[-3] != "A" else "B") + sealed[-2:]
    with pytest.raises(SealError):
        unseal(broken)


async def _jobs(business_id: str) -> list[OutboundJob]:
    async with tenant_session(TenantContext(business_id=uuid.UUID(business_id))) as s:
        return list(
            await s.scalars(
                select(OutboundJob)
                .where(OutboundJob.business_id == uuid.UUID(business_id))
                .order_by(OutboundJob.created_at)
            )
        )


async def _enqueue(t: dict[str, object], phone: str = PHONE, **kw: object) -> OutboundJob:
    business_id = uuid.UUID(t["business"]["id"])  # type: ignore[index]
    async with tenant_session(TenantContext(business_id=business_id)) as s:
        job = await enqueue_call(
            s,
            business_id,
            employee_id=uuid.UUID(t["employee"]["id"]),  # type: ignore[index]
            phone_e164=phone,
            purpose="service",
            source="test",
            **({"variables": {"lead_name": "Ravi"}, "not_before": MONDAY_MORNING} | kw),  # type: ignore[arg-type]
        )
        await s.commit()
        return job


async def test_enqueue_validates_and_dedupes(client: httpx.AsyncClient) -> None:
    configure()
    t = await tenant(client, number=False)
    first = await _enqueue(t, dedupe_key="lead:1")
    again = await _enqueue(t, dedupe_key="lead:1")
    assert again.id == first.id
    assert first.phone_last4 == "0001"
    assert first.variables == {"lead_name": "Ravi"}
    assert PHONE not in first.phone_enc
    other = await _enqueue(t, dedupe_key="lead:2")
    assert other.id != first.id
    with pytest.raises(EnqueueError):
        await _enqueue(t, phone="98765")
    with pytest.raises(EnqueueError):
        await _enqueue(t, variables={"Bad Name": "x"})  # type: ignore[arg-type]

    business_id = uuid.UUID(t["business"]["id"])
    async with tenant_session(TenantContext(business_id=business_id)) as s:
        assert await cancel_jobs(s, business_id, dedupe_key="lead:1") == 1
        await s.commit()
    # A cancelled job no longer blocks its dedupe key.
    fresh = await _enqueue(t, dedupe_key="lead:1")
    assert fresh.id != first.id


async def test_enqueue_respects_rls(client: httpx.AsyncClient, app_engine: AsyncEngine) -> None:
    configure()
    a = await tenant(client, number=False)
    b = await tenant(client, number=False)
    await _enqueue(a)
    async with app_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.business_id', :b, false)"), {"b": b["business"]["id"]}
        )
        count = await conn.scalar(text("SELECT count(*) FROM outbound_job"))
        await conn.execute(text("SELECT set_config('app.business_id', '', false)"))
    assert count == 0
    assert len(await _jobs(b["business"]["id"])) == 0


async def test_answered_call_completes_job(client: httpx.AsyncClient, clock: FakeClock) -> None:
    voice, _ = configure()
    morning_clock(clock)
    t = await tenant(client)
    await consent(client, t, PHONE)
    await _enqueue(t)
    from mitra_core.models.enums import CallResult

    voice.script["0001"] = (AttemptOutcome.ANSWERED, CallResult.INTERESTED)
    report = await tick(client)
    assert report["dialed"] == 1
    assert report["finished"] == 1
    [job] = await _jobs(t["business"]["id"])
    assert job.status == JobStatus.COMPLETED
    assert job.last_outcome == AttemptOutcome.ANSWERED
    assert job.attempts == 1
    [placed] = voice.placed
    assert placed.phone_e164 == PHONE
    assert placed.variables == {"lead_name": "Ravi"}
    assert str(placed.phone_number_id) == t["number_id"]


async def test_no_consent_blocks_with_reason(client: httpx.AsyncClient, clock: FakeClock) -> None:
    voice, _ = configure()
    morning_clock(clock)
    t = await tenant(client)
    await _enqueue(t)
    report = await tick(client)
    assert report["blocked"] == 1
    [job] = await _jobs(t["business"]["id"])
    assert job.status == JobStatus.BLOCKED
    assert job.reasons == ["no_consent"]
    assert voice.placed == []


async def test_outside_hours_defers(client: httpx.AsyncClient, clock: FakeClock) -> None:
    voice, _ = configure()
    morning_clock(clock)
    clock.now -= timedelta(hours=4)  # 06:30 IST
    t = await tenant(client)
    await consent(client, t, PHONE)
    await _enqueue(t, not_before=clock.now)
    report = await tick(client)
    assert report["deferred"] == 1
    [job] = await _jobs(t["business"]["id"])
    assert job.status == JobStatus.QUEUED
    assert job.reasons == ["outside_hours"]
    assert (job.not_before - clock.now) == timedelta(hours=2, minutes=30)  # 09:00 IST
    assert voice.placed == []


async def test_retry_ladder_then_failed(client: httpx.AsyncClient, clock: FakeClock) -> None:
    voice, _ = configure()
    morning_clock(clock)
    t = await tenant(client)
    await consent(client, t, PHONE)
    await _enqueue(t, retry_ladder=[30, 120])
    voice.script["0001"] = (AttemptOutcome.NO_ANSWER, None)
    start = clock.now
    await tick(client)
    [job] = await _jobs(t["business"]["id"])
    assert job.status == JobStatus.QUEUED
    assert job.not_before == start + timedelta(minutes=30)
    clock.advance(30 * 60)
    await tick(client)
    [job] = await _jobs(t["business"]["id"])
    assert job.not_before == start + timedelta(minutes=150)
    clock.advance(120 * 60)
    await tick(client)
    [job] = await _jobs(t["business"]["id"])
    assert job.status == JobStatus.FAILED
    assert job.attempts == 3
    assert len(voice.placed) == 3


async def test_concurrency_and_same_person(client: httpx.AsyncClient, clock: FakeClock) -> None:
    voice, _ = configure(voice=PendingDialer(), default_channels=2, dial_timeout_min=20)
    morning_clock(clock)
    t = await tenant(client)
    phones = [f"+91987650000{i}" for i in range(1, 5)]
    await consent(client, t, *phones)
    for phone in phones:
        await _enqueue(t, phone=phone)
    await _enqueue(t, phone=phones[0], dedupe_key="second-call")  # same person again
    report = await tick(client)
    assert report["dialed"] == 2
    statuses = [j.status for j in await _jobs(t["business"]["id"])]
    assert statuses.count(JobStatus.DIALING) == 2
    # Channels are full: nothing more is dialled until an outcome arrives.
    assert (await tick(client))["dialed"] == 0

    # The carrier reports one call unanswered; the other times out as no answer.
    jobs = await _jobs(t["business"]["id"])
    first = next(j for j in jobs if j.status == JobStatus.DIALING)
    resp = await client.patch(
        f"/internal/v1/telephony/attempts/{first.attempt_id}",
        json={"business_id": t["business"]["id"], "outcome": "no_answer"},
        headers=SVC,
    )
    assert resp.status_code == 200, resp.text
    report = await tick(client)
    assert report["finished"] == 1
    assert report["dialed"] == 1
    clock.advance(21 * 60)
    report = await tick(client)
    assert report["finished"] >= 1
    # The second job for the first person waited until their first call was over.
    dialled = [p.phone_e164 for p in voice.placed]
    assert len(set(dialled[:4])) == 4
    assert dialled.count(phones[0]) == 2


async def test_callback_endpoint(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    morning_clock(clock)
    t = await tenant(client)
    body = {
        "business_id": t["business"]["id"],
        "employee_id": t["employee"]["id"],
        "contact_phone": PHONE,
        "at": (clock.now + timedelta(hours=3)).isoformat(),
        "note": "Wants the 2BHK price",
        "contact_name": "Ravi",
    }
    resp = await client.post("/internal/v1/dialer/callbacks", json=body, headers=SVC)
    assert resp.status_code == 201, resp.text
    again = await client.post("/internal/v1/dialer/callbacks", json=body, headers=SVC)
    assert again.json()["job_id"] == resp.json()["job_id"]
    [job] = await _jobs(t["business"]["id"])
    assert job.purpose == "callback"
    assert job.variables == {"callback_note": "Wants the 2BHK price", "lead_name": "Ravi"}
    assert (await tick(client))["dialed"] == 0  # not due yet

    too_far = body | {"at": (clock.now + timedelta(days=40)).isoformat()}
    resp = await client.post("/internal/v1/dialer/callbacks", json=too_far, headers=SVC)
    assert resp.status_code == 422
    other = await tenant(client, number=False)
    wrong = body | {"employee_id": other["employee"]["id"]}
    resp = await client.post("/internal/v1/dialer/callbacks", json=wrong, headers=SVC)
    assert resp.status_code == 404
    resp = await client.post("/internal/v1/dialer/callbacks", json=body)
    assert resp.status_code == 401
