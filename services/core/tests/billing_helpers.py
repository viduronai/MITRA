"""Shared setup for the billing tests."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from pydantic import SecretStr

from mitra_core.config import Settings, get_settings
from mitra_core.main import app
from tests.helpers import bearer, create_business, create_employee, new_actor

TOKEN = "test-service-token-0123456789abcdef"
WEBHOOK_SECRET = "test-webhook-secret"


def configure(**overrides: Any) -> Settings:
    """Service token + webhook secret (aliased env names are set via model_copy)."""
    settings = Settings(service_token=SecretStr(TOKEN)).model_copy(
        update={"razorpay_webhook_secret": SecretStr(WEBHOOK_SECRET)} | overrides
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


async def tenant(
    client: httpx.AsyncClient, name: str = "Sunrise Clinic", **employee: Any
) -> dict[str, Any]:
    owner = new_actor()
    business = await create_business(client, owner, name=name)
    emp = await create_employee(client, owner, business["id"], **employee)
    return {
        "owner": owner,
        "headers": owner.headers(business["id"]),
        "business": business,
        "employee": emp,
    }


async def usage(
    client: httpx.AsyncClient,
    employee_id: str,
    call_id: str,
    seconds: float,
    *,
    direction: str = "outbound",
    outcome: str = "connected",
    started_at: datetime | None = None,
) -> httpx.Response:
    body = {
        "call_id": call_id,
        "employee_id": employee_id,
        "direction": direction,
        "outcome": outcome,
        "connected_seconds": seconds,
        "started_at": (started_at.isoformat() if started_at else "2026-10-18T09:00:00+00:00"),
    }
    return await client.post("/internal/v1/usage", json=body, headers=bearer(TOKEN))


async def summary(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = await client.get("/v1/billing/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def topup(
    client: httpx.AsyncClient, headers: dict[str, str], rupees: int, **extra: str
) -> httpx.Response:
    return await client.post(
        "/v1/billing/topups", json={"amount_paise": rupees * 100}, headers=headers | extra
    )
