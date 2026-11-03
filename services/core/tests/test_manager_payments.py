"""Ask Mitra money questions (te / hi / en), "not sure" instead of a wrong answer, and approval
summaries the server rebuilds from the payload (translatable, never stale)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.approvals import request_approval
from mitra_core.db import tenant_session
from mitra_core.manager.intents import parse
from mitra_core.tenancy import TenantContext
from tests.helpers import FakeClock
from tests.manager_helpers import ask, make_business

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)  # FakeClock default (14:30 IST)


@pytest.mark.parametrize(
    ("said", "name", "kind", "period"),
    [
        ("Who paid today?", "payments", "paid", "today"),
        ("Any payments pending?", "payments", "pending", "today"),
        ("How much did we collect this week?", "payments", "collected", "week"),
        ("आज किसने pay किया?", "payments", "paid", "today"),
        ("कितने पैसे बकाया हैं?", "payments", "pending", "today"),
        ("इस हफ्ते कितना पैसा जमा हुआ?", "payments", "collected", "week"),
        ("ఈ రోజు ఎవరు కట్టారు?", "payments", "paid", "today"),
        ("ఎన్ని పేమెంట్లు బాకీ ఉన్నాయి?", "payments", "pending", "today"),
        ("ఈ వారం ఎంత వసూలు అయింది?", "payments", "collected", "week"),
        ("Send Ramesh a payment link for ₹2,000", "payment_link", "", "today"),
        ("What happened this week?", "summary", "", "week"),
        ("How's the weather?", "unknown", "", "today"),
        ("मौसम कैसा है?", "unknown", "", "today"),
        ("వాతావరణం ఎలా ఉంది?", "unknown", "", "today"),
    ],
)
def test_money_and_unknown_phrasings(said: str, name: str, kind: str, period: str) -> None:
    intent = parse(said)
    assert intent.name == name
    if name == "payments":
        assert (intent.text, intent.period) == (kind, period)


async def _payment(
    admin: AsyncEngine,
    business_id: str,
    *,
    who: str,
    paise: int,
    status: str,
    paid_at: datetime | None = None,
) -> None:
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO payment_request (business_id, customer_name, amount_paise, purpose,"
                " status, mode, source, paid_at) VALUES (:b, :n, :a, 'consultation', :s, 'upi',"
                " 'owner', :p)"
            ),
            {"b": uuid.UUID(business_id), "n": who, "a": paise, "s": status, "p": paid_at},
        )


async def test_payment_answers_come_from_payments(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    biz = await make_business(client)
    empty = await ask(client, biz["owner"], biz["id"], "Who paid today?")
    assert empty["text"] == "Today: no payments received yet."
    await _payment(
        admin_engine,
        biz["id"],
        who="Ravi",
        paise=150_000,
        status="paid",
        paid_at=NOW - timedelta(hours=1),
    )
    await _payment(
        admin_engine,
        biz["id"],
        who="Lakshmi",
        paise=50_000,
        status="paid",
        paid_at=NOW - timedelta(days=3),
    )
    await _payment(admin_engine, biz["id"], who="Suresh", paise=200_000, status="sent")
    paid = await ask(client, biz["owner"], biz["id"], "Who paid today?")
    assert paid["text"].splitlines() == [
        "Today: 1 paid, ₹1,500 in total",
        "• Ravi: ₹1,500 · consultation",
    ]
    week = await ask(client, biz["owner"], biz["id"], "How much did we collect this week?")
    assert week["text"] == "This week: ₹2,000 collected from 2 payments."
    pending = await ask(client, biz["owner"], biz["id"], "ఎన్ని పేమెంట్లు బాకీ ఉన్నాయి?")
    assert pending["text"].startswith("1 payments బాకీ ఉన్నాయి, మొత్తం ₹2,000")
    lost = await ask(client, biz["owner"], biz["id"], "How's the weather?")
    assert lost["text"].startswith("I'm not sure what you mean.")


# --- server-owned approval summaries ------------------------------------------------------------


async def _list_call(biz: dict[str, Any], contacts: int = 3) -> uuid.UUID:
    bid = uuid.UUID(biz["id"])
    async with tenant_session(TenantContext(business_id=bid)) as session:
        approval = await request_approval(
            session, bid, kind="list_call", summary="Call a list of 3 people: 'Diwali' (service)",
            payload={
                "campaign_id": str(uuid.uuid4()),
                "contacts": contacts,
                "name": "Diwali offer",
            },
            requested_by="campaign",
        )  # fmt: skip
        await session.commit()
        return approval.id


async def test_list_call_summary_follows_the_edit_and_is_locked(client: httpx.AsyncClient) -> None:
    biz = await make_business(client)
    approval_id = await _list_call(biz)
    detail = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()
    approval = detail["approval"]
    assert approval["summary"] == "Call a list of 3 people: “Diwali offer”"
    assert approval["summary_key"] == "list_call"
    assert approval["summary_params"] == {"count": "3", "name": "Diwali offer"}
    url = f"/v1/approvals/{approval_id}"
    payload = approval["payload"] | {"contacts": 2}
    locked = await client.patch(
        url,
        json={"version": 1, "payload": payload, "summary": "Call everyone"},
        headers=biz["headers"],
    )
    assert locked.status_code == 422
    assert locked.json()["error"]["code"] == "summary_locked"
    ok = await client.patch(
        url,
        json={"version": 1, "payload": payload, "summary": approval["summary"]},
        headers=biz["headers"],
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["summary"] == "Call a list of 2 people: “Diwali offer”"
    assert ok.json()["summary_params"]["count"] == "2"
    too_many = await client.patch(
        url, json={"version": 2, "payload": payload | {"contacts": 5}}, headers=biz["headers"]
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "invalid_edit"


async def test_payment_link_summary_in_rupees(client: httpx.AsyncClient) -> None:
    biz = await make_business(client)
    bid = uuid.UUID(biz["id"])
    async with tenant_session(TenantContext(business_id=bid)) as session:
        approval = await request_approval(
            session, bid, kind="payment_link", summary="x",
            payload={"payment_request_id": str(uuid.uuid4()), "amount_paise": 1_500_000,
                     "discount_percent": 10, "purpose": "MRI", "customer": "Ravi"},
            requested_by="employee",
        )  # fmt: skip
        await session.commit()
    assert approval.summary == "Send Ravi a payment link: ₹15,000 (10% off) for MRI"
    assert approval.summary_key == "payment_link_discount"
    assert approval.summary_params["amount"] == "₹15,000"
