"""In-call WhatsApp sends from knowledge, the reminder template, UPI requests, and what button
taps do (call later / call me / not now / done / already paid / I'll come / change time)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import Settings, get_settings
from mitra_core.db import tenant_session
from mitra_core.dialer.queue import enqueue_call
from mitra_core.main import app
from mitra_core.manager import buttons
from mitra_core.manager.buttons import PaidClaim, register_paid_claim_handler
from mitra_core.manager.inbound import handle_inbound
from mitra_core.manager.planner import RulesPlanner
from mitra_core.models import Commitment
from mitra_core.models.enums import CommitmentStatus
from mitra_core.models.team import FollowUpTask, HandoffCard
from mitra_core.tenancy import TenantContext
from mitra_core.whatsapp import send_customer_message, send_heads_up, send_team_message
from mitra_core.whatsapp.inbound import InboundMessage
from tests.helpers import bearer
from tests.manager_helpers import add_contact, make_business

TOKEN = "test-service-token-0123456789abcdef"
CUSTOMER = "+919811112222"


def _tenant(biz: dict[str, Any]) -> Any:
    return tenant_session(TenantContext(business_id=uuid.UUID(biz["id"])))


async def _fact(admin: AsyncEngine, business_id: str, category: str, key: str, value: str) -> None:
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO fact (business_id, category, key, value, status)"
                " VALUES (:b, :c, :k, :v, 'confirmed')"
            ),
            {"b": uuid.UUID(business_id), "c": category, "k": key, "v": value},
        )


async def _rows(admin: AsyncEngine, business_id: str) -> list[dict[str, Any]]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT direction, kind, status, template, body, buttons, ref, provider_message_id"
                " FROM wa_message WHERE business_id = :b ORDER BY created_at"
            ),
            {"b": uuid.UUID(business_id)},
        )
        return [dict(r._mapping) for r in rows]


async def _jobs(admin: AsyncEngine, business_id: str) -> list[dict[str, Any]]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT source, status, not_before, dedupe_key FROM outbound_job"
                " WHERE business_id = :b ORDER BY created_at"
            ),
            {"b": uuid.UUID(business_id)},
        )
        return [dict(r._mapping) for r in rows]


async def _tap(
    payload: str | None, context: str | None, said: str = "", phone: str = CUSTOMER
) -> str:
    msg = InboundMessage(
        phone,
        "button_reply" if payload else "text",
        f"wamid.{uuid.uuid4().hex}",
        text=said,
        button_id=payload,
        context_id=context,
    )
    return await handle_inbound(
        msg, provider="sim", planner=RulesPlanner(), transcriber=None, now=datetime.now(UTC)
    )


# --- in-call sends (voice -> core) ---------------------------------------------------------------


async def _send(client: httpx.AsyncClient, biz: dict[str, Any], **body: Any) -> str:
    settings = Settings(service_token=SecretStr(TOKEN))
    app.dependency_overrides[get_settings] = lambda: settings
    payload = {
        "employee_id": biz["employee"]["id"],
        "contact_phone": CUSTOMER,
        "client_ref": f"call:test:wa:{uuid.uuid4().hex[:6]}",
    } | body
    res = await client.post("/internal/v1/whatsapp/sends", json=payload, headers=bearer(TOKEN))
    assert res.status_code == 201, res.text
    return str(res.json()["status"])


async def test_in_call_sends_use_only_the_business_knowledge(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["en"])
    assert await _send(client, biz, kind="location") == "not_in_knowledge"
    assert await _send(client, biz, kind="document", document="price list") == "not_in_knowledge"
    await _fact(
        admin_engine,
        biz["id"],
        "location",
        "Address",
        "Road No. 12, Banjara Hills https://maps.app.goo.gl/AbCd1234",
    )
    await _fact(
        admin_engine,
        biz["id"],
        "prices",
        "Price list",
        "All prices: https://example.com/p/prices.pdf",
    )
    assert await _send(client, biz, kind="location") == "sent"
    assert await _send(client, biz, kind="document", document="the price list") == "sent"
    assert await _send(client, biz, kind="document", document="brochure") == "not_in_knowledge"
    assert (
        await _send(client, biz, kind="booking_confirmation", when="Wed 21 Oct, 6:15 pm") == "sent"
    )
    assert await _send(client, biz, kind="follow_up", topic="MRI price") == "sent"
    ref = "call:test:wa:same"
    assert await _send(client, biz, kind="follow_up", client_ref=ref) == "sent"
    assert await _send(client, biz, kind="follow_up", client_ref=ref) == "duplicate"
    rows = await _rows(admin_engine, biz["id"])
    templates = [r["template"] for r in rows]
    assert templates[:4] == [
        "share_location",
        "share_document",
        "booking_confirmation",
        "enquiry_follow_up",
    ]
    assert rows[0]["body"] == (
        "You can find Sunrise Clinic at Road No. 12, Banjara Hills. Tap below for directions."
    )
    assert rows[0]["buttons"] == [{"url": "https://maps.app.goo.gl/AbCd1234", "title": "Open map"}]
    assert rows[1]["body"] == "Here is the Price list from Sunrise Clinic that you asked for."
    assert rows[2]["buttons"][0]["id"] == "change_time"


async def test_booking_confirmation_without_a_map_link_is_text_only(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["en"])
    assert (
        await _send(client, biz, kind="booking_confirmation", when="Wed 21 Oct, 6:15 pm")
        == "blocked"
    )
    assert await _send(client, biz, kind="booking_confirmation") == "invalid"


# --- reminders and UPI ---------------------------------------------------------------------------


async def test_appointment_reminder_uses_the_next_open_appointment(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["hi"])
    bid = uuid.UUID(biz["id"])
    contact = await add_contact(admin_engine, biz["id"], "Ravi", CUSTOMER)
    async with _tenant(biz) as session:
        blocked = await send_team_message(
            session, bid, to_phone=CUSTOMER, text="See you soon", kind="team_follow_up",
            task="remind_appointment",
        )  # fmt: skip
        session.add(
            Commitment(
                business_id=bid,
                contact_id=contact,
                kind="appointment",
                description="Appointment",
                due_at=datetime.now(UTC) + timedelta(days=1),
                status=CommitmentStatus.OPEN,
            )
        )
        await session.flush()
        sent = await send_team_message(
            session, bid, to_phone=CUSTOMER, text="See you soon", kind="team_follow_up",
            task="remind_appointment",
        )  # fmt: skip
        await session.commit()
    assert blocked is not None
    assert blocked.status == "blocked"
    assert sent is not None
    assert sent.template == "appointment_reminder"
    assert sent.body.startswith("याद दिला रहे हैं: Sunrise Clinic में आपकी appointment ")
    assert [b["id"] for b in sent.buttons] == ["ill_come", "change_time"]


async def test_upi_request_template(client: httpx.AsyncClient) -> None:
    biz = await make_business(client)
    async with _tenant(biz) as session:
        msg = await send_customer_message(
            session, uuid.UUID(biz["id"]), to_phone=CUSTOMER, template="payment_upi_request",
            params={
                "name": "",
                "amount": "500",
                "purpose": "consultation",
                "upi_id": "sunrise@okicici",
            },
        )  # fmt: skip
        await session.commit()
    assert msg is not None
    assert msg.body == (
        "నమస్కారం అండి, consultation కోసం Sunrise Clinic ₹500 request చేసింది. దయచేసి UPI ID "
        "sunrise@okicici కి pay చేయండి. Pay చేశాక PAID అని reply చేయండి."
    ).replace("sunrise@okicici కి", "sunrise@okiciciకి")


# --- button actions ------------------------------------------------------------------------------


async def test_call_me_later_moves_the_lead_call_to_the_next_window(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["en"])
    bid, emp = uuid.UUID(biz["id"]), uuid.UUID(biz["employee"]["id"])
    async with _tenant(biz) as session:
        await enqueue_call(
            session, bid, employee_id=emp, phone_e164=CUSTOMER, purpose="service",
            variables={}, source="lead", dedupe_key="lead:abc",
        )  # fmt: skip
        await send_heads_up(
            session,
            bid,
            phone_e164=CUSTOMER,
            name="Ravi",
            employee_id=emp,
            eta_seconds=120,
            source="lead",
        )
        await session.commit()
    card = (await _rows(admin_engine, biz["id"]))[0]
    assert await _tap("call_later", "wamid.forged") == "recorded"  # not our message: nothing
    assert await _tap("call_later", card["provider_message_id"]) == "acted"
    jobs = await _jobs(admin_engine, biz["id"])
    assert [(j["source"], str(j["status"])) for j in jobs] == [
        ("lead", "cancelled"),
        ("whatsapp", "queued"),
    ]
    assert jobs[1]["not_before"] >= datetime.now(UTC) + timedelta(hours=2) - timedelta(minutes=1)
    reply = (await _rows(admin_engine, biz["id"]))[-1]
    assert reply["body"].startswith("Sure. We'll call you at ")


async def test_not_now_pauses_that_follow_up_and_notes_it(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["en"])
    bid = uuid.UUID(biz["id"])
    contact = await add_contact(admin_engine, biz["id"], "Ravi", CUSTOMER)
    async with _tenant(biz) as session:
        task = FollowUpTask(
            business_id=bid, contact_id=contact, kind="routine", task="follow_up",
            channel="whatsapp", due_at=datetime.now(UTC), status="pending", context={}, outcome={},
        )  # fmt: skip
        session.add(task)
        await session.flush()
        await send_team_message(
            session, bid, to_phone=CUSTOMER, text="Any questions?", kind="team_follow_up",
            task="follow_up", ref_id=str(task.id), name="Ravi",
        )  # fmt: skip
        await session.commit()
        task_id = task.id
    card = (await _rows(admin_engine, biz["id"]))[0]
    assert [b["id"] for b in card["buttons"]] == [
        f"call_me:task:{task_id}",
        f"not_now:task:{task_id}",
    ]
    assert await _tap(f"not_now:task:{task_id}", card["provider_message_id"]) == "acted"
    async with admin_engine.connect() as conn:
        status = await conn.scalar(
            text("SELECT status FROM follow_up_task WHERE id = :i"), {"i": task_id}
        )
        note = await conn.scalar(
            text(
                "SELECT value FROM memory_fact WHERE contact_id = :c AND key = 'whatsapp_follow_up'"
            ),
            {"c": contact},
        )
    assert status == "cancelled"
    assert note is not None
    assert note.startswith("Said “not now”")


async def test_reminder_ill_come_and_change_time(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["en"])
    bid = uuid.UUID(biz["id"])
    contact = await add_contact(admin_engine, biz["id"], "Ravi", CUSTOMER)
    async with _tenant(biz) as session:
        session.add(
            Commitment(
                business_id=bid, contact_id=contact, kind="appointment", description="Cleaning",
                due_at=datetime.now(UTC) + timedelta(days=1), status=CommitmentStatus.OPEN,
            )
        )  # fmt: skip
        await session.flush()
        await send_team_message(
            session, bid, to_phone=CUSTOMER, text="See you soon", kind="team_follow_up",
            task="remind_appointment",
        )  # fmt: skip
        await session.commit()
    card = (await _rows(admin_engine, biz["id"]))[0]
    assert await _tap("ill_come", "wamid.forged") == "recorded"  # not our message: nothing
    assert await _tap("ill_come", card["provider_message_id"]) == "acted"
    reply = (await _rows(admin_engine, biz["id"]))[-1]
    assert reply["body"].startswith("Thank you! See you on ")
    async with admin_engine.connect() as conn:
        note = await conn.scalar(
            text(
                "SELECT value FROM memory_fact"
                " WHERE contact_id = :c AND key = 'appointment_confirmed'"
            ),
            {"c": contact},
        )
        still_open = await conn.scalar(
            text("SELECT status FROM commitment WHERE contact_id = :c"), {"c": contact}
        )
    assert note is not None
    assert note.startswith("Confirmed on WhatsApp")
    assert str(still_open) == "open"

    assert await _tap("change_time", card["provider_message_id"]) == "acted"
    jobs = await _jobs(admin_engine, biz["id"])
    assert [(j["source"], str(j["status"])) for j in jobs] == [("whatsapp", "queued")]
    assert str(jobs[0]["dedupe_key"]).startswith("wa_change_time:")
    reply = (await _rows(admin_engine, biz["id"]))[-1]
    assert reply["body"] == "Sure, we'll call you shortly to find a new time."


async def test_staff_done_marks_the_handoff_card(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["en"])
    bid = uuid.UUID(biz["id"])
    staff_phone = "+919800099999"
    async with _tenant(biz) as session:
        handoff = HandoffCard(
            business_id=bid, reason="wanted a person", message="call me", attempts=[]
        )
        session.add(handoff)
        await session.flush()
        await send_team_message(
            session, bid, to_phone=staff_phone, text="Missed transfer", kind="handoff_card",
            ref_id=str(handoff.id),
        )  # fmt: skip
        await session.commit()
        card_id = handoff.id
    card = (await _rows(admin_engine, biz["id"]))[0]
    assert card["template"] == "staff_handoff"
    assert (
        await _tap(f"done:card:{card_id}", card["provider_message_id"], phone=staff_phone)
        == "acted"
    )
    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, resolved_at FROM handoff_card WHERE id = :i"), {"i": card_id}
            )
        ).one()
    assert row.status == "done"
    assert row.resolved_at is not None


@pytest.fixture
def paid_claims() -> Any:
    seen: list[PaidClaim] = []

    async def handler(_session: Any, claim: PaidClaim) -> None:
        seen.append(claim)

    register_paid_claim_handler(handler)
    yield seen
    buttons._paid_handlers.remove(handler)


async def test_already_paid_and_paid_reply_only_notify_the_hook(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, paid_claims: list[PaidClaim]
) -> None:
    biz = await make_business(client, languages=["en"])
    request_id = uuid.uuid4()
    async with _tenant(biz) as session:
        await send_customer_message(
            session, uuid.UUID(biz["id"]), to_phone=CUSTOMER, template="payment_reminder",
            params={"amount": "500", "purpose": "consultation", "due": "5 Nov"},
            url_suffix="abc123", buttons=[(f"paid:{request_id}", "Already paid")],
        )  # fmt: skip
        await session.commit()
    card = (await _rows(admin_engine, biz["id"]))[0]
    assert {"url": "https://rzp.io/abc123", "title": "Pay now"} in card["buttons"]
    assert await _tap(f"paid:{request_id}", card["provider_message_id"]) == "acted"
    assert await _tap(None, None, said="PAID") == "acted"
    assert [(c.request_id, c.via) for c in paid_claims] == [(request_id, "button"), (None, "text")]
    reply = (await _rows(admin_engine, biz["id"]))[-1]
    assert reply["body"] == "Thank you! Sunrise Clinic will confirm your payment shortly."
