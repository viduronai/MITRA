"""Seeding helpers for approvals / WhatsApp / Manager tests (direct inserts as the schema owner)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.pii import hash_phone
from tests.helpers import Actor, create_business, create_employee, new_actor


async def make_business(
    client: httpx.AsyncClient, name: str = "Sunrise Clinic", **fields: Any
) -> dict[str, Any]:
    owner = new_actor("Asha")
    business = await create_business(client, owner, name=name, **fields)
    emp = await create_employee(client, owner, business["id"])
    return {
        "owner": owner,
        "id": business["id"],
        "headers": owner.headers(business["id"]),
        "employee": emp,
    }


async def add_contact(
    admin: AsyncEngine, business_id: str, name: str, phone: str = "+919800000001"
) -> uuid.UUID:
    cid = uuid.uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO contact (id, business_id, phone_hash, phone_last4, name)"
                " VALUES (:id, :b, :h, :l4, :n)"
            ),
            {
                "id": cid,
                "b": uuid.UUID(business_id),
                "h": hash_phone(phone),
                "l4": phone[-4:],
                "n": name,
            },
        )
    return cid


async def add_call(
    admin: AsyncEngine,
    business_id: str,
    *,
    started_at: datetime,
    result: str | None = "booked",
    employee_id: str | None = None,
    contact_id: uuid.UUID | None = None,
    summary: str = "",
    transcript_text: str = "",
    alerts: list[dict[str, str]] | None = None,
    unknown: list[str] | None = None,
    sentiment: str | None = None,
) -> uuid.UUID:
    call_id = uuid.uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO call (id, business_id, employee_id, contact_id, direction, status,"
                " phone_last4, started_at, ended_at, result, summary, transcript_text, alerts,"
                " unknown_questions, sentiment)"
                " VALUES (:id, :b, :e, :c, 'inbound', 'processed', '5678', :s, :s, :r, :sum, :tt,"
                " CAST(:alerts AS jsonb), CAST(:unknown AS jsonb), :sent)"
            ),
            {
                "id": call_id,
                "b": uuid.UUID(business_id),
                "e": uuid.UUID(employee_id) if employee_id else None,
                "c": contact_id,
                "s": started_at,
                "r": result,
                "sum": summary,
                "tt": transcript_text.lower(),
                "alerts": json.dumps(alerts or []),
                "unknown": json.dumps(unknown or []),
                "sent": sentiment,
            },
        )
    return call_id


async def wa_messages(admin: AsyncEngine, business_id: str) -> list[dict[str, Any]]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT direction, kind, purpose, user_id, body, buttons, ref, provider_message_id,"
                " dedupe_key FROM wa_message WHERE business_id = :b ORDER BY created_at, id"
            ),
            {"b": uuid.UUID(business_id)},
        )
        return [dict(r._mapping) for r in rows]


async def ask(
    client: httpx.AsyncClient, actor: Actor, business_id: str, said: str
) -> dict[str, Any]:
    res = await client.post(
        "/v1/manager/thread", json={"text": said}, headers=actor.headers(business_id)
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items[-1]["role"] == "mitra"
    return items[-1]  # type: ignore[no-any-return]
