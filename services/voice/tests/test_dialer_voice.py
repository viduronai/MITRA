"""Core's dialer path in the voice service: pre-cleared calls with script variables (CALL-15)
and callbacks requested during a call (CALL-05)."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import httpx

from mitra_voice.brain.tools import IST, ToolExecutor
from mitra_voice.callbacks import call_brief, fill, fmt_when, resolve_callback_time
from mitra_voice.carriers.base import OutboundIntent, OutboundRegistry
from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.carriers.sim import SimCarrier
from mitra_voice.pack import FIXTURES_DIR, SCENARIO_FIXTURES, load_fixture
from mitra_voice.transports.routing import Route
from mitra_voice.transports.telephony import TelephonyState, _after_call
from tests.fakes import wait_for
from tests.test_telephony_e2e import _ended, _settings, caller_speech, serving

NOW = datetime(2026, 11, 2, 10, 30, tzinfo=IST)  # Monday
BUSINESS = "6f1c1d6e-1111-4a2b-9c3d-000000000001"
EMPLOYEE = "6f1c1d6e-2222-4a2b-9c3d-000000000002"


def test_resolve_callback_time() -> None:
    def at(**args: str) -> str:
        return resolve_callback_time(args, NOW).strftime("%a %H:%M")

    assert at(when="tomorrow 5 pm") == "Tue 17:00"
    assert at(when="kal shaam") == "Tue 18:00"
    assert at(when="in 2 hours") == "Mon 12:30"
    assert at(when="9 am") == "Tue 09:00"  # already past today
    assert at(when="friday morning") == "Fri 10:00"
    assert at(when_iso="2026-11-04T15:00") == "Wed 15:00"
    assert at(when_iso="2026-01-01T15:00") == "Mon 10:35"  # never in the past
    assert at(when="whenever") == "Mon 12:30"
    assert fmt_when(resolve_callback_time({"when": "tomorrow 5 pm"}, NOW)) == "Tue 3 Nov, 5 pm"


def test_brief_and_fill() -> None:
    brief = call_brief("service", {"lead_name": "Ravi", "interest": "2BHK"})
    assert brief is not None
    assert "You are calling Ravi." in brief
    assert "interest: 2BHK" in brief
    assert call_brief("service", {}) is None
    assert "called back" in (call_brief("callback", {}) or "")
    assert fill("Hello {lead_name}, this is Meera.", {"lead_name": "Ravi"}) == (
        "Hello Ravi, this is Meera."
    )
    assert fill("Hello {lead_name}, hi {unknown}.", {}) == "Hello, hi."


def test_schedule_callback_tool_confirms_time() -> None:
    pack = load_fixture_pack()
    executor = ToolExecutor(pack, clock=lambda: NOW)
    result = executor.execute("schedule_callback", {"topic": "price", "when": "tomorrow 5 pm"})
    assert result == {"status": "scheduled", "when": "Tue 3 Nov, 5 pm", "channel": "call"}
    assert executor.execute("schedule_callback", {"topic": "x"})["by"] == "the team, today"


def load_fixture_pack() -> Any:
    return load_fixture(FIXTURES_DIR / SCENARIO_FIXTURES["clinic"])


async def test_dialer_call_carries_variables() -> None:
    async with serving(_settings()) as (app, host):
        sim = SimCarrier(
            answer_ws_url=f"ws://{host}/telephony/exotel/ws", answer_pcm=caller_speech()
        )
        app.state.telephony.carrier = sim
        async with httpx.AsyncClient(base_url=f"http://{host}") as client:
            res = await client.post(
                "/telephony/dialer/calls",
                json={
                    "job_id": "6f1c1d6e-3333-4a2b-9c3d-000000000003",
                    "business_id": BUSINESS,
                    "employee_id": EMPLOYEE,
                    "contact_phone": "+919812345678",
                    "purpose": "service",
                    "caller_id": "+914041234567",
                    "phone_number_id": "6f1c1d6e-4444-4a2b-9c3d-000000000004",
                    "attempt_id": "6f1c1d6e-5555-4a2b-9c3d-000000000005",
                    "variables": {"lead_name": "Ravi", "interest": "2BHK"},
                },
            )
        assert res.status_code == 200, res.text
        assert res.json()["carrier"] == "sim"
        await wait_for(lambda: bool(sim.answered), within=30)
        session = await _ended(app)
    assert session.direction == "outbound"
    assert session.call.call_brief is not None
    assert "Ravi" in session.call.call_brief
    _, intent = sim.placed[0]
    assert intent.attempt_id == "6f1c1d6e-5555-4a2b-9c3d-000000000005"


async def test_callback_request_reaches_core() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"job_id": "j1", "id": "x"})

    core = CoreTelephony("http://core", "tok", transport=httpx.MockTransport(handler))
    state = TelephonyState(carrier=SimCarrier(), registry=OutboundRegistry(), core=core)
    session = SimpleNamespace(
        id="s1",
        pack=SimpleNamespace(business_id=BUSINESS, employee_id=EMPLOYEE),
        action_log=lambda: [
            {"name": "schedule_callback", "args": {"topic": "price", "when": "tomorrow 5 pm"}}
        ],
    )
    intent = OutboundIntent(
        business_id=BUSINESS,
        employee_id=EMPLOYEE,
        contact_phone="+919812345678",
        caller_id="+914041234567",
        purpose="service",
        phone_number_id="num-1",
    )
    route = Route("outbound", EMPLOYEE, "clinic", "+919812345678", BUSINESS, intent=intent)
    await _after_call(session, route, state)  # type: ignore[arg-type]
    [(path, body)] = sent
    assert path == "/internal/v1/dialer/callbacks"
    assert body["contact_phone"] == "+919812345678"
    assert body["note"] == "price"
    assert body["called_number_id"] == "num-1"
    assert datetime.fromisoformat(body["at"]) > datetime.now(IST)

    sent.clear()
    session.action_log = lambda: [
        {"name": "opt_out", "args": {}},
        {"name": "schedule_callback", "args": {"when": "tomorrow"}},
    ]
    await _after_call(session, route, state)  # type: ignore[arg-type]
    assert [p for p, _ in sent] == ["/internal/v1/telephony/opt-outs"]
    await core.aclose()
