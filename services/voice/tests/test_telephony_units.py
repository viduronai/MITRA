"""Telephony building blocks: number parsing, carrier auth, Plivo signatures, carrier adapters
(against mocked HTTP) and the compliance-first dial orchestration."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from mitra_voice.carriers import CarrierError, make_carrier, make_fallback
from mitra_voice.carriers.base import OutboundIntent, OutboundRegistry
from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.carriers.exotel import ExotelCarrier
from mitra_voice.carriers.outbound import DialRequest, dial
from mitra_voice.carriers.plivo import (
    PlivoCarrier,
    answer_xml,
    signature_v3,
    stream_url,
    verify_signature_v3,
    verify_stream,
)
from mitra_voice.carriers.sim import SimCarrier
from mitra_voice.carriers.simulator import pcm_to_ulaw, ulaw_to_pcm
from mitra_voice.config import Settings
from mitra_voice.transports.routing import (
    CallMeta,
    RouteError,
    custom_params,
    exotel_authorized,
    route_call,
    to_e164,
)

BIZ = "6f1c1d6e-1111-4a2b-9c3d-000000000001"
EMP = "6f1c1d6e-2222-4a2b-9c3d-000000000002"
CUSTOMER = "+919812345678"
EXOPHONE = "+914041234567"


def intent(**kw: Any) -> OutboundIntent:
    base: dict[str, Any] = {
        "business_id": BIZ,
        "employee_id": EMP,
        "contact_phone": CUSTOMER,
        "caller_id": EXOPHONE,
        "purpose": "service",
    }
    return OutboundIntent(**(base | kw))


# ---- numbers and parameters ---


@pytest.mark.parametrize(
    ("raw", "e164"),
    [
        ("09812345678", "+919812345678"),
        ("9812345678", "+919812345678"),
        ("919812345678", "+919812345678"),
        ("+91 98123 45678", "+919812345678"),
        ("04041234567", "+914041234567"),
        ("anonymous", None),
        ("", None),
        (None, None),
    ],
)
def test_to_e164(raw: object, e164: str | None) -> None:
    assert to_e164(raw) == e164


def test_custom_params_dict_or_query_string() -> None:
    assert custom_params({"employee_id": "x"}) == {"employee_id": "x"}
    assert custom_params("?employee_id=x&scenario=clinic") == {
        "employee_id": "x",
        "scenario": "clinic",
    }
    assert custom_params(None) == {}


# ---- carrier authentication ---


def _basic(user: str, password: str) -> dict[str, str]:
    return {"authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test_exotel_basic_auth() -> None:
    configured = Settings(exotel_api_key="key", exotel_api_token=SecretStr("tok"))
    assert exotel_authorized(_basic("key", "tok"), configured)
    assert not exotel_authorized(_basic("key", "nope"), configured)
    assert not exotel_authorized({}, configured)
    # Unconfigured: the simulator works locally, everything else fails closed.
    assert exotel_authorized({}, Settings())
    assert not exotel_authorized({}, Settings(mitra_env="staging"))  # type: ignore[arg-type]


def test_plivo_stream_token_round_trip() -> None:
    url = stream_url("wss://v.example", "s3cret", call_uuid="c1", from_="+911", to="+912")
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}
    assert verify_stream("s3cret", params)
    assert not verify_stream("other", params)
    assert not verify_stream("s3cret", params | {"from": "+919999999999"})  # tampered
    assert url.startswith("wss://v.example/telephony/plivo/ws?")
    xml = answer_xml(url)
    assert 'bidirectional="true"' in xml
    assert "&amp;" in xml  # the URL is XML-escaped
    assert 'contentType="audio/x-mulaw;rate=8000"' in xml


def test_plivo_signature_v3() -> None:
    params = {"To": "+15555555555", "From": "+15551111111", "CallUUID": "abc"}
    sig = signature_v3("tok", "https://v.example/answer", "nonce1", params)
    assert verify_signature_v3("tok", "https://v.example/answer", "nonce1", params, sig)
    assert verify_signature_v3("tok", "https://v.example/answer", "nonce1", params, f"x,{sig}")
    assert not verify_signature_v3("tok", "https://v.example/answer", "nonce2", params, sig)
    assert not verify_signature_v3("tok", "https://v.example/answer", "", params, sig)


def test_mu_law_round_trip_is_close() -> None:
    t = np.arange(800) / 8000
    pcm = (8000 * np.sin(2 * np.pi * 300 * t)).astype("<i2").tobytes()
    back = np.frombuffer(ulaw_to_pcm(pcm_to_ulaw(pcm)), dtype="<i2").astype(np.int32)
    orig = np.frombuffer(pcm, dtype="<i2").astype(np.int32)
    assert len(pcm_to_ulaw(pcm)) == len(orig)
    assert np.max(np.abs(back - orig)) < 300  # G.711 quantisation error


# ---- routing ---


def _meta(**kw: Any) -> CallMeta:
    base: dict[str, Any] = {
        "carrier": "exotel",
        "call_sid": "CA1",
        "stream_sid": "ST1",
        "from_": CUSTOMER,
        "to": EXOPHONE,
        "custom": {},
    }
    return CallMeta(**(base | kw))


async def test_route_outbound_from_registry_then_pinned_then_fixture() -> None:
    registry = OutboundRegistry()
    registry.add("CA1", intent())
    out = await route_call(_meta(), settings=Settings(), registry=registry, core=None)
    assert out.direction == "outbound"
    assert out.employee_id == EMP
    assert out.caller_phone == CUSTOMER
    assert registry.get("CA1") is None  # consumed

    pinned = await route_call(
        _meta(custom={"employee_id": EMP}), settings=Settings(), registry=registry, core=None
    )
    assert (pinned.direction, pinned.employee_id) == ("inbound", EMP)

    local = await route_call(
        _meta(custom={"scenario": "real_estate"}), settings=Settings(), registry=registry, core=None
    )
    assert (local.employee_id, local.scenario) == (None, "real_estate")


def _core(handler: Any) -> CoreTelephony:
    return CoreTelephony("http://core", "tok", transport=httpx.MockTransport(handler))


async def test_route_inbound_via_core_number_lookup() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.params["to"] == EXOPHONE:
            return httpx.Response(
                200,
                json={
                    "business_id": BIZ,
                    "business_name": "Sunrise Clinic",
                    "employee_id": EMP,
                    "phone_number_id": "n1",
                    "caller_known": False,
                },
            )
        return httpx.Response(404, json={})

    core = _core(handler)
    staging = Settings(mitra_env="staging")  # type: ignore[arg-type]
    route = await route_call(_meta(), settings=staging, registry=OutboundRegistry(), core=core)
    assert (route.direction, route.employee_id, route.business_id) == ("inbound", EMP, BIZ)
    assert seen[0].url.path == "/internal/v1/telephony/resolve"
    assert seen[0].headers["authorization"] == "Bearer tok"
    with pytest.raises(RouteError):
        await route_call(
            _meta(to="+914000000000"), settings=staging, registry=OutboundRegistry(), core=core
        )
    with pytest.raises(RouteError):  # outside local, no core = no route
        await route_call(_meta(), settings=staging, registry=OutboundRegistry(), core=None)


def test_registry_expires() -> None:
    registry = OutboundRegistry(ttl_s=0)
    registry.add("x", intent())
    assert registry.get("x") is None


# ---- carriers ---


async def test_exotel_place_call_request() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"Call": {"Sid": "exo-sid-1", "Status": "in-progress"}})

    carrier = ExotelCarrier(
        account_sid="acme1",
        api_key="key",
        api_token="tok",
        app_id="777",
        status_callback="https://v.example/telephony/exotel/status",
        transport=httpx.MockTransport(handler),
    )
    placed = await carrier.place_call(intent())
    assert (placed.carrier, placed.call_sid) == ("exotel", "exo-sid-1")
    req = seen[0]
    assert str(req.url) == "https://api.in.exotel.com/v1/Accounts/acme1/Calls/connect.json"
    assert req.headers["authorization"] == "Basic " + base64.b64encode(b"key:tok").decode()
    form = parse_qs(req.content.decode())
    assert form["From"] == [CUSTOMER]
    assert form["CallerId"] == [EXOPHONE]
    assert form["Url"] == ["http://my.exotel.com/acme1/exoml/start_voice/777"]
    assert form["CallType"] == ["trans"]
    assert CUSTOMER not in form["CustomField"][0]  # ids only, never numbers
    await carrier.aclose()


async def test_exotel_errors_never_leak_secrets() -> None:
    carrier = ExotelCarrier(
        account_sid="acme1",
        api_key="key",
        api_token="tok",
        app_id="777",
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="bad tok")),
    )
    with pytest.raises(CarrierError) as err:
        await carrier.place_call(intent())
    assert "tok" not in str(err.value)
    await carrier.aclose()


async def test_plivo_place_call_request() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(201, json={"request_uuid": "req-1", "message": "call fired"})

    carrier = PlivoCarrier(
        auth_id="MA1",
        auth_token="tok",
        answer_url="https://v.example/telephony/plivo/answer",
        transport=httpx.MockTransport(handler),
    )
    placed = await carrier.place_call(intent())
    assert placed.call_sid == "req-1"
    assert str(seen[0].url) == "https://api.plivo.com/v1/Account/MA1/Call/"
    body = json.loads(seen[0].content)
    assert body["from"] == "914041234567"
    assert body["to"] == "919812345678"
    assert body["answer_url"].endswith("/telephony/plivo/answer")
    await carrier.aclose()


def test_make_carrier_names_missing_settings() -> None:
    assert make_carrier(Settings()).name == "sim"
    with pytest.raises(ValueError, match="EXOTEL_ACCOUNT_SID"):
        make_carrier(Settings(mitra_telephony_carrier="exotel"))
    with pytest.raises(ValueError, match="PLIVO_AUTH_ID"):
        make_carrier(Settings(mitra_telephony_carrier="plivo"))
    exotel = Settings(
        mitra_telephony_carrier="exotel",
        exotel_account_sid="a",
        exotel_api_key="k",
        exotel_api_token=SecretStr("t"),
        exotel_app_id="1",
        plivo_auth_id="MA1",
        plivo_auth_token=SecretStr("p"),
        mitra_public_base_url="https://v.example",
    )
    assert make_carrier(exotel).name == "exotel"
    fallback = make_fallback(exotel)
    assert fallback is not None
    assert fallback.name == "plivo"


# ---- dial: compliance first ---


def _compliance_core(decision: str, calls: list[tuple[str, str]]) -> CoreTelephony:
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.url.path.endswith("/compliance/check"):
            if decision != "allow":
                reasons = [{"code": "opted_out", "message": "asked not to be called"}]
                return httpx.Response(
                    200,
                    json={
                        "decision": decision,
                        "allowed": False,
                        "reasons": reasons,
                        "caller_id": None,
                        "defer_until": None,
                        "decision_id": "d1",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "allowed": True,
                    "reasons": [],
                    "caller_id": {"phone_number_id": "n1", "e164": EXOPHONE, "type": "local"},
                    "defer_until": None,
                    "decision_id": "d1",
                },
            )
        if req.url.path.endswith("/attempts"):
            return httpx.Response(201, json={"id": "att-1", "outcome": None, "attempted_at": "x"})
        return httpx.Response(200, json={"id": "att-1", "outcome": "failed", "attempted_at": "x"})

    return _core(handler)


def _req() -> DialRequest:
    return DialRequest(business_id=BIZ, employee_id=EMP, contact_phone=CUSTOMER, purpose="service")


async def test_blocked_call_is_never_dialled() -> None:
    calls: list[tuple[str, str]] = []
    sim, registry = SimCarrier(), OutboundRegistry()
    result = await dial(
        _req(), carrier=sim, registry=registry, core=_compliance_core("block", calls)
    )
    assert result.decision == "block"
    assert result.reasons[0]["code"] == "opted_out"
    assert sim.placed == []
    assert [p for _, p in calls] == ["/internal/v1/telephony/compliance/check"]


async def test_allowed_call_records_attempt_and_registers_intent() -> None:
    calls: list[tuple[str, str]] = []
    sim, registry = SimCarrier(), OutboundRegistry()
    result = await dial(
        _req(), carrier=sim, registry=registry, core=_compliance_core("allow", calls)
    )
    assert result.decision == "allow"
    assert result.call is not None
    assert result.caller_id == EXOPHONE
    registered = registry.get(result.call.call_sid)
    assert registered is not None
    assert (registered.caller_id, registered.attempt_id) == (EXOPHONE, "att-1")
    assert [p.rsplit("/", 1)[-1] for _, p in calls] == ["check", "attempts"]


class _DownCarrier:
    name = "exotel"

    async def place_call(self, _: OutboundIntent) -> Any:
        raise CarrierError("exotel answered 503")

    async def aclose(self) -> None:
        return None


async def test_carrier_outage_falls_back_then_fails_cleanly() -> None:
    calls: list[tuple[str, str]] = []
    core = _compliance_core("allow", calls)
    sim = SimCarrier()
    result = await dial(
        _req(), carrier=_DownCarrier(), fallback=sim, registry=OutboundRegistry(), core=core
    )  # type: ignore[arg-type]
    assert result.call is not None
    assert result.call.carrier == "sim"
    with pytest.raises(CarrierError):
        await dial(_req(), carrier=_DownCarrier(), registry=OutboundRegistry(), core=core)  # type: ignore[arg-type]
    assert calls[-1] == ("PATCH", "/internal/v1/telephony/attempts/att-1")  # marked failed


async def test_real_carrier_requires_core() -> None:
    with pytest.raises(CarrierError, match="compliance"):
        await dial(_req(), carrier=_DownCarrier(), registry=OutboundRegistry(), core=None)  # type: ignore[arg-type]
