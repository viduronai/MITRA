"""Call reporting to services/core: payloads, ordering, retries, and clean disabling."""

from __future__ import annotations

import dataclasses
import json
import uuid
from typing import Any

import httpx
from pydantic import SecretStr

from mitra_voice.config import Settings
from mitra_voice.core_client import CoreCallReporter, end_payload
from mitra_voice.pack import FIXTURES_DIR, SCENARIO_FIXTURES, load_fixture
from mitra_voice.providers import ResolvedProviders
from mitra_voice.session import CallSession

EMPLOYEE_ID = str(uuid.uuid4())
PROVIDERS = ResolvedProviders(stt="mock", llm="mock", tts="mock")


def _pack(employee_id: str = EMPLOYEE_ID) -> Any:
    pack = load_fixture(FIXTURES_DIR / SCENARIO_FIXTURES["clinic"])
    return dataclasses.replace(pack, employee_id=employee_id)


class FakeCore:
    """Records requests; ``fail`` = number of 503s to return before succeeding."""

    def __init__(self, fail: int = 0, status: int = 200) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok"
        self.requests.append((request.url.path, json.loads(request.content)))
        if self.fail > 0:
            self.fail -= 1
            return httpx.Response(503)
        return httpx.Response(self.status, json={})


def _reporter(core: FakeCore) -> CoreCallReporter:
    return CoreCallReporter(
        "http://core.test/", "tok", transport=httpx.MockTransport(core), backoff_s=0
    )


def _session(reporter: CoreCallReporter | None, **kw: Any) -> CallSession:
    return CallSession(
        scenario="clinic", pack=_pack(), providers=PROVIDERS, reporter=reporter, **kw
    )


async def test_reports_start_then_end_with_transcript_and_actions() -> None:
    core = FakeCore()
    reporter = _reporter(core)
    session = _session(reporter, direction="inbound", caller_phone="+919812345678")
    session.action_log = lambda: [
        {"name": "book_slot", "args": {"date": "2026-10-21"}, "result": {"status": "booked"}},
        {"name": "Not Valid!", "args": {}, "result": {}},
    ]
    session.add_assistant("Namaskaram, Sunrise Clinic.")
    session.add_user("Appointment kavali")
    session.end()
    session.end()  # a second end() never reports twice
    await reporter.drain()

    paths = [p for p, _ in core.requests]
    call_id = str(uuid.UUID(session.id))
    assert paths == ["/internal/v1/calls", f"/internal/v1/calls/{call_id}/end"]
    start, end = core.requests[0][1], core.requests[1][1]
    assert start["id"] == call_id
    assert start["employee_id"] == EMPLOYEE_ID
    assert start["direction"] == "inbound"
    assert start["caller_phone"] == "+919812345678"
    assert end["employee_id"] == EMPLOYEE_ID
    assert [t["role"] for t in end["transcript"]] == ["assistant", "user"]
    assert [a["name"] for a in end["actions"]] == ["book_slot"]
    assert end["latency_stats"]["turns"] == 0
    assert "stt_seconds" in end["usage"]
    await reporter.aclose()


async def test_retries_transient_failures() -> None:
    core = FakeCore(fail=2)
    reporter = _reporter(core)
    session = _session(reporter)
    session.end()
    await reporter.drain()
    assert [p.rsplit("/", 1)[-1] for p, _ in core.requests] == ["calls", "calls", "calls", "end"]
    await reporter.aclose()


async def test_gives_up_on_client_errors_without_end_report() -> None:
    core = FakeCore(status=404)
    reporter = _reporter(core)
    session = _session(reporter)
    session.end()
    await reporter.drain()
    # Start failed (not retryable), retried once before the end report, then nothing more.
    assert [p for p, _ in core.requests] == ["/internal/v1/calls", "/internal/v1/calls"]
    await reporter.aclose()


async def test_unreachable_core_never_raises() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    reporter = CoreCallReporter(
        "http://core.test", "tok", transport=httpx.MockTransport(boom), backoff_s=0, attempts=2
    )
    session = _session(reporter)
    session.end()
    await reporter.drain()
    await reporter.aclose()


async def test_fixture_packs_are_not_reported() -> None:
    core = FakeCore()
    reporter = _reporter(core)
    session = CallSession(
        scenario="clinic",
        pack=_pack("fixture-priya"),
        providers=PROVIDERS,
        reporter=reporter,
    )
    session.end()
    await reporter.drain()
    assert core.requests == []
    await reporter.aclose()


def test_disabled_without_core_settings() -> None:
    assert CoreCallReporter.from_settings(Settings()) is None
    assert CoreCallReporter.from_settings(Settings(mitra_core_url="http://x")) is None
    reporter = CoreCallReporter.from_settings(
        Settings(mitra_core_url="http://x", mitra_core_service_token=SecretStr("t"))
    )
    assert reporter is not None
    # No event loop: building a session must not fail.
    _session(reporter).end()


def test_end_payload_trims_to_core_limits() -> None:
    session = _session(None)
    for i in range(450):
        session.add_user(f"turn {i} " + "x" * 5_000)
    session.action_log = lambda: [{"name": "record_field", "args": {"v": "y" * 9_000}}]
    body = end_payload(session)
    assert len(body["transcript"]) == 400
    assert all(len(t["text"]) <= 4_000 for t in body["transcript"])
    assert body["actions"][0]["args"] == {"truncated": True}
