"""Shared test helpers (actors, tokens, API shortcuts)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.models.enums import MemberRole
from scripts.dev_token import mint

_phone_counter = iter(range(10**8))


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
