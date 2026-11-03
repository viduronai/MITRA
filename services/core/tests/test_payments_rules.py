"""UPI collections: link expiry, lenders' collection hours, "Already paid" claims."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import get_settings
from mitra_core.db import tenant_session
from mitra_core.dialer.queue import is_collection
from mitra_core.manager.buttons import PaidClaim
from mitra_core.models import Business, PaymentRequest
from mitra_core.payments import scheduler
from mitra_core.payments.claims import on_paid_claim
from mitra_core.pii import hash_phone
from mitra_core.telephony.compliance import ComplianceFacts, KycStatus, NumberInfo, evaluate
from mitra_core.telephony.dnd import MockDndProvider
from mitra_core.telephony.enums import CallPurpose, ConsentScope, Decision, NumberHealth, NumberType
from mitra_core.telephony.service import load_facts
from mitra_core.tenancy import TenantContext
from tests.helpers import FakeClock
from tests.payments_helpers import CUSTOMER, connect_razorpay, create_link, customer_messages
from tests.test_calls import make_tenant

# FakeClock default: 2026-10-18 09:00 UTC. Links expire 15 days later: 2 Nov 09:00 UTC.
SENT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


async def _jobs(admin: AsyncEngine, business_id: str) -> list[str]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text("SELECT status FROM outbound_job WHERE business_id = :b"),
            {"b": uuid.UUID(business_id)},
        )
        return [str(r[0]) for r in rows]


async def test_link_expires_after_a_notice_and_stops_reminder_calls(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    bid = t["business"]["id"]
    out = await connect_razorpay(client, t["headers"])
    assert out["link_expiry_days"] == 15
    res = await client.post(
        "/v1/routines/from-library",
        json={"library_id": "payment_reminder", "enabled": True},
        headers=t["headers"],
    )
    assert res.status_code == 201, res.text
    req = await create_link(client, t["headers"], due_date="2026-10-20")
    assert req["expires_at"].startswith("2026-11-02T09:00")
    # Overdue step on 21 Oct: WhatsApp + one queued call (a day later).
    await scheduler.tick(datetime(2026, 10, 21, 5, 0, tzinfo=UTC))
    assert await _jobs(admin_engine, bid) == ["queued"]
    # Two days before expiry: one more WhatsApp.
    assert (await scheduler.tick(datetime(2026, 10, 31, 8, 0, tzinfo=UTC))).reminded == 0
    assert (await scheduler.tick(datetime(2026, 10, 31, 9, 1, tzinfo=UTC))).reminded == 1
    sent = await customer_messages(admin_engine, bid)
    assert [m["template"] for m in sent] == ["payment_link", "payment_reminder", "payment_reminder"]
    assert "02 Nov" in sent[2]["body"]
    assert (await scheduler.tick(datetime(2026, 11, 1, tzinfo=UTC))).reminded == 0
    # Expiry: status expired, the queued reminder call is cancelled.
    async with admin_engine.begin() as conn:  # pretend the call is still waiting
        await conn.execute(text("UPDATE outbound_job SET status = 'queued'"))
    await scheduler.tick(datetime(2026, 11, 2, 9, 1, tzinfo=UTC))
    row = (await client.get(f"/v1/payments/{req['id']}", headers=t["headers"])).json()
    assert row["status"] == "expired"
    assert row["remind_at"] is None
    assert await _jobs(admin_engine, bid) == ["cancelled"]


async def test_simulator_refuses_a_lapsed_link(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    res = await client.put(
        "/v1/payments/settings",
        json={
            "mode": "razorpay",
            "razorpay_key_id": "rzp_test_AbCdEf123456",
            "razorpay_key_secret": "key-secret-0123456789",
            "razorpay_webhook_secret": "hook-secret-0123456789",
            "link_expiry_days": 1,
        },
        headers=t["headers"],
    )
    assert res.json()["link_expiry_days"] == 1
    req = await create_link(client, t["headers"])
    clock.advance(25 * 3600)
    link_path = req["short_url"].split("/v1/", 1)[1]
    page = await client.get(f"/v1/{link_path}")
    assert "Pay with UPI" not in page.text
    assert (await client.post(f"/v1/{link_path}/pay")).status_code == 409
    row = (await client.get(f"/v1/payments/{req['id']}", headers=t["headers"])).json()
    assert row["status"] == "expired"


def _facts(at: datetime, **extra: Any) -> ComplianceFacts:
    number = NumberInfo(
        id=uuid.uuid4(),
        e164="+914041234567",
        type=NumberType.LOCAL,
        kyc_status=KycStatus.APPROVED,
        health=NumberHealth.HEALTHY,
    )
    return ComplianceFacts(
        purpose=CallPurpose.SERVICE,
        now=at,
        consents=frozenset({ConsentScope.SERVICE}),
        numbers=[number],
        **extra,
    )


def test_lenders_collect_only_in_rbi_hours() -> None:
    ist = timedelta(hours=5, minutes=30)
    evening = datetime(2026, 11, 3, 19, 30, tzinfo=UTC) - ist  # 7:30 pm IST
    noon = datetime(2026, 11, 3, 12, 0, tzinfo=UTC) - ist
    assert evaluate(_facts(evening)).decision == Decision.ALLOW  # ordinary service call
    assert evaluate(_facts(evening, collection=True)).decision == Decision.ALLOW  # not a lender
    late = evaluate(_facts(evening, collection=True, lender=True))
    assert late.decision == Decision.DEFER
    assert [r.code for r in late.reasons] == ["outside_hours"]
    assert late.defer_until is not None
    assert (late.defer_until + ist).hour == 9  # next morning, inside both windows
    assert evaluate(_facts(noon, collection=True, lender=True)).decision == Decision.ALLOW
    assert is_collection({"task": "collect_payment"})
    assert is_collection({"payment_amount": "₹2,000"})
    assert not is_collection({"task": "follow_up"})


async def test_lender_flag_reaches_the_gate(client: httpx.AsyncClient, clock: FakeClock) -> None:
    t = await make_tenant(client)
    bid = uuid.UUID(t["business"]["id"])
    res = await client.put(
        "/v1/payments/settings",
        json={"mode": "upi", "upi_vpa": "shop@okhdfcbank", "is_lender": True},
        headers=t["headers"],
    )
    assert res.json()["is_lender"] is True
    async with tenant_session(TenantContext(business_id=bid)) as session:
        business = await session.get(Business, bid)
        assert business is not None
        common: dict[str, Any] = {
            "business": business,
            "phone_e164": CUSTOMER,
            "purpose": CallPurpose.SERVICE,
            "now": clock(),
            "settings": get_settings(),
            "dnd": MockDndProvider(),
        }
        assert (await load_facts(session, **common, collection=True)).lender is True
        assert (await load_facts(session, **common)).lender is False  # only collection calls


async def test_already_paid_only_flags_for_the_owner(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, clock: FakeClock
) -> None:
    t = await make_tenant(client)
    bid = uuid.UUID(t["business"]["id"])
    await connect_razorpay(client, t["headers"])
    req = await create_link(client, t["headers"], due_date="2026-10-20")
    rid = uuid.UUID(req["id"])

    async def claim(phone: str, request_id: uuid.UUID | None) -> None:
        async with tenant_session(TenantContext(business_id=bid)) as session:
            await on_paid_claim(
                session, PaidClaim(bid, phone, hash_phone(phone), request_id, "button", None)
            )
            await session.commit()

    await claim("+919800000099", rid)  # someone else's number: ignored
    row = (await client.get(f"/v1/payments/{req['id']}", headers=t["headers"])).json()
    assert row["customer_says_paid_at"] is None
    await claim(CUSTOMER, rid)
    row = (await client.get(f"/v1/payments/{req['id']}", headers=t["headers"])).json()
    assert row["status"] == "sent"  # never marked paid by a claim
    assert row["customer_says_paid_at"] is not None
    assert row["remind_at"] == row["expires_at"]  # no reminders, but it still expires
    async with admin_engine.connect() as conn:
        bodies = (
            await conn.execute(
                text("SELECT body FROM wa_message WHERE business_id = :b AND purpose = 'alert'"),
                {"b": bid},
            )
        ).scalars()
        assert any("says they paid" in b for b in bodies)
    async with tenant_session(TenantContext(business_id=bid)) as session:
        stored = await session.scalar(select(PaymentRequest).where(PaymentRequest.id == rid))
        assert stored is not None
        assert stored.reminder_stage == 1
