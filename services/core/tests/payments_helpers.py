"""Helpers for the UPI collections tests (payments module)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.billing.providers import hmac_hex

CUSTOMER = "+919876543210"
KEY_ID = "rzp_test_AbCdEf123456"
KEY_SECRET = "key-secret-0123456789"
HOOK_SECRET = "hook-secret-0123456789"


async def connect_razorpay(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    res = await client.put(
        "/v1/payments/settings",
        json={
            "mode": "razorpay",
            "razorpay_key_id": KEY_ID,
            "razorpay_key_secret": KEY_SECRET,
            "razorpay_webhook_secret": HOOK_SECRET,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


async def create_link(
    client: httpx.AsyncClient, headers: dict[str, str], **fields: Any
) -> dict[str, Any]:
    body = {
        "phone": CUSTOMER,
        "customer_name": "Ramesh",
        "amount_paise": 200_000,
        "purpose": "Consultation fee",
    } | fields
    res = await client.post("/v1/payments", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()  # type: ignore[no-any-return]


def webhook_token(settings_out: dict[str, Any]) -> str:
    return str(settings_out["webhook_url"]).rsplit("/", 1)[-1]


def signed(body: bytes, secret: str = HOOK_SECRET) -> dict[str, str]:
    return {"X-Razorpay-Signature": hmac_hex(secret, body), "Content-Type": "application/json"}


async def customer_messages(admin: AsyncEngine, business_id: str) -> list[dict[str, Any]]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT body, ref, dedupe_key, purpose, template, status, buttons FROM wa_message"
                " WHERE business_id = :b AND purpose = 'customer' ORDER BY created_at, id"
            ),
            {"b": uuid.UUID(business_id)},
        )
        return [dict(r._mapping) for r in rows]


async def owner_messages(admin: AsyncEngine, business_id: str) -> list[dict[str, Any]]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT body, ref FROM wa_message"
                " WHERE business_id = :b AND purpose = 'alert' ORDER BY created_at, id"
            ),
            {"b": uuid.UUID(business_id)},
        )
        return [dict(r._mapping) for r in rows]
