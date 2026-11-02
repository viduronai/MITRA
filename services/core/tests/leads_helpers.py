"""Shared setup for lead intake and webhook tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.config import Settings, get_settings
from mitra_core.leads.calling import get_heads_up, get_lead_dialer
from mitra_core.main import app
from mitra_core.webhooks import sender as sender_mod
from mitra_core.webhooks.sender import SendResult, get_webhook_sender
from tests.helpers import bearer, create_business, create_employee, new_actor

TOKEN = "test-service-token-0123456789abcdef"
SVC = bearer(TOKEN)
LEAD_PHONE = "+919812345678"
META_SECRET = "meta-app-secret-for-tests"
META_VERIFY = "meta-verify-token"


def configure(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "service_token": SecretStr(TOKEN),
        "meta_app_secret": SecretStr(META_SECRET),
        "meta_verify_token": SecretStr(META_VERIFY),
    }
    settings = Settings(**(base | overrides))
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


@dataclass
class FakeDialer:
    calls: list[dict[str, Any]] = field(default_factory=list)
    fail: bool = False

    async def __call__(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        *,
        employee_id: uuid.UUID,
        phone_e164: str,
        variables: dict[str, str],
        not_before: datetime | None,
        dedupe_key: str,
    ) -> uuid.UUID:
        if self.fail:
            raise ValueError("refused")
        self.calls.append(
            {
                "business_id": business_id,
                "employee_id": employee_id,
                "phone": phone_e164,
                "variables": variables,
                "not_before": not_before,
                "dedupe_key": dedupe_key,
            }
        )
        return uuid.uuid4()


@dataclass
class FakeHeadsUp:
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, session: AsyncSession, business_id: uuid.UUID, **kw: Any) -> None:
        self.sent.append(kw)


@dataclass
class FakeSender:
    """Records requests; answers ``status`` (None = connection error)."""

    status: int | None = 200
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def send(self, url: str, headers: dict[str, str], body: bytes) -> SendResult:
        self.requests.append({"url": url, "headers": headers, "body": body})
        if self.status is None:
            return SendResult(None, "Could not connect", 5)
        ok = 200 <= self.status < 300
        return SendResult(self.status, None if ok else f"Answered HTTP {self.status}", 5)


def install_fakes(monkeypatch: Any) -> tuple[FakeDialer, FakeHeadsUp, FakeSender]:
    dialer, heads_up, sender = FakeDialer(), FakeHeadsUp(), FakeSender()
    app.dependency_overrides[get_lead_dialer] = lambda: dialer
    app.dependency_overrides[get_heads_up] = lambda: heads_up
    app.dependency_overrides[get_webhook_sender] = lambda: sender
    monkeypatch.setattr(sender_mod, "default_sender", lambda: sender)
    return dialer, heads_up, sender


async def tenant(client: httpx.AsyncClient, name: str = "Sunrise Homes") -> dict[str, Any]:
    owner = new_actor()
    business = await create_business(client, owner, name=name, industry="real_estate")
    employee = await create_employee(client, owner, business["id"], role_template="lead_caller")
    return {
        "owner": owner,
        "headers": owner.headers(business["id"]),
        "business": business,
        "employee": employee,
    }


async def live_number(client: httpx.AsyncClient, t: dict[str, Any], e164: str) -> None:
    resp = await client.post(
        "/v1/phone-numbers/requests", json={"city": "Hyderabad"}, headers=t["headers"]
    )
    assert resp.status_code == 201, resp.text
    resp = await client.patch(
        f"/internal/v1/telephony/numbers/{resp.json()['id']}",
        json={"business_id": t["business"]["id"], "e164": e164, "kyc_status": "approved"},
        headers=SVC,
    )
    assert resp.status_code == 200, resp.text


async def enable_leads(client: httpx.AsyncClient, t: dict[str, Any]) -> dict[str, Any]:
    resp = await client.post("/v1/leads/setup", headers=t["headers"])
    assert resp.status_code == 200, resp.text
    setup: dict[str, Any] = resp.json()
    t["slug"], t["secret"] = setup["slug"], setup["secret"]
    return setup


_numbers = iter(range(10**6))


async def ready_tenant(client: httpx.AsyncClient, name: str = "Sunrise Homes") -> dict[str, Any]:
    """Business + lead caller + live number + lead intake on."""
    t = await tenant(client, name)
    await live_number(client, t, f"+9140{next(_numbers):08d}")
    await enable_leads(client, t)
    return t


async def send_lead(
    client: httpx.AsyncClient, t: dict[str, Any], body: dict[str, Any], **kw: Any
) -> httpx.Response:
    headers = {"X-Mitra-Secret": kw.pop("secret", t["secret"])}
    return await client.post(f"/lead-intake/{t['slug']}", json=body, headers=headers, **kw)
