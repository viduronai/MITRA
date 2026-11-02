"""Approvals (APPR-01..06): versioned single-use decisions, edit before approve, timeouts, log,
roles, rules and tenant isolation."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.approvals import needs_approval, register_handler, request_approval
from mitra_core.approvals.service import _handlers
from mitra_core.db import tenant_session
from mitra_core.models.enums import MemberRole
from mitra_core.tenancy import TenantContext
from tests.helpers import FakeClock, add_member
from tests.manager_helpers import make_business, wa_messages

calls: list[tuple[str, dict[str, Any]]] = []


async def _record(session: Any, approval: Any) -> None:
    calls.append((approval.status, dict(approval.payload)))


async def _boom(session: Any, approval: Any) -> None:
    raise RuntimeError("cannot apply")


@pytest.fixture(autouse=True)
def _handlers_fixture() -> Any:
    calls.clear()
    register_handler("test_kind", _record)
    register_handler("test_boom", _boom)
    yield
    _handlers.pop("test_kind", None)
    _handlers.pop("test_boom", None)


async def _request(business_id: str, kind: str = "test_kind", **kw: Any) -> uuid.UUID:
    async with tenant_session(TenantContext(business_id=uuid.UUID(business_id))) as session:
        approval = await request_approval(
            session,
            uuid.UUID(business_id),
            kind=kind,
            summary="10% discount for Mr. Rao (₹1.2L)",
            payload={"percent": 10, "customer": "Rao"},
            requested_by="call:test",
            **kw,
        )
        await session.commit()
        return approval.id


@pytest.fixture
async def biz(client: httpx.AsyncClient) -> dict[str, Any]:
    return await make_business(client)


async def test_request_sends_whatsapp_card_and_lists(
    client: httpx.AsyncClient, biz: dict[str, Any], admin_engine: AsyncEngine
) -> None:
    approval_id = await _request(biz["id"])
    msgs = await wa_messages(admin_engine, biz["id"])
    assert len(msgs) == 1
    assert msgs[0]["purpose"] == "approval"
    assert [b["id"] for b in msgs[0]["buttons"]] == [
        f"appr:{approval_id}:1:approve",
        f"appr:{approval_id}:1:decline",
    ]
    res = await client.get("/v1/approvals", headers=biz["headers"])
    assert res.status_code == 200
    body = res.json()
    assert body["pending"] == 1
    assert body["items"][0]["summary"].startswith("10% discount")


async def test_decide_is_single_use_and_runs_handler_once(
    client: httpx.AsyncClient, biz: dict[str, Any]
) -> None:
    approval_id = await _request(biz["id"])
    url = f"/v1/approvals/{approval_id}/decide"
    res = await client.post(url, json={"action": "approve", "version": 1}, headers=biz["headers"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    assert res.json()["decided_via"] == "app"
    again = await client.post(url, json={"action": "approve", "version": 1}, headers=biz["headers"])
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_decided"
    assert calls == [("approved", {"percent": 10, "customer": "Rao"})]

    detail = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()
    events = [e["event"] for e in detail["events"]]
    assert events == ["requested", "approved", "applied", "rejected_used"]


async def test_edit_bumps_version_and_old_cards_are_stale(
    client: httpx.AsyncClient, biz: dict[str, Any]
) -> None:
    approval_id = await _request(biz["id"])
    edit = await client.patch(
        f"/v1/approvals/{approval_id}",
        json={"version": 1, "payload": {"percent": 5, "customer": "Rao"}, "summary": "5% for Rao"},
        headers=biz["headers"],
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["version"] == 2
    url = f"/v1/approvals/{approval_id}/decide"
    stale = await client.post(url, json={"action": "approve", "version": 1}, headers=biz["headers"])
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_version"
    ok = await client.post(url, json={"action": "approve", "version": 2}, headers=biz["headers"])
    assert ok.status_code == 200
    # The handler sees exactly the edited payload.
    assert calls == [("approved", {"percent": 5, "customer": "Rao"})]
    events = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()[
        "events"
    ]
    assert [e["event"] for e in events] == [
        "requested",
        "edited",
        "rejected_stale",
        "approved",
        "applied",
    ]
    assert events[1]["detail"]["before"] == {"percent": 10, "customer": "Rao"}


async def test_staff_cannot_decide_or_edit(
    client: httpx.AsyncClient, biz: dict[str, Any], admin_engine: AsyncEngine
) -> None:
    approval_id = await _request(biz["id"])
    staff = await add_member(admin_engine, biz["id"], MemberRole.STAFF, "Ravi")
    res = await client.post(
        f"/v1/approvals/{approval_id}/decide",
        json={"action": "approve", "version": 1},
        headers=staff.headers(biz["id"]),
    )
    assert res.status_code == 403
    res = await client.patch(
        f"/v1/approvals/{approval_id}",
        json={"version": 1, "payload": {}},
        headers=staff.headers(biz["id"]),
    )
    assert res.status_code == 403
    manager = await add_member(admin_engine, biz["id"], MemberRole.MANAGER, "Meena")
    res = await client.post(
        f"/v1/approvals/{approval_id}/decide",
        json={"action": "decline", "version": 1, "note": "too much"},
        headers=manager.headers(biz["id"]),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "declined"
    assert calls == [("declined", {"percent": 10, "customer": "Rao"})]


async def test_timeout_applies_default(
    client: httpx.AsyncClient, biz: dict[str, Any], clock: FakeClock
) -> None:
    approval_id = await _request(
        biz["id"], expires_at=clock.now - timedelta(minutes=1), default_action="decline"
    )
    res = await client.get("/v1/approvals?status=all", headers=biz["headers"])
    item = next(i for i in res.json()["items"] if i["id"] == str(approval_id))
    assert item["status"] == "declined"
    assert item["decided_via"] == "timeout"
    assert calls == [("declined", {"percent": 10, "customer": "Rao"})]
    late = await client.post(
        f"/v1/approvals/{approval_id}/decide",
        json={"action": "approve", "version": 1},
        headers=biz["headers"],
    )
    assert late.status_code == 409


async def test_timeout_without_default_expires(
    client: httpx.AsyncClient, biz: dict[str, Any], clock: FakeClock
) -> None:
    approval_id = await _request(biz["id"], expires_at=clock.now - timedelta(minutes=1))
    res = await client.post(
        f"/v1/approvals/{approval_id}/decide",
        json={"action": "approve", "version": 1},
        headers=biz["headers"],
    )
    assert res.status_code == 409
    detail = (await client.get(f"/v1/approvals/{approval_id}", headers=biz["headers"])).json()
    assert detail["approval"]["status"] == "expired"
    assert calls == [("expired", {"percent": 10, "customer": "Rao"})]


async def test_handler_failure_keeps_decision(
    client: httpx.AsyncClient, biz: dict[str, Any]
) -> None:
    approval_id = await _request(biz["id"], kind="test_boom")
    res = await client.post(
        f"/v1/approvals/{approval_id}/decide",
        json={"action": "approve", "version": 1},
        headers=biz["headers"],
    )
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    assert "cannot apply" in res.json()["apply_error"]


async def test_other_business_cannot_see_or_decide(
    client: httpx.AsyncClient, biz: dict[str, Any]
) -> None:
    approval_id = await _request(biz["id"])
    other = await make_business(client, "Other Homes")
    assert (await client.get("/v1/approvals", headers=other["headers"])).json()["items"] == []
    res = await client.get(f"/v1/approvals/{approval_id}", headers=other["headers"])
    assert res.status_code == 404
    res = await client.post(
        f"/v1/approvals/{approval_id}/decide",
        json={"action": "approve", "version": 1},
        headers=other["headers"],
    )
    assert res.status_code == 404
    assert calls == []


async def test_rules_defaults_and_update(client: httpx.AsyncClient, biz: dict[str, Any]) -> None:
    bid = uuid.UUID(biz["id"])
    async with tenant_session(TenantContext(business_id=bid)) as session:
        assert await needs_approval(session, bid, "discount", amount=5)
        assert not await needs_approval(session, bid, "list_call", amount=20)
        assert await needs_approval(session, bid, "list_call", amount=80)
        assert await needs_approval(session, bid, "something_new")
    res = await client.put(
        "/v1/approvals/rules",
        json={"items": [{"kind": "list_call", "enabled": True, "threshold": 10}]},
        headers=biz["headers"],
    )
    assert res.status_code == 200, res.text
    rule = next(r for r in res.json()["items"] if r["kind"] == "list_call")
    assert rule["threshold"] == 10
    async with tenant_session(TenantContext(business_id=bid)) as session:
        assert await needs_approval(session, bid, "list_call", amount=20)
    res = await client.put(
        "/v1/approvals/rules",
        json={"items": [{"kind": "discount", "enabled": False}]},
        headers=biz["headers"],
    )
    async with tenant_session(TenantContext(business_id=bid)) as session:
        assert not await needs_approval(session, bid, "discount", amount=50)
