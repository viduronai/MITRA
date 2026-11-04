"""HTTP surface of the voice engine (port 8200).

- ``GET /``                       browser test page (mic -> WebRTC -> pipeline)
- ``POST /api/offer``             WebRTC offer -> answer; starts a call session
- ``PATCH /api/offer``            trickle ICE candidates
- ``GET /sessions``               recent sessions
- ``GET /sessions/{id}/metrics``  per-turn latencies + p50/p95 summary
- ``/v1/text-sessions`` (POST), ``.../{id}/turns`` (POST), ``.../{id}`` (DELETE): text-mode
  sessions for mitra-evals
- ``/telephony/*``: carrier media streams + outbound calls (transports/telephony.py)
- ``GET /health``
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
import threading
import time
import traceback
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner
from pydantic import BaseModel, Field

from mitra_voice.config import Settings, get_settings
from mitra_voice.core_client import CoreCallReporter
from mitra_voice.logging import configure_logging
from mitra_voice.pack import Scenario, load_pack
from mitra_voice.pipeline import build_call_pipeline, greet, make_turn_analyzers
from mitra_voice.providers import ResolvedProviders, resolve_providers
from mitra_voice.session import CallSession, SessionRegistry
from mitra_voice.text_sessions import TextSessionIn, TextSessionStore, TurnIn
from mitra_voice.transports.telephony import telephony_router
from mitra_voice.voices import voice_registry
from mitra_voice.warmup import warm_up

log = structlog.get_logger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


class OfferIn(BaseModel):
    sdp: str = Field(min_length=1, max_length=50_000)
    type: Literal["offer"]
    pc_id: str | None = Field(default=None, max_length=200)
    restart_pc: bool | None = None
    scenario: Scenario = "clinic"
    voice_id: str | None = Field(default=None, max_length=64)
    # A real employee from services/core (needs MITRA_CORE_URL + MITRA_CORE_SERVICE_TOKEN).
    employee_id: uuid.UUID | None = None


class CandidateIn(BaseModel):
    candidate: str = Field(max_length=2_000)
    sdp_mid: str
    sdp_mline_index: int


class PatchIn(BaseModel):
    pc_id: str = Field(max_length=200)
    candidates: list[CandidateIn] = Field(max_length=50)


LOOP_SAMPLE_S = 0.25
LOOP_LAG_WARN_MS = 100.0


def start_loop_watchdog(loop: asyncio.AbstractEventLoop, stall_s: float = 1.0) -> None:
    """Debug aid (MITRA_LOOP_WATCHDOG=1): log the event-loop thread's stack when it stalls."""
    loop_thread = threading.get_ident()
    beat = [time.monotonic()]

    def tick() -> None:
        beat[0] = time.monotonic()
        loop.call_later(0.1, tick)

    def watch() -> None:
        reported = 0.0
        while True:
            time.sleep(0.2)
            stalled = time.monotonic() - beat[0]
            if stalled > stall_s and beat[0] != reported:
                reported = beat[0]
                frame = sys._current_frames().get(loop_thread)
                stack = "".join(traceback.format_stack(frame)[-12:]) if frame else "?"
                log.warning("loop.stalled", stalled_s=round(stalled, 1), stack=stack)

    loop.call_soon_threadsafe(tick)
    threading.Thread(target=watch, name="loop-watchdog", daemon=True).start()


async def monitor_loop_lag(state: Any) -> None:
    """Event-loop lag: every call shares this loop, so a blocked loop delays all audio."""
    loop = asyncio.get_running_loop()
    while True:
        expected = loop.time() + LOOP_SAMPLE_S
        await asyncio.sleep(LOOP_SAMPLE_S)
        lag_ms = (loop.time() - expected) * 1000
        state.loop_lag_max_ms = max(state.loop_lag_max_ms, lag_ms)
        if lag_ms > LOOP_LAG_WARN_MS:
            log.warning("loop.lag", lag_ms=round(lag_ms))


async def run_call(
    connection: SmallWebRTCConnection, session: CallSession, settings: Settings
) -> None:
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )

    def send(message: dict[str, Any]) -> None:
        try:
            connection.send_app_message(message)
        except Exception:  # a closed data channel must never break the call
            log.debug("session.send_failed", session_id=session.id)

    session.send = send
    # Model loads block for 100s of ms: never on the event loop that carries every call's audio.
    analyzers = await asyncio.to_thread(make_turn_analyzers, settings)
    call = build_call_pipeline(
        session,
        settings,
        transport_input=transport.input(),
        transport_output=transport.output(),
        analyzers=analyzers,
    )

    @transport.event_handler("on_client_connected")
    async def _on_connected(_: SmallWebRTCTransport, __: SmallWebRTCConnection) -> None:
        log.info("session.connected", session_id=session.id, scenario=session.scenario)
        await greet(call, session)

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_: SmallWebRTCTransport, __: SmallWebRTCConnection) -> None:
        await call.worker.cancel(reason="client disconnected")

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(call.worker)
    try:
        await runner.run()
    finally:
        session.end()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.pipecat_log_level)
        providers = resolve_providers(settings)  # raises outside local if a key is missing
        for message in providers.messages:
            print(f"[mitra-voice] {message}", file=sys.stderr)
            log.warning("providers.fallback_to_mock", detail=message)
        log.info(
            "voice.started",
            env=settings.mitra_env,
            stt=providers.stt,
            llm=providers.llm,
            tts=providers.tts,
            port=settings.port,
        )
        app.state.providers = providers
        registry = voice_registry(settings)
        for reason in registry.refused:
            print(f"[mitra-voice] team voice refused: {reason}", file=sys.stderr)
        log.info("voices.loaded", team=len(registry.team), refused=len(registry.refused))
        await asyncio.to_thread(warm_up, providers, settings)
        # STUN lets a server behind NAT offer its public address (none needed on localhost).
        # TODO(deploy): TURN for callers behind strict firewalls.
        app.state.webrtc = SmallWebRTCRequestHandler(
            ice_servers=[IceServer(urls=url) for url in settings.mitra_webrtc_ice_servers]
        )
        app.state.sessions = SessionRegistry()
        app.state.text_sessions = TextSessionStore(settings=settings)
        app.state.tasks = set()
        app.state.core_reporter = CoreCallReporter.from_settings(settings)
        app.state.loop_lag_max_ms = 0.0
        lag_task = asyncio.create_task(monitor_loop_lag(app.state))
        if settings.mitra_loop_watchdog:
            start_loop_watchdog(asyncio.get_running_loop())
        yield
        lag_task.cancel()
        for task in list(app.state.tasks):
            task.cancel()
        await app.state.webrtc.close()
        if app.state.core_reporter is not None:
            await app.state.core_reporter.aclose()

    app = FastAPI(title="Mitra Voice", version="0.1.0", lifespan=lifespan)
    # Phone calls (Exotel / Plivo media streams, outbound): transports/telephony.py.
    app.include_router(telephony_router(settings))

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/voices")
    async def voices(request: Request) -> dict[str, Any]:
        p: ResolvedProviders = request.app.state.providers
        registry = voice_registry(settings)
        replaced = registry.replacements
        return {
            "tts": p.tts,
            # Team voices are Sarvam clones: they only sound like the person with MITRA_TTS=sarvam.
            "voices": [
                {
                    "id": v.id,
                    "name": v.name,
                    "kind": v.kind,
                    "gender": v.gender,
                    "languages": list(v.languages),
                    "persona": v.persona,
                    "speaker": v.sarvam_speaker if p.tts == "sarvam" else None,
                    "replaces": v.replaces,
                    "replaced_by": replaced[v.id].id if v.id in replaced else None,
                    # Consent reference only (who/when), never contact details or evidence paths.
                    "consent": (
                        {"person": v.consent.person, "date": v.consent.date.isoformat()}
                        if v.consent
                        else None
                    ),
                }
                for v in registry.all()
            ],
            "refused": len(registry.refused),
        }

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        p: ResolvedProviders = request.app.state.providers
        return {
            "status": "ok",
            "providers": {"stt": p.stt, "llm": p.llm, "tts": p.tts},
            "loop_lag_max_ms": round(request.app.state.loop_lag_max_ms),
        }

    @app.post("/api/offer")
    async def offer(body: OfferIn, request: Request) -> dict[str, Any]:
        state = request.app.state
        webrtc_request = SmallWebRTCRequest(
            sdp=body.sdp, type=body.type, pc_id=body.pc_id, restart_pc=body.restart_pc
        )
        if body.pc_id:  # renegotiation of an existing call
            answer = await state.webrtc.handle_web_request(webrtc_request, _no_new_call)
            return dict(answer or {})

        employee_id = str(body.employee_id) if body.employee_id else None
        pack = await load_pack(settings, body.scenario, employee_id)
        if body.voice_id:
            voice = voice_registry(settings).get(body.voice_id)
            if voice is None:
                raise HTTPException(status_code=422, detail="unknown voice_id")
            pack = dataclasses.replace(pack, voice_id=voice.id, voice_gender=voice.gender)
        session = CallSession(
            scenario=body.scenario,
            pack=pack,
            providers=state.providers,
            reporter=state.core_reporter,
        )
        state.sessions.add(session)

        async def on_connection(connection: SmallWebRTCConnection) -> None:
            task = asyncio.create_task(run_call(connection, session, settings))
            state.tasks.add(task)
            task.add_done_callback(state.tasks.discard)

        answer = await state.webrtc.handle_web_request(webrtc_request, on_connection)
        return {**(answer or {}), "session_id": session.id}

    @app.patch("/api/offer")
    async def ice_candidates(body: PatchIn, request: Request) -> dict[str, str]:
        await request.app.state.webrtc.handle_patch_request(
            SmallWebRTCPatchRequest(
                pc_id=body.pc_id,
                candidates=[
                    IceCandidate(
                        candidate=c.candidate, sdp_mid=c.sdp_mid, sdp_mline_index=c.sdp_mline_index
                    )
                    for c in body.candidates
                ],
            )
        )
        return {"status": "ok"}

    @app.get("/sessions")
    async def sessions(request: Request) -> list[dict[str, Any]]:
        return [
            {
                "session_id": s.id,
                "scenario": s.scenario,
                "created_at": s.created_at,
                "ended_at": s.ended_at,
                "turns": len(s.tracker.turns),
            }
            for s in reversed(request.app.state.sessions.all())
        ]

    @app.get("/sessions/{session_id}/metrics")
    async def session_metrics(session_id: str, request: Request) -> dict[str, Any]:
        session = request.app.state.sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        metrics: dict[str, Any] = session.metrics()
        return metrics

    @app.post("/v1/text-sessions", status_code=201)
    async def open_text_session(body: TextSessionIn, request: Request) -> dict[str, Any]:
        try:
            session = request.app.state.text_sessions.open(body)
        except ValueError as e:  # pydantic ValidationError is a ValueError
            raise HTTPException(status_code=422, detail=f"invalid pack: {e}") from e
        return {"session_id": session.id, "reply": session.start()}

    @app.post("/v1/text-sessions/{session_id}/turns")
    async def text_turn(session_id: str, body: TurnIn, request: Request) -> dict[str, Any]:
        session = request.app.state.text_sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="text session not found")
        reply: dict[str, Any] = await session.send(body.text, interrupt=body.interrupt)
        return reply

    @app.delete("/v1/text-sessions/{session_id}", status_code=204)
    async def close_text_session(session_id: str, request: Request) -> Response:
        if not request.app.state.text_sessions.close(session_id):
            raise HTTPException(status_code=404, detail="text session not found")
        return Response(status_code=204)

    return app


async def _no_new_call(_: SmallWebRTCConnection) -> None:
    return None
