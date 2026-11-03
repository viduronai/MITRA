"""ACT-02: send_whatsapp_template promises only what the business has; core sends it later."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import httpx

from mitra_voice.brain.tools import TOOL_SPECS, ToolExecutor
from mitra_voice.brain.whatsapp_sends import booking_words
from mitra_voice.carriers.base import OutboundRegistry
from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.carriers.sim import SimCarrier
from mitra_voice.pack import Fact
from mitra_voice.transports.routing import Route
from mitra_voice.transports.telephony import TelephonyState, _after_call
from tests.test_dialer_voice import BUSINESS, EMPLOYEE, NOW, load_fixture_pack

CALL_ID = "6f1c1d6e-3333-4a2b-9c3d-000000000004"
EXTRA = [
    Fact(
        category="location",
        key="Address",
        value="Road No. 12, Banjara Hills https://maps.app.goo.gl/AbCd1234",
    ),
    Fact(category="prices", key="Price list", value="Full list: https://example.com/prices.pdf"),
]


def _executor(with_knowledge: bool = True) -> ToolExecutor:
    pack = load_fixture_pack()
    if with_knowledge:
        pack = replace(pack, facts=[*pack.facts, *EXTRA])
    return ToolExecutor(pack, clock=lambda: NOW)


def test_only_known_documents_and_locations() -> None:
    assert "document" in str(TOOL_SPECS["send_whatsapp_template"])
    tools = _executor()
    assert tools.execute("send_whatsapp_template", {"template": "location"})["ok"] is True
    doc = tools.execute(
        "send_whatsapp_template", {"template": "document", "document": "price list"}
    )
    assert doc["document"] == "Price list"
    made_up = tools.execute(
        "send_whatsapp_template", {"template": "document", "document": "brochure"}
    )
    assert made_up["status"] == "not_sent"
    assert made_up["available"] == ["Price list"]
    bare = _executor(with_knowledge=False)
    assert bare.execute("send_whatsapp_template", {"template": "location"})["status"] == "not_sent"
    report = bare.execute("send_whatsapp_template", {"template": "report_link"})
    assert report["status"] == "not_sent"
    assert "team will WhatsApp" in report["error"]


def test_booking_confirmation_needs_a_booking_on_this_call() -> None:
    tools = _executor()
    first = tools.execute("send_whatsapp_template", {"template": "booking_confirmation"})
    assert first["status"] == "not_sent"
    assert booking_words({"date": "2026-10-21", "time": "18:15"}) == "Wed 21 Oct, 6:15 pm"
    assert booking_words({"date": "bad"}) is None


async def test_accepted_messages_reach_core_after_the_call() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"status": "sent"})

    core = CoreTelephony("http://core", "tok", transport=httpx.MockTransport(handler))
    state = TelephonyState(carrier=SimCarrier(), registry=OutboundRegistry(), core=core)
    tools = _executor()
    tools.execute("send_whatsapp_template", {"template": "location"})
    tools.execute("send_whatsapp_template", {"template": "document", "document": "made-up flyer"})
    tools.execute("send_whatsapp_template", {"template": "follow_up", "topic": "MRI price"})
    session = SimpleNamespace(
        id=CALL_ID,
        pack=SimpleNamespace(business_id=BUSINESS, employee_id=EMPLOYEE),
        action_log=lambda: [
            {"name": c.name, "args": c.args, "result": c.result} for c in tools.calls
        ],
    )
    route = Route("inbound", EMPLOYEE, "clinic", "+919812345678", BUSINESS)
    await _after_call(session, route, state)  # type: ignore[arg-type]
    bodies = [b for p, b in sent if p == "/internal/v1/whatsapp/sends"]
    assert [b["kind"] for b in bodies] == ["location", "follow_up"]  # the invented one is dropped
    assert bodies[0]["client_ref"] == f"call:{CALL_ID}:wa:1"
    assert bodies[1]["topic"] == "MRI price"
    assert all("http" not in json.dumps(b) for b in bodies)  # links are core's job
