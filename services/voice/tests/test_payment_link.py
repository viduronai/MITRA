"""ACT-05: the send_payment_link tool only accepts grounded amounts; core gets it after the call."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx

from mitra_voice.brain.tools import TOOL_SPECS, ToolExecutor
from mitra_voice.carriers.base import OutboundRegistry
from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.carriers.sim import SimCarrier
from mitra_voice.transports.routing import Route
from mitra_voice.transports.telephony import TelephonyState, _after_call
from tests.test_dialer_voice import BUSINESS, EMPLOYEE, NOW, load_fixture_pack

CALL_ID = "6f1c1d6e-3333-4a2b-9c3d-000000000003"


def _executor() -> ToolExecutor:
    return ToolExecutor(load_fixture_pack(), clock=lambda: NOW)


def test_amount_must_come_from_the_facts() -> None:
    assert "send_payment_link" in TOOL_SPECS
    tools = _executor()
    ok = tools.execute("send_payment_link", {"amount_rupees": 500, "purpose": "consultation"})
    assert ok["ok"] is True
    assert ok["amount_paise"] == 50_000
    assert ok["needs_owner_ok"] is False
    made_up = tools.execute("send_payment_link", {"amount_rupees": 450, "purpose": "consult"})
    assert made_up["status"] == "not_sent"
    assert "not in the business facts" in made_up["error"]
    assert tools.execute("send_payment_link", {"amount_rupees": "abc", "purpose": "x"})["error"]


def test_brief_grounds_a_reminder_amount_and_discount_needs_ok() -> None:
    tools = _executor()
    tools.grounding.append("From the calling list: payment amount: ₹2,000; payment purpose: MRI.")
    out = tools.execute(
        "send_payment_link", {"amount_rupees": 2000, "purpose": "MRI", "discount_percent": 10}
    )
    assert out["amount_paise"] == 180_000
    assert out["needs_owner_ok"] is True
    tools.execute("send_payment_link", {"amount_rupees": 500, "purpose": "fee"})
    third = tools.execute("send_payment_link", {"amount_rupees": 500, "purpose": "fee"})
    assert third["status"] == "not_sent"  # at most two links per call


async def test_accepted_links_reach_core_after_the_call() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"status": "sent", "payment_request_id": "p1"})

    core = CoreTelephony("http://core", "tok", transport=httpx.MockTransport(handler))
    state = TelephonyState(carrier=SimCarrier(), registry=OutboundRegistry(), core=core)
    tools = _executor()
    tools.execute("send_payment_link", {"amount_rupees": 500, "purpose": "consultation fee"})
    tools.execute("send_payment_link", {"amount_rupees": 999, "purpose": "invented"})
    session = SimpleNamespace(
        id=CALL_ID,
        pack=SimpleNamespace(business_id=BUSINESS, employee_id=EMPLOYEE),
        action_log=lambda: (
            [{"name": c.name, "args": c.args, "result": c.result} for c in tools.calls]
            + [{"name": "opt_out", "args": {}}]
        ),
    )
    route = Route("inbound", EMPLOYEE, "clinic", "+919812345678", BUSINESS)
    await _after_call(session, route, state)  # type: ignore[arg-type]
    paths = [p for p, _ in sent]
    assert paths == ["/internal/v1/payments/links", "/internal/v1/telephony/opt-outs"]
    body = sent[0][1]
    assert body["amount_paise"] == 50_000
    assert body["contact_phone"] == "+919812345678"
    assert body["call_id"] == CALL_ID
    assert body["client_ref"] == f"call:{CALL_ID}:1"
    await core.aclose()
