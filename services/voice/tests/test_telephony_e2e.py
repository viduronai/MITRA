"""Phone calls end to end: the carrier simulator dials a real (in-process) voice server over a
real WebSocket using Exotel's / Plivo's protocol. Mock STT/LLM/TTS (no credits) and an energy
VAD (synthetic audio is not speech to Silero); everything else is the production path."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import httpx
import numpy as np
import pytest
import uvicorn
import websockets
from fastapi import FastAPI
from pydantic import SecretStr

from mitra_voice.app import create_app
from mitra_voice.carriers.sim import SimCarrier
from mitra_voice.carriers.simulator import RATE, basic_auth, simulate_call
from mitra_voice.config import Settings
from mitra_voice.session import CallSession
from tests.fakes import EnergyVAD, wait_for


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "mock_llm_ttft_ms": 60,
        "mock_llm_token_ms": 5,
        "mock_tool_latency_ms": 0,
        "mock_tts_ttfb_ms": 20,
        "mock_tts_ms_per_char": 15,
    }
    return Settings(**(base | overrides))


def caller_speech(seconds: float = 1.0) -> bytes:
    """Loud noise-modulated tone at 8 kHz: 'speech' for the energy VAD."""
    rng = np.random.default_rng(3)
    t = np.arange(int(RATE * seconds)) / RATE
    samples = 0.3 * np.sin(2 * np.pi * 180 * t) + 0.05 * rng.standard_normal(t.size)
    return bytes((samples * 32767).astype("<i2").tobytes())


@asynccontextmanager
async def serving(settings: Settings) -> AsyncIterator[tuple[FastAPI, str]]:
    app = create_app(settings)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", ws="websockets-sansio")
    )
    task = asyncio.create_task(server.serve())
    await wait_for(lambda: server.started, within=60)
    port = server.servers[0].sockets[0].getsockname()[1]
    app.state.telephony.vad_factory = EnergyVAD
    app.state.telephony.turn = "vad"
    try:
        yield app, f"127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 30)


def _sessions(app: FastAPI) -> list[CallSession]:
    return app.state.sessions.all()  # type: ignore[no-any-return]


async def _ended(app: FastAPI) -> CallSession:
    await wait_for(lambda: bool(_sessions(app)) and _sessions(app)[-1].ended_at is not None, 15)
    return _sessions(app)[-1]


async def test_exotel_inbound_call_gets_greeting_and_answer() -> None:
    async with serving(_settings()) as (app, host):
        call = await simulate_call(
            f"ws://{host}/telephony/exotel/ws?scenario=clinic", caller_speech(), quiet_s=0.8
        )
        session = await _ended(app)
    assert call.greeting_bytes > RATE  # > 0.5 s of greeting at 8 kHz 16-bit
    assert call.reply_bytes > RATE  # and a spoken answer after the caller talked
    assert session.direction == "inbound"
    assert session.caller_phone == "+919812345678"
    roles = [t.role for t in session.transcript]
    assert roles[:3] == ["assistant", "user", "assistant"]
    assert session.transcript[1].text == "Hi, what is the consultation fee?"  # mock STT script
    assert "five hundred" in session.transcript[2].text  # answered from the clinic pack


async def test_barge_in_clears_carrier_audio() -> None:
    async with serving(_settings(mock_tts_ms_per_char=60)) as (app, host):
        call = await simulate_call(
            f"ws://{host}/telephony/exotel/ws", caller_speech(1.2), barge_in=True, quiet_s=0.8
        )
        session = await _ended(app)
    # Exotel was told to drop the queued greeting, which was cut short.
    assert call.clears >= 1
    assert session.transcript[0].role == "assistant"
    assert call.seconds(call.greeting_bytes) < 4.0
    assert any(t.role == "user" for t in session.transcript)


async def test_plivo_answer_xml_then_stream() -> None:
    async with serving(_settings()) as (app, host):
        async with httpx.AsyncClient(base_url=f"http://{host}") as client:
            res = await client.post(
                "/telephony/plivo/answer",
                data={"CallUUID": "plivo-call-1", "From": "919812345678", "To": "914041234567"},
            )
        assert res.status_code == 200
        url = res.text.split(">")[-3].split("<")[0].replace("&amp;", "&")
        assert urlparse(url).path == "/telephony/plivo/ws"
        call = await simulate_call(url, caller_speech(), protocol="plivo", quiet_s=0.8)
        session = await _ended(app)
    assert call.greeting_bytes > RATE
    assert call.reply_bytes > RATE
    assert session.caller_phone == "+919812345678"
    assert [t.role for t in session.transcript][:2] == ["assistant", "user"]


async def test_plivo_stream_without_token_is_refused() -> None:
    async with serving(_settings()) as (_, host):
        with pytest.raises(websockets.InvalidStatus):
            await simulate_call(f"ws://{host}/telephony/plivo/ws?call=x", b"", protocol="plivo")


async def test_exotel_rejects_wrong_credentials() -> None:
    settings = _settings(exotel_api_key="key", exotel_api_token=SecretStr("tok"))
    async with serving(settings) as (app, host):
        url = f"ws://{host}/telephony/exotel/ws"
        with pytest.raises(websockets.InvalidStatus):
            await simulate_call(url, b"", headers=basic_auth("key", "wrong"))
        call = await simulate_call(url, caller_speech(), headers=basic_auth("key", "tok"))
        await _ended(app)
    assert call.reply_bytes > 0


async def test_outbound_call_through_sim_carrier() -> None:
    async with serving(_settings()) as (app, host):
        sim = SimCarrier(
            answer_ws_url=f"ws://{host}/telephony/exotel/ws", answer_pcm=caller_speech()
        )
        app.state.telephony.carrier = sim
        async with httpx.AsyncClient(base_url=f"http://{host}") as client:
            res = await client.post(
                "/telephony/calls",
                json={
                    "business_id": "6f1c1d6e-1111-4a2b-9c3d-000000000001",
                    "employee_id": "6f1c1d6e-2222-4a2b-9c3d-000000000002",
                    "contact_phone": "+919812345678",
                    "purpose": "service",
                },
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["decision"] == "allow"
        assert body["carrier"] == "sim"
        await wait_for(lambda: bool(sim.answered), within=30)
        session = await _ended(app)
    assert session.direction == "outbound"
    assert session.caller_phone == "+919812345678"
    assert sim.answered[0].call_sid == body["call_sid"]
    assert sim.answered[0].reply_bytes > 0
