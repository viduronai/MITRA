"""Outgoing webhooks (INT-13): endpoints, signed deliveries, retries with backoff, delivery log,
test event, lead.created from intake and call.ended from the call-end flow."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.config import Settings
from mitra_core.webhooks import signing
from mitra_core.webhooks.sender import HttpSender
from mitra_core.webhooks.service import MAX_ATTEMPTS, RETRY_DELAYS
from tests.helpers import FakeClock
from tests.leads_helpers import SVC, FakeSender, configure, install_fakes, ready_tenant, send_lead

HOOK = "https://hooks.example.com/mitra"


@pytest.fixture
def sender(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> FakeSender:
    configure()
    return install_fakes(monkeypatch)[2]


async def _hook(client: httpx.AsyncClient, t: dict[str, Any], **body: Any) -> dict[str, Any]:
    payload = {"url": HOOK, "events": ["lead.created", "call.ended"]} | body
    resp = await client.post("/v1/webhooks", json=payload, headers=t["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def test_create_shows_secret_once_and_validates(
    client: httpx.AsyncClient, sender: FakeSender
) -> None:
    t = await ready_tenant(client)
    hook = await _hook(client, t, headers={"X-Api-Key": "abc"}, description="CRM")
    assert hook["secret"].startswith("whsec_")
    assert hook["secret_hint"] == hook["secret"][:10]
    listed = (await client.get("/v1/webhooks", headers=t["headers"])).json()
    assert listed["items"][0]["secret"] is None
    assert listed["events"] == ["call.ended", "lead.created", "campaign.finished"]

    for bad in (
        {"url": "http://hooks.example.com"},
        {"url": "https://127.0.0.1/x"},
        {"events": ["test"]},
        {"events": []},
        {"headers": {"Host": "evil"}},
        {"headers": {"X-Mitra-Signature": "x"}},
        {"headers": {"Bad Name": "x"}},
    ):
        payload = {"url": HOOK, "events": ["lead.created"]} | bad
        resp = await client.post("/v1/webhooks", json=payload, headers=t["headers"])
        assert resp.status_code == 422, bad

    rotated = (
        await client.post(f"/v1/webhooks/{hook['id']}/rotate-secret", headers=t["headers"])
    ).json()
    assert rotated["secret"] != hook["secret"]


async def test_test_event_is_signed(
    client: httpx.AsyncClient, sender: FakeSender, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    hook = await _hook(client, t, headers={"X-Api-Key": "abc"})
    resp = await client.post(f"/v1/webhooks/{hook['id']}/test", headers=t["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "succeeded"
    assert resp.json()["response_status"] == 200

    [req] = sender.requests
    headers = req["headers"]
    assert req["url"] == HOOK
    assert headers["X-Api-Key"] == "abc"
    assert headers["X-Mitra-Event"] == "test"
    now = int(clock.now.timestamp())
    assert headers["X-Mitra-Timestamp"] == str(now)
    assert signing.verify(hook["secret"], headers["X-Mitra-Signature"], req["body"], now=now)
    body = json.loads(req["body"])
    assert body["event"] == "test"
    assert body["business_id"] == t["business"]["id"]

    sender.status = 500
    failed = (await client.post(f"/v1/webhooks/{hook['id']}/test", headers=t["headers"])).json()
    assert failed["status"] == "failed"  # test events are not retried
    assert failed["error"] == "Answered HTTP 500"


async def test_lead_created_is_delivered_after_intake(
    client: httpx.AsyncClient, sender: FakeSender
) -> None:
    t = await ready_tenant(client)
    hook = await _hook(client, t)
    await _hook(client, t, events=["call.ended"])  # not subscribed: gets nothing
    lead = (await send_lead(client, t, {"phone": "9811112222", "name": "Ravi", "area": "X"})).json()
    [req] = sender.requests
    body = json.loads(req["body"])
    assert body["event"] == "lead.created"
    data = body["data"]
    assert data["lead_id"] == lead["lead_id"]
    assert data["phone_last4"] == "2222"
    assert data["fields"] == {"area": "X"}
    assert "9811112222" not in req["body"].decode()
    log = (await client.get(f"/v1/webhooks/{hook['id']}/deliveries", headers=t["headers"])).json()
    assert [d["status"] for d in log["items"]] == ["succeeded"]


async def test_retries_with_backoff_then_gives_up(
    client: httpx.AsyncClient, sender: FakeSender, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    hook = await _hook(client, t)
    sender.status = None  # endpoint down
    await send_lead(client, t, {"phone": "9811112222"})
    log_url = f"/v1/webhooks/{hook['id']}/deliveries"
    [first] = (await client.get(log_url, headers=t["headers"])).json()["items"]
    assert first["status"] == "pending"
    assert first["attempts"] == 1
    assert first["error"] == "Could not connect"

    # Nothing is due before the first back-off step.
    early = await client.post("/internal/v1/webhooks/run", headers=SVC)
    assert early.json() == {"businesses": 0, "processed": 0}

    for delay in RETRY_DELAYS:
        clock.advance(delay)
        run = await client.post("/internal/v1/webhooks/run", headers=SVC)
        assert run.json() == {"businesses": 1, "processed": 1}
    [last] = (await client.get(log_url, headers=t["headers"])).json()["items"]
    assert last["attempts"] == MAX_ATTEMPTS
    assert last["status"] == "failed"
    assert last["next_attempt_at"] is None
    listed = (await client.get("/v1/webhooks", headers=t["headers"])).json()["items"][0]
    assert listed["consecutive_failures"] == MAX_ATTEMPTS
    assert listed["last_delivery_ok"] is False

    # Manual resend after fixing the receiver.
    sender.status = 204
    resent = await client.post(f"/v1/webhooks/deliveries/{last['id']}/retry", headers=t["headers"])
    assert resent.json()["status"] == "succeeded"
    again = await client.post(f"/v1/webhooks/deliveries/{last['id']}/retry", headers=t["headers"])
    assert again.status_code == 409


async def test_retry_recovers(
    client: httpx.AsyncClient, sender: FakeSender, clock: FakeClock
) -> None:
    t = await ready_tenant(client)
    hook = await _hook(client, t)
    sender.status = 503
    await send_lead(client, t, {"phone": "9811112222"})
    sender.status = 200
    clock.advance(RETRY_DELAYS[0])
    await client.post("/internal/v1/webhooks/run", headers=SVC)
    [d] = (await client.get(f"/v1/webhooks/{hook['id']}/deliveries", headers=t["headers"])).json()[
        "items"
    ]
    assert (d["status"], d["attempts"]) == ("succeeded", 2)
    # Both tries carried the same event id (receivers dedupe on it).
    ids = {r["headers"]["X-Mitra-Event-Id"] for r in sender.requests}
    assert len(ids) == 1


async def test_disabled_endpoint_gets_nothing(
    client: httpx.AsyncClient, sender: FakeSender
) -> None:
    t = await ready_tenant(client)
    hook = await _hook(client, t)
    resp = await client.patch(
        f"/v1/webhooks/{hook['id']}", json={"enabled": False}, headers=t["headers"]
    )
    assert resp.json()["enabled"] is False
    await send_lead(client, t, {"phone": "9811112222"})
    assert sender.requests == []
    delete = await client.delete(f"/v1/webhooks/{hook['id']}", headers=t["headers"])
    assert delete.status_code == 204


async def test_webhooks_are_tenant_isolated(client: httpx.AsyncClient, sender: FakeSender) -> None:
    a = await ready_tenant(client, "A Homes")
    b = await ready_tenant(client, "B Homes")
    hook = await _hook(client, a)
    for method, url in (
        ("get", f"/v1/webhooks/{hook['id']}/deliveries"),
        ("post", f"/v1/webhooks/{hook['id']}/test"),
        ("delete", f"/v1/webhooks/{hook['id']}"),
    ):
        resp = await client.request(method.upper(), url, headers=b["headers"])
        assert resp.status_code == 404
    assert (await client.get("/v1/webhooks", headers=b["headers"])).json()["items"] == []
    await send_lead(client, b, {"phone": "9811112222"})
    assert sender.requests == []  # B's lead never reaches A's endpoint


async def test_call_ended_hook_on_call_end_flow(
    client: httpx.AsyncClient, sender: FakeSender, admin_engine: AsyncEngine
) -> None:
    t = await ready_tenant(client)
    await _hook(client, t, events=["call.ended"])
    call_id = str(uuid.uuid4())
    started = "2026-10-18T09:00:00+00:00"
    start = await client.post(
        "/internal/v1/calls",
        json={
            "id": call_id,
            "employee_id": t["employee"]["id"],
            "direction": "outbound",
            "caller_phone": "+919811112222",
            "started_at": started,
        },
        headers=SVC,
    )
    assert start.status_code == 201, start.text
    end_body = {
        "employee_id": t["employee"]["id"],
        "ended_at": "2026-10-18T09:02:00+00:00",
        "transcript": [{"role": "assistant", "text": "Namaste"}, {"role": "user", "text": "Hi"}],
    }
    end = await client.post(f"/internal/v1/calls/{call_id}/end", json=end_body, headers=SVC)
    assert end.status_code == 200, end.text
    [req] = sender.requests
    body = json.loads(req["body"])
    assert body["event"] == "call.ended"
    assert body["data"]["call_id"] == call_id
    assert body["data"]["phone_last4"] == "2222"
    assert body["data"]["summary"]  # post-call processing ran first

    replay = await client.post(f"/internal/v1/calls/{call_id}/end", json=end_body, headers=SVC)
    assert replay.json()["replayed"] is True
    assert len(sender.requests) == 1


async def test_http_sender_blocks_private_resolution() -> None:
    async def resolve_private(host: str) -> list[str]:
        return ["10.1.2.3"]

    async def resolve_public(host: str) -> list[str]:
        return ["93.184.216.34"]

    def ok(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Test"] == "1"
        return httpx.Response(202)

    settings = Settings()
    blocked = HttpSender(settings, resolve=resolve_private, transport=httpx.MockTransport(ok))
    result = await blocked.send(HOOK, {"X-Test": "1"}, b"{}")
    assert (result.status, result.error) == (None, "Private addresses are not allowed")
    allowed = HttpSender(settings, resolve=resolve_public, transport=httpx.MockTransport(ok))
    assert (await allowed.send(HOOK, {"X-Test": "1"}, b"{}")).status == 202

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/"})

    moved = HttpSender(settings, resolve=resolve_public, transport=httpx.MockTransport(redirect))
    result = await moved.send(HOOK, {}, b"{}")
    assert (result.status, result.ok) == (302, False)  # redirects are not followed


async def test_due_businesses_function_is_definer_only(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT internal_webhook_due_businesses(now() + :d)"), {"d": timedelta(days=1)}
        )
        assert rows.all() == []
