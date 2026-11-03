"""Shared setup for dialer / campaign tests: a business with a live number, consent, a worker."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from mitra_core.api.internal_dialer import get_voice_dialer
from mitra_core.config import Settings, get_settings
from mitra_core.dialer.settings import DialerSettings, get_dialer_settings
from mitra_core.dialer.voice import Placed, PlaceRequest, SimVoiceDialer
from mitra_core.main import app
from mitra_core.telephony.dnd import MockDndProvider, get_dnd_provider
from tests.helpers import FakeClock, bearer, create_business, create_employee, new_actor

TOKEN = "test-service-token-0123456789abcdef"
SVC = bearer(TOKEN)
# Monday 2 Nov 2026, 10:30 IST: inside service calling hours on a default calling day.
MONDAY_MORNING = datetime(2026, 11, 2, 5, 0, tzinfo=UTC)


@dataclass
class PendingDialer:
    """Places calls whose outcome arrives later (like the real voice service)."""

    placed: list[PlaceRequest] = field(default_factory=list)

    async def place(self, req: PlaceRequest) -> Placed:
        self.placed.append(req)
        return Placed(call_sid=f"PEND{len(self.placed)}")


def configure(
    voice: Any | None = None, **dialer: Any
) -> tuple[SimVoiceDialer | Any, DialerSettings]:
    settings = Settings(service_token=SecretStr(TOKEN))
    dialer_settings = DialerSettings(**dialer)
    voice = voice if voice is not None else SimVoiceDialer()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_dialer_settings] = lambda: dialer_settings
    app.dependency_overrides[get_voice_dialer] = lambda: voice
    app.dependency_overrides[get_dnd_provider] = lambda: MockDndProvider()
    return voice, dialer_settings


def morning_clock(clock: FakeClock) -> FakeClock:
    clock.now = MONDAY_MORNING
    return clock


async def tenant(client: httpx.AsyncClient, *, number: bool = True) -> dict[str, Any]:
    owner = new_actor()
    business = await create_business(client, owner, name=f"Biz {uuid.uuid4().hex[:6]}")
    employee = await create_employee(
        client, owner, business["id"], role_template="lead_caller", name="Meera"
    )
    headers = owner.headers(business["id"])
    t = {"owner": owner, "headers": headers, "business": business, "employee": employee}
    if number:
        resp = await client.post(
            "/v1/phone-numbers/requests",
            json={"city": "Hyderabad", "employee_id": employee["id"]},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        e164 = "+9140" + str(uuid.uuid4().int)[:8]
        resp = await client.patch(
            f"/internal/v1/telephony/numbers/{resp.json()['id']}",
            json={"business_id": business["id"], "e164": e164, "kyc_status": "approved"},
            headers=SVC,
        )
        assert resp.status_code == 200, resp.text
        t["number_id"] = resp.json()["id"]
    return t


async def consent(client: httpx.AsyncClient, t: dict[str, Any], *phones: str) -> None:
    for phone in phones:
        resp = await client.post(
            "/internal/v1/telephony/consents",
            json={
                "business_id": t["business"]["id"],
                "contact_phone": phone,
                "scope": "service",
                "source": "lead_form",
            },
            headers=SVC,
        )
        assert resp.status_code == 201, resp.text


async def opt_out(client: httpx.AsyncClient, t: dict[str, Any], *phones: str) -> None:
    for phone in phones:
        resp = await client.post(
            "/internal/v1/telephony/opt-outs",
            json={"business_id": t["business"]["id"], "contact_phone": phone, "source": "owner"},
            headers=SVC,
        )
        assert resp.status_code == 201, resp.text


async def tick(client: httpx.AsyncClient) -> dict[str, Any]:
    resp = await client.post("/internal/v1/dialer/tick", headers=SVC)
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]
