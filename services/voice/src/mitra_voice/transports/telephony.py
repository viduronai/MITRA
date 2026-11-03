"""Phone calls: carrier media streams into the same pipeline as browser calls.

- ``WS   /telephony/exotel/ws``      Exotel Voicebot applet (bidirectional): 16-bit PCM (slin)
  at 8 kHz in ``media`` events; we answer with ``media`` and send ``clear`` on barge-in.
- ``WS   /telephony/plivo/ws``       Plivo ``<Stream bidirectional>``: mu-law 8 kHz; ``playAudio``
  out, ``clearAudio`` on barge-in. Only streams carrying our per-call token are accepted.
- ``POST /telephony/plivo/answer``   answer XML for Plivo (signature-checked when configured)
- ``POST /telephony/exotel/status``  Exotel status callback -> attempt outcome in core
- ``GET  /telephony/exotel/missed-call``  Exotel Passthru for missed-call numbers (CALL-20)
- ``POST /telephony/calls``          place an outbound call (service token): compliance first
- ``POST /telephony/dialer/calls``   place a call core's dialer already cleared (service token):
  core ran compliance.check and recorded the attempt; carries the script variables

Audio: Pipecat's Exotel/Plivo serializers resample carrier audio to the pipeline's 16 kHz input
and our 24 kHz output down to the carrier rate (and mu-law for Plivo). Barge-in: the pipeline's
InterruptionFrame becomes ``clear``/``clearAudio``, so the carrier drops audio already queued.
Output goes out in 200 ms chunks (3,200 bytes at 8 kHz, a multiple of 320, as Exotel advises).
"""

from __future__ import annotations

import asyncio
import dataclasses
import hmac
import json
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any
from urllib.parse import parse_qsl

import structlog
from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import Response
from pipecat.audio.vad.vad_analyzer import VADAnalyzer
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.serializers.exotel import ExotelFrameSerializer
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner
from pydantic import BaseModel, Field

from mitra_voice.callbacks import call_brief, fill, resolve_callback_time
from mitra_voice.carriers import CarrierError, OutboundRegistry, make_carrier
from mitra_voice.carriers.base import Carrier, OutboundIntent, Purpose
from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.carriers.outbound import DialRequest, dial, place_intent
from mitra_voice.carriers.plivo import answer_xml, stream_url, verify_signature_v3, verify_stream
from mitra_voice.config import Settings, TurnStrategy
from mitra_voice.pack import load_pack
from mitra_voice.pipeline import CallPipeline, build_call_pipeline, greet, make_turn_analyzers, say
from mitra_voice.session import CallSession
from mitra_voice.team.control import LiveControl
from mitra_voice.transports import missed_call
from mitra_voice.transports.payment_links import send_payment_links
from mitra_voice.transports.routing import (
    CallMeta,
    Route,
    RouteError,
    custom_params,
    exotel_authorized,
    plivo_stream_secret,
    route_call,
    to_e164,
)
from mitra_voice.transports.whatsapp_sends import send_whatsapp_messages

log = structlog.get_logger(__name__)

OUT_CHUNK_10MS = 20  # 200 ms per media message
MAX_CALL_S = 900  # matches the TimeLimit we give the carrier
EXOTEL_OUTCOMES = {"busy": "busy", "no-answer": "no_answer", "failed": "failed"}
POLICY_VIOLATION = 1008
MAX_WEBHOOK_BYTES = 16_384


@dataclass
class TelephonyState:
    carrier: Carrier
    registry: OutboundRegistry
    core: CoreTelephony | None
    fallback: Carrier | None = None
    # Placed calls awaiting a carrier status (attempt outcome), by call sid.
    dialled: dict[str, OutboundIntent] = field(default_factory=dict)
    # Tests swap Silero for an energy VAD (synthetic audio is not speech to Silero).
    vad_factory: Callable[[], VADAnalyzer] | None = None
    turn: TurnStrategy | None = None


class DialIn(BaseModel):
    business_id: uuid.UUID
    employee_id: uuid.UUID
    contact_phone: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    purpose: Purpose
    number_id: uuid.UUID | None = None
    called_number_id: uuid.UUID | None = None


class DialerCallIn(BaseModel):
    job_id: uuid.UUID
    business_id: uuid.UUID
    employee_id: uuid.UUID
    contact_phone: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    purpose: Purpose
    caller_id: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    phone_number_id: uuid.UUID
    attempt_id: uuid.UUID
    variables: dict[str, str] = Field(default_factory=dict, max_length=20)


def _require_service(settings: Settings, authorization: str | None) -> None:
    token = settings.mitra_core_service_token
    if token is None:
        if settings.is_local:
            return
        raise HTTPException(status_code=503, detail="outbound calling is not configured")
    supplied = (authorization or "").removeprefix("Bearer ")
    if not hmac.compare_digest(supplied.encode(), token.get_secret_value().encode()):
        raise HTTPException(status_code=401, detail="invalid service token")


def telephony_router(settings: Settings) -> APIRouter:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from mitra_voice.carriers import make_fallback

        state = TelephonyState(
            carrier=make_carrier(settings),
            registry=OutboundRegistry(),
            core=CoreTelephony.from_settings(settings),
            fallback=make_fallback(settings),
        )
        app.state.telephony = state
        log.info("telephony.ready", carrier=state.carrier.name, core=state.core is not None)
        yield
        for closable in (state.carrier, state.fallback, state.core):
            if closable is not None:
                await closable.aclose()

    router = APIRouter(prefix="/telephony", tags=["telephony"], lifespan=lifespan)

    @router.websocket("/exotel/ws")
    async def exotel_ws(websocket: WebSocket) -> None:
        if not exotel_authorized(websocket.headers, settings):
            log.warning("telephony.exotel_unauthorized")
            await websocket.close(code=POLICY_VIOLATION)
            return
        await websocket.accept()
        kind, data = await parse_telephony_websocket(websocket)
        if kind != "exotel" or not data.call_id or not data.stream_id:
            await websocket.close(code=POLICY_VIOLATION)
            return
        meta = CallMeta(
            carrier="exotel",
            call_sid=data.call_id,
            stream_sid=data.stream_id,
            from_=to_e164(data.from_number),
            to=to_e164(data.to_number),
            custom=custom_params(getattr(data, "custom_parameters", None))
            | dict(websocket.query_params),
        )
        serializer = ExotelFrameSerializer(
            meta.stream_sid,
            meta.call_sid,
            params=ExotelFrameSerializer.InputParams(
                exotel_sample_rate=settings.exotel_sample_rate
            ),
        )
        await _serve(websocket, serializer, meta, settings)

    @router.websocket("/plivo/ws")
    async def plivo_ws(websocket: WebSocket) -> None:
        secret = plivo_stream_secret(settings)
        params = dict(websocket.query_params)
        if secret is None or not verify_stream(secret, params):
            log.warning("telephony.plivo_unauthorized")
            await websocket.close(code=POLICY_VIOLATION)
            return
        await websocket.accept()
        kind, data = await parse_telephony_websocket(websocket)
        if kind != "plivo" or not data.call_id or not data.stream_id:
            await websocket.close(code=POLICY_VIOLATION)
            return
        token = settings.plivo_auth_token
        serializer = PlivoFrameSerializer(
            data.stream_id,
            data.call_id,
            auth_id=settings.plivo_auth_id,
            auth_token=token.get_secret_value() if token else None,
            params=PlivoFrameSerializer.InputParams(auto_hang_up=token is not None),
        )
        meta = CallMeta(
            carrier="plivo",
            call_sid=params.get("call", data.call_id),
            stream_sid=data.stream_id,
            from_=to_e164(params.get("from")),
            to=to_e164(params.get("to")),
            custom={k: v for k, v in params.items() if k in ("employee_id", "scenario") and v},
        )
        await _serve(websocket, serializer, meta, settings)

    @router.post("/plivo/answer", include_in_schema=False)
    async def plivo_answer(request: Request) -> Response:
        form = await _webhook_fields(request)
        token = settings.plivo_auth_token
        if token is not None:
            url = str(request.url)
            if settings.mitra_public_base_url:  # behind a proxy: sign the public URL
                url = settings.mitra_public_base_url.rstrip("/") + request.url.path
            ok = verify_signature_v3(
                token.get_secret_value(),
                url,
                request.headers.get("x-plivo-signature-v3-nonce", ""),
                form,
                request.headers.get("x-plivo-signature-v3", ""),
            )
            if not ok:
                raise HTTPException(status_code=403, detail="bad signature")
        elif not settings.is_local:
            raise HTTPException(status_code=503, detail="plivo is not configured")
        # Outbound: Plivo's RequestUUID is what place_call returned (the registry key).
        call = form.get("RequestUUID") or form.get("CallUUID", "")
        state: TelephonyState = request.app.state.telephony
        if state.registry.get(call) is None and await missed_call.reject_if_missed_call(
            state.core, to_e164(form.get("To")), to_e164(form.get("From")), call
        ):
            return Response(missed_call.PLIVO_REJECT_XML, media_type="application/xml")
        secret = plivo_stream_secret(settings) or ""
        base = settings.mitra_public_base_url or str(request.base_url)
        ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
        url = stream_url(
            ws_base,
            secret,
            call_uuid=call,
            from_=form.get("From", ""),
            to=form.get("To", ""),
        )
        return Response(answer_xml(url), media_type="application/xml")

    @router.post("/exotel/status", include_in_schema=False)
    async def exotel_status(request: Request) -> dict[str, str]:
        form = await _webhook_fields(request)
        state: TelephonyState = request.app.state.telephony
        sid, status = str(form.get("CallSid", "")), str(form.get("Status", ""))
        intent = state.dialled.pop(sid, None)  # unknown sids are ignored: nothing to update
        outcome = EXOTEL_OUTCOMES.get(status)
        if intent and outcome and intent.attempt_id and state.core is not None:
            await state.core.set_outcome(intent.attempt_id, intent.business_id, outcome)
        return {"status": "ok"}

    missed_call.add_missed_call_routes(router, settings)

    @router.post("/calls")
    async def place_call(
        body: DialIn, request: Request, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        _require_service(settings, authorization)
        state: TelephonyState = request.app.state.telephony
        try:
            result = await dial(
                DialRequest(
                    business_id=str(body.business_id),
                    employee_id=str(body.employee_id),
                    contact_phone=body.contact_phone,
                    purpose=body.purpose,
                    number_id=str(body.number_id) if body.number_id else None,
                    called_number_id=str(body.called_number_id) if body.called_number_id else None,
                ),
                carrier=state.carrier,
                registry=state.registry,
                core=state.core,
                fallback=state.fallback,
            )
        except CarrierError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        if result.call is not None and result.intent is not None:
            _remember(state, result.call.call_sid, result.intent)
        return {
            "decision": result.decision,
            "reasons": result.reasons,
            "defer_until": result.defer_until,
            "call_sid": result.call.call_sid if result.call else None,
            "carrier": result.call.carrier if result.call else None,
        }

    @router.post("/dialer/calls")
    async def place_dialer_call(
        body: DialerCallIn, request: Request, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Core's dialer worker: compliance and the attempt row are already done in core."""
        _require_service(settings, authorization)
        state: TelephonyState = request.app.state.telephony
        intent = OutboundIntent(
            business_id=str(body.business_id),
            employee_id=str(body.employee_id),
            contact_phone=body.contact_phone,
            caller_id=body.caller_id,
            purpose=body.purpose,
            phone_number_id=str(body.phone_number_id),
            attempt_id=str(body.attempt_id),
            job_id=str(body.job_id),
            variables={k[:40]: v[:200] for k, v in body.variables.items()},
        )
        try:
            placed = await place_intent(
                intent, carrier=state.carrier, registry=state.registry, fallback=state.fallback
            )
        except CarrierError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        _remember(state, placed.call_sid, intent)
        return {"call_sid": placed.call_sid, "carrier": placed.carrier}

    return router


async def _webhook_fields(request: Request) -> dict[str, str]:
    """Carrier webhooks: urlencoded (Plivo) or JSON (Exotel, StatusCallbackContentType)."""
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="webhook too large")
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            data = json.loads(body or b"{}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail="invalid json") from e
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    return dict(parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True))


def _remember(state: TelephonyState, sid: str, intent: OutboundIntent, cap: int = 1000) -> None:
    state.dialled[sid] = intent
    while len(state.dialled) > cap:
        state.dialled.pop(next(iter(state.dialled)))


async def _serve(
    websocket: WebSocket, serializer: FrameSerializer, meta: CallMeta, settings: Settings
) -> None:
    app_state = websocket.app.state
    state: TelephonyState = app_state.telephony
    try:
        route = await route_call(meta, settings=settings, registry=state.registry, core=state.core)
    except RouteError as e:
        log.warning("telephony.unroutable", carrier=meta.carrier, reason=str(e))
        await websocket.close(code=POLICY_VIOLATION)
        return
    if route.missed_call:  # a stream reached us anyway: never talk, core calls back
        await websocket.close()
        if state.core is not None and meta.to:
            await missed_call.report(state.core, meta.to, meta.from_, meta.call_sid)
        return
    pack = await load_pack(settings, route.scenario, route.employee_id)
    intent = route.intent
    if intent is not None and intent.variables and pack.greeting:
        pack = dataclasses.replace(pack, greeting=fill(pack.greeting, intent.variables) or None)
    session = CallSession(
        scenario=route.scenario,
        pack=pack,
        providers=app_state.providers,
        reporter=getattr(app_state, "core_reporter", None),
        direction=route.direction,
        caller_phone=route.caller_phone,
    )
    if intent is not None:
        session.call.call_brief = call_brief(intent.purpose, intent.variables)
    session.call_sid = meta.call_sid
    app_state.sessions.add(session)
    log.info(
        "telephony.call",
        session_id=session.id,
        carrier=meta.carrier,
        direction=route.direction,
        employee_id=route.employee_id,
    )
    if route.intent is not None and route.intent.attempt_id and state.core is not None:
        state.dialled.pop(meta.call_sid, None)
        await state.core.set_outcome(route.intent.attempt_id, route.intent.business_id, "answered")
    try:
        await run_phone_call(websocket, serializer, session, settings, state)
    finally:
        await _after_call(session, route, state)


async def run_phone_call(
    websocket: WebSocket,
    serializer: FrameSerializer,
    session: CallSession,
    settings: Settings,
    state: TelephonyState,
) -> None:
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            audio_out_10ms_chunks=OUT_CHUNK_10MS,
            session_timeout=MAX_CALL_S,
        ),
    )
    # Model loads block for 100s of ms: never on the event loop that carries every call's audio.
    analyzers = await asyncio.to_thread(make_turn_analyzers, settings)
    call = build_call_pipeline(
        session,
        settings,
        transport_input=transport.input(),
        transport_output=transport.output(),
        analyzers=analyzers,
        vad=state.vad_factory() if state.vad_factory else None,
        turn=state.turn,
    )

    control = LiveControl.from_settings(settings, session, state.carrier, session.call_sid)

    @transport.event_handler("on_client_connected")
    async def _on_connected(*_: object) -> None:
        await greet(call, session)
        if control is not None:
            control.attach(partial(say, call, session), partial(_hang_up, call))

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(*_: object) -> None:
        await call.worker.cancel(reason="caller hung up")

    @transport.event_handler("on_session_timeout")
    async def _on_timeout(*_: object) -> None:
        await call.worker.cancel(reason="call time limit")

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(call.worker)
    try:
        await runner.run()
    finally:
        session.end()
        if control is not None:
            await control.aclose()


async def _hang_up(call: CallPipeline, reason: str) -> None:
    await call.worker.cancel(reason=reason)


async def _after_call(session: CallSession, route: Route, state: TelephonyState) -> None:
    """CMP-06: "don't call me" during a call -> suppress the number in core.
    CALL-05: "call me back tomorrow at 5" -> a callback in core's dialer queue.
    ACT-05: payment links the employee promised -> core sends them on WhatsApp.
    ACT-02: booking confirmation / location / document / follow-up -> core WhatsApps them."""
    if state.core is None or not route.caller_phone or session.action_log is None:
        return
    try:
        actions = session.action_log()
        business_id = route.business_id or session.pack.business_id
        if not _is_uuid(business_id):
            return
        if route.caller_phone and _is_uuid(session.pack.employee_id):
            await send_payment_links(state.core, session, route.caller_phone, actions)
            await send_whatsapp_messages(state.core, session, route.caller_phone, actions)
        if any(a.get("name") == "opt_out" for a in actions):
            await state.core.opt_out(business_id, route.caller_phone, None)
            return  # never call back someone who asked not to be called
        asks = [a for a in actions if a.get("name") == "schedule_callback"]
        if asks and _is_uuid(session.pack.employee_id):
            args = dict(asks[-1].get("args") or {})
            if args.get("when") or args.get("when_iso"):
                at = resolve_callback_time(args, datetime.now(UTC))
                await state.core.schedule_callback(
                    {
                        "business_id": business_id,
                        "employee_id": session.pack.employee_id,
                        "contact_phone": route.caller_phone,
                        "at": at.isoformat(),
                        "note": str(args.get("topic") or "")[:200] or None,
                        "called_number_id": _called_number(route),
                    }
                )
    except Exception as e:  # never let bookkeeping fail the call teardown
        log.warning("telephony.after_call_failed", session_id=session.id, error=type(e).__name__)


def _called_number(route: Route) -> str | None:
    """Ring back from the number the customer dealt with (inbound: the one they dialled)."""
    if route.intent is not None:
        return route.intent.phone_number_id
    return route.phone_number_id


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
