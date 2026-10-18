from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

import httpx
import pytest

from mitra_evals.agents import AgentUnavailableError, CallContext, build_agent
from mitra_evals.agents.base import AgentReply
from mitra_evals.agents.core_sim import _ScriptSession
from mitra_evals.agents.voice_text import _HttpSession, voice_text_agent
from mitra_evals.schema import EmployeePack

CTX = CallContext(scenario_id="t", language="te-en")


def _converse(agent_name: str, pack: EmployeePack, *lines: str) -> list[AgentReply]:
    async def go() -> list[AgentReply]:
        session = await build_agent(agent_name, {}).open(pack, CTX)
        replies = [await session.start()]
        replies += [await session.send(line) for line in lines]
        await session.close()
        return replies

    return asyncio.run(go())


def test_scripted_greets_in_base_language_and_answers(clinic: EmployeePack) -> None:
    greeting, fee, emergency = _converse("scripted", clinic, "Doctor fees ఎంత?", "ఛాతీ నొప్పి వస్తుంది")
    assert greeting.text == clinic.greeting.inbound["te"]
    assert "500" in fee.text
    assert {a.name for a in emergency.actions} == {"transfer_to_human", "alert_staff"}


def test_scripted_defers_unknowns(clinic: EmployeePack) -> None:
    _, reply = _converse("scripted", clinic, "Do you accept insurance?")
    assert [a.name for a in reply.actions] == ["schedule_callback"]


def test_core_sim_script_session_matches_questions() -> None:
    script = [
        {"speaker": "employee", "text": "Hello, AI assistant."},
        {"speaker": "caller", "text": "What is the consultation fee?"},
        {"speaker": "employee", "text": "The fee is ₹500."},
        {"speaker": "caller", "text": "And what are your timings?"},
        {"speaker": "employee", "text": "9 AM to 9 PM."},
        {"speaker": "employee", "text": "Thank you for calling!"},
    ]

    async def go() -> list[str]:
        session = _ScriptSession(script)
        out = [(await session.start()).text]
        for line in ("Your timings please?", "ఫీజు ఎంత?", "anything else?"):
            out.append((await session.send(line)).text)
        return out

    assert asyncio.run(go()) == [
        "Hello, AI assistant.",
        "9 AM to 9 PM.",
        "The fee is ₹500.",
        "Thank you for calling!",
    ]


@pytest.mark.skipif(
    importlib.util.find_spec("mitra_core") is None, reason="mitra_core not installed"
)
def test_core_sim_in_process(clinic: EmployeePack) -> None:
    agent = build_agent("core-sim", {})
    assert getattr(agent, "mode", None) == "in-process"
    replies = _converse("core-sim", clinic, "What is the consultation fee?")
    assert replies[0].text == clinic.greeting.inbound["te"]
    assert "500" in replies[1].text


def test_voice_text_unavailable_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MITRA_VOICE_TEXT_URL", raising=False)
    monkeypatch.delenv("MITRA_VOICE_TEXT_ENTRYPOINT", raising=False)
    with pytest.raises(AgentUnavailableError, match="voice-text needs"):
        voice_text_agent()


def test_voice_text_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MITRA_VOICE_TEXT_ENTRYPOINT", "mitra_evals.agents.scripted:ScriptedAgent")
    assert voice_text_agent().name == "scripted"
    monkeypatch.setenv("MITRA_VOICE_TEXT_ENTRYPOINT", "no.such.module:factory")
    with pytest.raises(AgentUnavailableError, match="cannot load"):
        voice_text_agent()


def test_voice_text_http_contract(clinic: EmployeePack) -> None:
    seen: list[tuple[str, str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "POST" and request.url.path == "/v1/text-sessions":
            return httpx.Response(201, json={"session_id": "s1", "reply": {"text": "Hi, AI here."}})
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "text": "Booked.",
                    "actions": [{"name": "book_slot", "args": {"time": "11:00"}}],
                    "timings": {"first_audio_ms": 640},
                },
            )
        return httpx.Response(204)

    async def go() -> list[AgentReply]:
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://voice")
        session = _HttpSession(http, clinic, CTX)
        replies = [await session.start(), await session.send("book 11", interrupt=True)]
        await session.close()
        return replies

    greeting, booked = asyncio.run(go())
    assert greeting.text == "Hi, AI here."
    assert booked.actions[0].name == "book_slot"
    assert booked.actions[0].args == {"time": "11:00"}
    assert booked.timings.first_audio_ms == 640
    create, turn, delete = seen
    assert create[2]["pack"]["id"] == "sunrise_clinic"
    assert create[2]["context"]["language"] == "te-en"
    assert turn == ("POST", "/v1/text-sessions/s1/turns", {"text": "book 11", "interrupt": True})
    assert delete[:2] == ("DELETE", "/v1/text-sessions/s1")


def test_unknown_agent() -> None:
    with pytest.raises(ValueError, match="unknown agent"):
        build_agent("nope", {})
