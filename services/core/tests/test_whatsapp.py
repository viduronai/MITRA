"""WhatsApp provider/simulator, owner notifications, and verified button replies (APPR-02/06)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.approvals import request_approval
from mitra_core.config import Settings, get_settings
from mitra_core.db import tenant_session
from mitra_core.main import app
from mitra_core.models.enums import MemberRole
from mitra_core.tenancy import TenantContext
from mitra_core.whatsapp import CloudApiProvider, notify_owner, send_staff_task, send_template
from mitra_core.whatsapp.inbound import parse_cloud_webhook, verify_signature
from tests.helpers import Actor, add_member
from tests.manager_helpers import make_business, wa_messages

SECRET = "test-whatsapp-app-secret"


def _signed_settings() -> None:
    settings = Settings(**{"WHATSAPP_APP_SECRET": SECRET})
    app.dependency_overrides[get_settings] = lambda: settings


def _webhook(actor: Actor, message: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {"changes": [{"value": {"messages": [{"from": actor.phone.lstrip("+"), **message}]}}]}
        ],
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": f"sha256={sig}", "Content-Type": "application/json"}


async def _approval(business_id: str) -> uuid.UUID:
    bid = uuid.UUID(business_id)
    async with tenant_session(TenantContext(business_id=bid)) as session:
        approval = await request_approval(
            session,
            bid,
            kind="refund",
            summary="Refund ₹2,000 to Lakshmi",
            payload={"rupees": 2000},
            requested_by="call:test",
        )
        await session.commit()
        return approval.id


async def test_notify_owner_reaches_owners_and_managers_once(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    await add_member(admin_engine, biz["id"], MemberRole.MANAGER, "Meena")
    await add_member(admin_engine, biz["id"], MemberRole.STAFF, "Ravi")
    bid = uuid.UUID(biz["id"])
    for _ in range(2):
        async with tenant_session(TenantContext(business_id=bid)) as session:
            await notify_owner(session, bid, "hot_lead", "Hot lead: Ravi", dedupe_key="call:1")
            await session.commit()
    msgs = await wa_messages(admin_engine, biz["id"])
    assert len(msgs) == 2  # owner + manager, not staff, and not twice
    assert {m["purpose"] for m in msgs} == {"alert"}


async def test_switched_off_alert_kind_is_not_sent(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    res = await client.patch(
        "/v1/manager/settings", json={"alert_kinds": ["hot_lead"]}, headers=biz["headers"]
    )
    assert res.status_code == 200, res.text
    bid = uuid.UUID(biz["id"])
    async with tenant_session(TenantContext(business_id=bid)) as session:
        assert await notify_owner(session, bid, "angry", "Upset caller") == []
        assert len(await notify_owner(session, bid, "hot_lead", "Hot lead")) == 1
        await session.commit()


async def test_template_and_staff_messages_store_no_raw_phone(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    staff = await add_member(admin_engine, biz["id"], MemberRole.STAFF, "Ravi")
    bid = uuid.UUID(biz["id"])
    async with tenant_session(TenantContext(business_id=bid)) as session:
        await send_template(
            session,
            bid,
            to_phone="+919811112222",
            template="call_heads_up",
            params={"name": "Ravi", "minutes": "2"},
        )
        await send_staff_task(
            session,
            bid,
            user_id=staff.user_id,
            text="Hot lead: call Lakshmi",
            action="call_back",
            customer="Lakshmi",
            brief="Hot lead",
        )
        await session.commit()
    msgs = await wa_messages(admin_engine, biz["id"])
    # Neither has written to us: both go as approved templates (call_heads_up, staff_handoff).
    assert [m["kind"] for m in msgs] == ["template", "template"]
    assert msgs[1]["body"] == (
        "Task from Sunrise Clinic: please call back Lakshmi. Hot lead Tap Done when finished."
    )
    assert all("+91" not in m["body"] for m in msgs)
    sim = await client.get("/v1/manager/whatsapp-sim/messages", headers=biz["headers"])
    assert sim.status_code == 200
    assert [m["phone_last4"] for m in sim.json()["items"]] == ["2222", staff.phone[-4:]]


async def test_webhook_rejects_unsigned(client: httpx.AsyncClient) -> None:
    _signed_settings()
    res = await client.post(
        "/webhooks/whatsapp", content=b"{}", headers={"X-Hub-Signature-256": "sha256=00"}
    )
    assert res.status_code == 401


async def test_verified_button_reply_approves_once(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    approval_id = await _approval(biz["id"])
    card = (await wa_messages(admin_engine, biz["id"]))[0]
    _signed_settings()

    # Right button, but not a reply to our card: refused.
    body, headers = _webhook(
        biz["owner"],
        {
            "id": "wamid.1",
            "type": "interactive",
            "context": {"id": "wamid.someone-else"},
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": card["buttons"][0]["id"], "title": "Approve"},
            },
        },
    )
    assert (
        await client.post("/webhooks/whatsapp", content=body, headers=headers)
    ).status_code == 200
    detail = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()
    assert detail["approval"]["status"] == "pending"

    body, headers = _webhook(
        biz["owner"],
        {
            "id": "wamid.2",
            "type": "interactive",
            "context": {"id": card["provider_message_id"]},
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": card["buttons"][0]["id"], "title": "Approve"},
            },
        },
    )
    assert (
        await client.post("/webhooks/whatsapp", content=body, headers=headers)
    ).status_code == 200
    detail = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()
    assert detail["approval"]["status"] == "approved"
    assert detail["approval"]["decided_via"] == "whatsapp"
    assert detail["approval"]["decided_by"] == str(biz["owner"].user_id)

    # A replayed tap is refused (single use) and the owner is told.
    body, headers = _webhook(
        biz["owner"],
        {
            "id": "wamid.3",
            "type": "interactive",
            "context": {"id": card["provider_message_id"]},
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": card["buttons"][1]["id"], "title": "Decline"},
            },
        },
    )
    await client.post("/webhooks/whatsapp", content=body, headers=headers)
    detail = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()
    assert detail["approval"]["status"] == "approved"
    assert "rejected_used" in [e["event"] for e in detail["events"]]


async def test_button_from_staff_or_stranger_is_ignored(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    approval_id = await _approval(biz["id"])
    card = (await wa_messages(admin_engine, biz["id"]))[0]
    staff = await add_member(admin_engine, biz["id"], MemberRole.STAFF, "Ravi")
    _signed_settings()
    body, headers = _webhook(
        staff,
        {
            "id": "wamid.9",
            "type": "interactive",
            "context": {"id": card["provider_message_id"]},
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": card["buttons"][0]["id"], "title": "Approve"},
            },
        },
    )
    res = await client.post("/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200
    detail = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()
    assert detail["approval"]["status"] == "pending"


def test_parse_and_signature_helpers() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919800000001",
                                    "id": "a",
                                    "type": "text",
                                    "text": {"body": "hi"},
                                },
                                {
                                    "from": "919800000001",
                                    "id": "b",
                                    "type": "audio",
                                    "audio": {"id": "m1"},
                                },
                                {"from": "919800000001", "id": "c", "type": "sticker"},
                            ]
                        }
                    }
                ]
            }
        ]
    }
    msgs = parse_cloud_webhook(payload)
    assert [(m.kind, m.from_phone) for m in msgs] == [
        ("text", "+919800000001"),
        ("voice", "+919800000001"),
    ]
    assert verify_signature(b"x", "sha256=" + hmac.new(b"k", b"x", hashlib.sha256).hexdigest(), "k")
    assert not verify_signature(b"x", None, "k")
    assert not verify_signature(b"x", "sha256=abc", "")


@pytest.mark.parametrize("ok", [True, False])
async def test_cloud_provider_payloads(ok: bool) -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        if not ok:
            return httpx.Response(500)
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    provider = CloudApiProvider("tok", "123", transport=httpx.MockTransport(handler))
    from mitra_core.whatsapp import Button

    result = await provider.send_buttons("+919800000001", "Approve?", [Button("a", "Approve")])
    assert result.ok is ok
    assert seen[0]["to"] == "919800000001"
    assert seen[0]["interactive"]["action"]["buttons"][0]["reply"] == {
        "id": "a",
        "title": "Approve",
    }
    if ok:
        assert result.message_id == "wamid.X"
