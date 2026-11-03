"""Missed-call numbers (CALL-20): the call is never answered and core is told to call back."""

from __future__ import annotations

from typing import Any

import httpx

from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.carriers.simulator import simulate_missed_call
from mitra_voice.transports.missed_call import reject_if_missed_call
from tests.test_telephony_e2e import _sessions, _settings, serving

MISSED_NUMBER = "+914041230000"
NORMAL_NUMBER = "+914041239999"
CALLER = "+919812345678"


def _fake_core(seen: list[tuple[str, dict[str, Any]]]) -> CoreTelephony:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/resolve"):
            to = req.url.params["to"]
            seen.append(("resolve", {"to": to}))
            return httpx.Response(
                200,
                json={
                    "business_id": "b1",
                    "business_name": "Sunrise Clinic",
                    "employee_id": "e1",
                    "phone_number_id": "n1",
                    "caller_known": False,
                    "missed_call": to == MISSED_NUMBER,
                },
            )
        if req.url.path.endswith("/missed-calls"):
            import json

            seen.append(("missed", json.loads(req.content)))
            return httpx.Response(200, json={"status": "queued"})
        return httpx.Response(404, json={})

    return CoreTelephony("http://core", "tok", transport=httpx.MockTransport(handler))


async def test_reject_only_missed_call_numbers() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []
    core = _fake_core(seen)
    assert await reject_if_missed_call(core, MISSED_NUMBER, CALLER, "sid1") is True
    assert await reject_if_missed_call(core, NORMAL_NUMBER, CALLER, "sid2") is False
    assert await reject_if_missed_call(None, MISSED_NUMBER, CALLER, "sid3") is False
    assert seen[1] == (
        "missed",
        {"to": MISSED_NUMBER, "from": CALLER, "carrier_call_sid": "sid1"},
    )
    assert [kind for kind, _ in seen] == ["resolve", "missed", "resolve"]


async def test_plivo_rejects_before_answer_and_exotel_passthru_reports() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []
    async with serving(_settings()) as (app, host):
        app.state.telephony.core = _fake_core(seen)
        base = f"http://{host}"
        assert (
            await simulate_missed_call(base, from_=CALLER, to=MISSED_NUMBER, carrier="plivo") == 200
        )
        # A normal number still gets the stream XML (not rejected).
        assert (
            await simulate_missed_call(base, from_=CALLER, to=NORMAL_NUMBER, carrier="plivo") == 409
        )
        assert await simulate_missed_call(base, from_="09812345678", to=MISSED_NUMBER) == 200
        assert _sessions(app) == []  # nothing was ever answered
    missed = [body for kind, body in seen if kind == "missed"]
    assert [(m["to"], m["from"]) for m in missed] == [(MISSED_NUMBER, CALLER)] * 2
    assert all(m["carrier_call_sid"].startswith("SIMMISS") for m in missed)
