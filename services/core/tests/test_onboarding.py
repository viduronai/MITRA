from __future__ import annotations

from typing import Any

import httpx

from tests.helpers import FakeClock, add_fact, create_business, create_employee, new_actor


async def _progress(client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = await client.get("/v1/onboarding/progress", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


def _done(progress: dict[str, Any]) -> dict[str, bool]:
    return {s["key"]: s["done"] for s in progress["steps"]}


async def test_progress_follows_the_data(client: httpx.AsyncClient, clock: FakeClock) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    headers = owner.headers(business["id"])

    progress = await _progress(client, headers)
    assert list(_done(progress)) == ["business", "role", "teach", "voice", "test_call", "go_live"]
    assert _done(progress)["business"] is True
    assert (progress["percent"], progress["next"]) == (17, "role")

    employee = await create_employee(client, owner, business["id"])
    assert (await _progress(client, headers))["next"] == "teach"

    for key in ("Consultation fee", "Timings"):
        await add_fact(client, headers, "faq", key, "x")
    assert (await _progress(client, headers))["next"] == "teach"  # needs 3 confirmed
    third = await add_fact(client, headers, "faq", "Parking", "Free")
    assert (await _progress(client, headers))["next"] == "voice"
    fact_url = f"/v1/knowledge/facts/{third['id']}"
    await client.patch(fact_url, json={"status": "suggested"}, headers=headers)
    assert (await _progress(client, headers))["next"] == "teach"
    await client.patch(fact_url, json={"status": "confirmed"}, headers=headers)

    await client.patch(
        f"/v1/employees/{employee['id']}", json={"voice_id": "priya-te-hyd"}, headers=headers
    )
    assert (await _progress(client, headers))["next"] == "test_call"

    await client.post("/v1/test-calls", json={"employee_id": employee["id"]}, headers=headers)
    clock.advance(3)
    assert (await _progress(client, headers))["next"] == "test_call"  # still ringing
    clock.advance(4)
    progress = await _progress(client, headers)
    assert (progress["percent"], progress["next"]) == (83, "go_live")
    assert _done(progress)["go_live"] is False


async def test_progress_requires_business_and_is_isolated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/onboarding/progress", headers=new_actor().headers())
    assert resp.status_code == 403
    a, b = new_actor(), new_actor()
    biz_a = await create_business(client, a)
    biz_b = await create_business(client, b)
    await create_employee(client, a, biz_a["id"])
    assert (await _progress(client, b.headers(biz_b["id"])))["next"] == "role"
