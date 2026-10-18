"""HTTP surface of the voice engine (port 8200).

- ``GET /``                       browser test page (mic -> WebRTC -> pipeline)
- ``POST /api/offer``             WebRTC offer -> answer; starts a call session
- ``PATCH /api/offer``            trickle ICE candidates
- ``GET /sessions``               recent sessions
- ``GET /sessions/{id}/metrics``  per-turn latencies + p50/p95 summary
- ``/v1/text-sessions`` (POST), ``.../{id}/turns`` (POST), ``.../{id}`` (DELETE): text-mode
  sessions for mitra-evals
- ``GET /health``
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
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
from mitra_voice.logging import configure_logging
from mitra_voice.pack import Scenario, load_pack
from mitra_voice.pipeline import build_call_pipeline, greet
from mitra_voice.providers import ResolvedProviders, resolve_providers
from mitra_voice.session import CallSession, SessionRegistry
from mitra_voice.text_sessions import TextSessionIn, TextSessionStore, TurnIn

log = structlog.get_logger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


class OfferIn(BaseModel):
    sdp: str = Field(min_length=1, max_length=50_000)
    type: Literal["offer"]
    pc_id: str | None = Field(default=None, max_length=200)
    restart_pc: bool | None = None
    scenario: Scenario = "clinic"


class CandidateIn(BaseModel):
    candidate: str = Field(max_length=2_000)
    sdp_mid: str
    sdp_mline_index: int


class PatchIn(BaseModel):
    pc_id: str = Field(max_length=200)
    candidates: list[CandidateIn] = Field(max_length=50)


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
    call = build_call_pipeline(
        session, settings, transport_input=transport.input(), transport_output=transport.output()
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
        # No STUN/TURN: fine for localhost; TODO(deploy) TURN for browsers off-LAN.
        app.state.webrtc = SmallWebRTCRequestHandler(ice_servers=[])
        app.state.sessions = SessionRegistry()
        app.state.text_sessions = TextSessionStore()
        app.state.tasks = set()
        yield
        for task in list(app.state.tasks):
            task.cancel()
        await app.state.webrtc.close()

    app = FastAPI(title="Mitra Voice", version="0.1.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        p: ResolvedProviders = request.app.state.providers
        return {"status": "ok", "providers": {"stt": p.stt, "llm": p.llm, "tts": p.tts}}

    @app.post("/api/offer")
    async def offer(body: OfferIn, request: Request) -> dict[str, Any]:
        state = request.app.state
        webrtc_request = SmallWebRTCRequest(
            sdp=body.sdp, type=body.type, pc_id=body.pc_id, restart_pc=body.restart_pc
        )
        if body.pc_id:  # renegotiation of an existing call
            answer = await state.webrtc.handle_web_request(webrtc_request, _no_new_call)
            return dict(answer or {})

        pack = await load_pack(settings, body.scenario)
        session = CallSession(scenario=body.scenario, pack=pack, providers=state.providers)
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
        reply: dict[str, Any] = session.send(body.text, interrupt=body.interrupt)
        return reply

    @app.delete("/v1/text-sessions/{session_id}", status_code=204)
    async def close_text_session(session_id: str, request: Request) -> Response:
        if not request.app.state.text_sessions.close(session_id):
            raise HTTPException(status_code=404, detail="text session not found")
        return Response(status_code=204)

    return app


async def _no_new_call(_: SmallWebRTCConnection) -> None:
    return None
