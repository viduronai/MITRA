"""Shared test helpers (actors, tokens, API shortcuts)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from scripts.dev_token import mint

_phone_counter = iter(range(10**8))
FIXED_CODE = "246810"


@dataclass
class Actor:
    user_id: uuid.UUID
    phone: str
    name: str = "Test User"

    def headers(self, business_id: uuid.UUID | str | None = None, **extra: str) -> dict[str, str]:
        token = mint(
            self.user_id,
            business_id=uuid.UUID(str(business_id)) if business_id else None,
            phone=self.phone,
            name=self.name,
        )
        return {"Authorization": f"Bearer {token}", **extra}


def new_actor(name: str = "Test User") -> Actor:
    return Actor(user_id=uuid.uuid4(), phone=f"+9198{next(_phone_counter):08d}", name=name)


async def create_business(
    client: httpx.AsyncClient, actor: Actor, name: str = "Sunrise Clinic", **fields: Any
) -> dict[str, Any]:
    body = {"name": name, "industry": "clinic", "city": "Hyderabad", "languages": ["te", "en"]}
    resp = await client.post("/v1/businesses", json=body | fields, headers=actor.headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["business"]  # type: ignore[no-any-return]


async def create_employee(
    client: httpx.AsyncClient, actor: Actor, business_id: str, **fields: Any
) -> dict[str, Any]:
    body = {"name": "Priya", "role_template": "receptionist", "languages": ["te", "en"]}
    resp = await client.post(
        "/v1/employees", json=body | fields, headers=actor.headers(business_id)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def add_member(
    admin_engine: AsyncEngine, business_id: str, role: MemberRole, name: str = "Member"
) -> Actor:
    """Insert a user + membership directly (no invite API yet)."""
    actor = new_actor(name)
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO app_user (id, phone_e164, name) VALUES (:id, :phone, :name)"),
            {"id": actor.user_id, "phone": actor.phone, "name": name},
        )
        await conn.execute(
            text("INSERT INTO membership (business_id, user_id, role) VALUES (:b, :u, :r)"),
            {"b": uuid.UUID(business_id), "u": actor.user_id, "r": role.value},
        )
    return actor


class FakeClock:
    """Injectable clock for time-dependent endpoints: ``app.dependency_overrides[get_clock]``."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 10, 18, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


async def login(client: httpx.AsyncClient, phone: str, name: str | None = None) -> dict[str, Any]:
    """OTP request + verify. Requires the code generator to be pinned to ``FIXED_CODE``."""
    resp = await client.post("/v1/auth/otp/request", json={"phone": phone})
    assert resp.status_code == 202, resp.text
    body: dict[str, Any] = {"request_id": resp.json()["request_id"], "code": FIXED_CODE}
    if name:
        body["name"] = name
    resp = await client.post("/v1/auth/otp/verify", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def add_fact(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    category: str,
    key: str,
    value: str,
) -> dict[str, Any]:
    resp = await client.post(
        "/v1/knowledge/facts",
        json={"category": category, "key": key, "value": value},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]
