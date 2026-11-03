"""Encrypted customer numbers (08 section 6): sealing, reveal + access log, erasure."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.db import tenant_session
from mitra_core.dialer import sealing
from mitra_core.models.enums import MemberRole
from mitra_core.phones import (
    PhoneSealError,
    mask_phone,
    reveal_phone,
    seal_phone,
    unseal_phone,
)
from mitra_core.tenancy import TenantContext
from tests.dialer_helpers import SVC, configure, consent, tenant
from tests.helpers import add_member
from tests.test_calls import PHONE, configure_service, make_tenant, start

BIZ_A, BIZ_B = uuid.uuid4(), uuid.uuid4()


def _legacy_v1(plain: str) -> str:
    """What the dialer wrote before 0006 (stdlib encrypt-then-MAC, no business binding)."""
    import base64
    import hashlib
    import hmac
    import secrets

    nonce = secrets.token_bytes(16)
    data = plain.encode()
    body = bytes(a ^ b for a, b in zip(data, sealing._stream(nonce, len(data)), strict=True))
    tag = hmac.new(sealing._key("mac"), nonce + body, hashlib.sha256).digest()[:16]
    return "v1:" + base64.urlsafe_b64encode(nonce + body + tag).decode()


def test_seal_is_per_business_authenticated_and_versioned() -> None:
    sealed = seal_phone(BIZ_A, PHONE)
    assert sealed.startswith("v2:")
    assert PHONE not in sealed
    assert unseal_phone(BIZ_A, sealed) == PHONE
    assert seal_phone(BIZ_A, PHONE) != sealed  # random nonce
    with pytest.raises(PhoneSealError):
        unseal_phone(BIZ_B, sealed)  # another business's key cannot open it
    broken = sealed[:-3] + ("A" if sealed[-3] != "A" else "B") + sealed[-2:]
    with pytest.raises(PhoneSealError):
        unseal_phone(BIZ_A, broken)
    with pytest.raises(PhoneSealError):
        unseal_phone(BIZ_A, "v9:abc")
    with pytest.raises(ValueError, match=r"E\.164"):
        seal_phone(BIZ_A, "98123")


def test_legacy_dialer_values_stay_readable() -> None:
    legacy = _legacy_v1(PHONE)
    assert unseal_phone(BIZ_A, legacy) == PHONE
    assert sealing.unseal(legacy, BIZ_B) == PHONE  # v1 is not business-bound
    assert sealing.unseal(sealing.seal(PHONE, BIZ_A), BIZ_A) == PHONE
    assert mask_phone("5678") == "+91 ••••• •5678"


async def _contact(admin_engine: AsyncEngine, business_id: str) -> Any:
    async with admin_engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT id, phone_enc, phone_last4 FROM contact WHERE business_id = :b"),
                {"b": business_id},
            )
        ).one()


async def test_inbound_caller_number_is_stored_encrypted_and_revealed_with_a_log(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)
    assert (await start(client, t["employee"]["id"])).status_code == 201
    row = await _contact(admin_engine, t["business"]["id"])
    assert row.phone_enc.startswith("v2:")
    assert PHONE not in row.phone_enc

    detail = (await client.get(f"/v1/customers/{row.id}", headers=t["headers"])).json()
    assert detail["phone_masked"] == "+91 ••••• •5678"
    assert detail["has_phone"] is True
    assert PHONE not in str(detail)

    staff = await add_member(admin_engine, t["business"]["id"], MemberRole.STAFF)
    resp = await client.post(
        f"/v1/customers/{row.id}/phone", headers=staff.headers(t["business"]["id"])
    )
    assert resp.status_code == 403
    resp = await client.post(f"/v1/customers/{row.id}/phone", headers=t["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["phone"] == PHONE

    async with admin_engine.connect() as conn:
        log = (
            await conn.execute(text("SELECT contact_id, purpose, actor FROM phone_access_log"))
        ).all()
    assert [(r.purpose, r.actor) for r in log] == [("owner_view", f"user:{t['owner'].user_id}")]
    assert log[0].contact_id == row.id


async def test_reveal_falls_back_to_dialer_copy_and_upgrades(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    """A contact from before 0006 has no phone_enc: the dialer's v1 copy is used and upgraded."""
    configure_service()
    t = await make_tenant(client)
    await start(client, t["employee"]["id"])
    bid = t["business"]["id"]
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE contact SET phone_enc = NULL"))
        await conn.execute(
            text(
                "INSERT INTO outbound_job (business_id, employee_id, phone_hash, phone_last4,"
                " phone_enc, purpose, source) SELECT c.business_id, :e, c.phone_hash,"
                " c.phone_last4, :enc, 'service', 'test' FROM contact c"
            ),
            {"e": t["employee"]["id"], "enc": _legacy_v1(PHONE)},
        )
    row = await _contact(admin_engine, bid)
    async with tenant_session(TenantContext(business_id=uuid.UUID(bid))) as session:
        phone = await reveal_phone(
            session, uuid.UUID(bid), row.id, purpose="callback", actor="test"
        )
        await session.commit()
    assert phone == PHONE
    assert (await _contact(admin_engine, bid)).phone_enc.startswith("v2:")
    async with tenant_session(TenantContext(business_id=uuid.UUID(bid))) as session:
        with pytest.raises(ValueError, match="purpose"):
            await reveal_phone(session, uuid.UUID(bid), row.id, purpose="Bad Purpose", actor="x")
        # Another tenant's contact id reveals nothing.
        assert await reveal_phone(session, uuid.uuid4(), row.id, purpose="x", actor="x") is None


async def test_forget_erases_the_number_everywhere(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    configure()
    t = await tenant(client)
    await consent(client, t, PHONE)
    resp = await client.post(
        "/internal/v1/dialer/callbacks",
        json={
            "business_id": t["business"]["id"],
            "employee_id": t["employee"]["id"],
            "contact_phone": PHONE,
            "at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
        headers=SVC,
    )
    assert resp.status_code == 201, resp.text
    await client.post(
        "/internal/v1/calls",
        json={
            "id": str(uuid.uuid4()),
            "employee_id": t["employee"]["id"],
            "direction": "inbound",
            "started_at": "2026-11-02T05:00:00+00:00",
            "caller_phone": PHONE,
        },
        headers=SVC,
    )
    row = await _contact(admin_engine, t["business"]["id"])
    assert row.phone_enc
    resp = await client.post(f"/v1/customers/{row.id}/forget", headers=t["headers"])
    assert resp.status_code == 200, resp.text
    async with admin_engine.connect() as conn:
        jobs = (await conn.execute(text("SELECT status, phone_enc FROM outbound_job"))).all()
        contacts = (await conn.execute(text("SELECT count(*) FROM contact"))).scalar_one()
    assert contacts == 0
    assert [(j.status, j.phone_enc) for j in jobs] == [("cancelled", "")]


async def test_new_tables_are_tenant_isolated(
    client: httpx.AsyncClient, admin_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    configure_service()
    t = await make_tenant(client)
    await start(client, t["employee"]["id"])
    row = await _contact(admin_engine, t["business"]["id"])
    await client.post(f"/v1/customers/{row.id}/phone", headers=t["headers"])
    other = await make_tenant(client, "Other Shop")
    async with app_engine.connect() as conn:
        for table in ("phone_access_log", "missed_call", "caller_block"):
            await conn.execute(
                text("SELECT set_config('app.business_id', :b, false)"),
                {"b": other["business"]["id"]},
            )
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
            await conn.execute(
                text("SELECT set_config('app.business_id', :b, false)"),
                {"b": t["business"]["id"]},
            )
            mine = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert mine == (1 if table == "phone_access_log" else 0)


def test_secret_sealing_is_label_bound() -> None:
    from mitra_core.phones import seal_secret, unseal_secret

    sealed = seal_secret(BIZ_A, "rzp_secret_value", label="razorpay_key_secret")
    assert "rzp_secret_value" not in sealed
    assert unseal_secret(BIZ_A, sealed, label="razorpay_key_secret") == "rzp_secret_value"
    with pytest.raises(PhoneSealError):
        unseal_secret(BIZ_A, sealed, label="razorpay_webhook_secret")
    with pytest.raises(PhoneSealError):
        unseal_secret(BIZ_B, sealed, label="razorpay_key_secret")
