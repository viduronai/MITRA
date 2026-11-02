"""How the dialer places a call: the voice service's carrier path, or an in-process simulator.

Core has already run ``compliance.check`` and recorded the ``outbound_attempt`` when it calls
:meth:`VoiceDialer.place`; the voice service only places the call (``POST
/telephony/dialer/calls``) and later reports the attempt's outcome to
``PATCH /internal/v1/telephony/attempts/{id}`` as it does for every outbound call.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from mitra_core.config import get_settings
from mitra_core.dialer.settings import DialerSettings
from mitra_core.models.enums import CallResult
from mitra_core.telephony.enums import AttemptOutcome

TIMEOUT_S = 10.0


class DialRejectedError(RuntimeError):
    """The carrier (or voice service) refused the call. ``spam``: carrier flagged the number."""

    def __init__(self, message: str, *, spam: bool = False) -> None:
        super().__init__(message)
        self.spam = spam


@dataclass(frozen=True, slots=True)
class PlaceRequest:
    job_id: uuid.UUID
    business_id: uuid.UUID
    employee_id: uuid.UUID
    phone_e164: str = field(repr=False)
    purpose: str
    caller_id: str
    phone_number_id: uuid.UUID
    attempt_id: uuid.UUID
    variables: dict[str, str]


@dataclass(frozen=True, slots=True)
class Placed:
    call_sid: str
    # Simulator only: the outcome (and, if answered, the call result) known immediately.
    outcome: AttemptOutcome | None = None
    result: CallResult | None = None


class VoiceDialer(Protocol):
    async def place(self, req: PlaceRequest) -> Placed: ...


# Deterministic per number so a demo campaign gives stable, plausible buckets.
_SIM_RESULTS: tuple[tuple[AttemptOutcome, CallResult | None], ...] = (
    (AttemptOutcome.ANSWERED, CallResult.INTERESTED),
    (AttemptOutcome.ANSWERED, CallResult.CALL_BACK),
    (AttemptOutcome.ANSWERED, CallResult.NOT_INTERESTED),
    (AttemptOutcome.NO_ANSWER, None),
    (AttemptOutcome.ANSWERED, CallResult.INTERESTED),
    (AttemptOutcome.BUSY, None),
    (AttemptOutcome.ANSWERED, CallResult.NOT_INTERESTED),
    (AttemptOutcome.ANSWERED, CallResult.BOOKED),
)


@dataclass
class SimVoiceDialer:
    """Never dials anyone. Tests can force an outcome per last-4 digits via ``script``."""

    script: dict[str, tuple[AttemptOutcome, CallResult | None] | Exception] = field(
        default_factory=dict
    )
    placed: list[PlaceRequest] = field(default_factory=list)

    async def place(self, req: PlaceRequest) -> Placed:
        scripted = self.script.get(req.phone_e164[-4:])
        if isinstance(scripted, Exception):
            raise scripted
        self.placed.append(req)
        if scripted is None:
            digest = hashlib.sha256(f"{req.phone_e164}:{req.attempt_id}".encode()).digest()
            scripted = _SIM_RESULTS[digest[0] % len(_SIM_RESULTS)]
        outcome, result = scripted
        return Placed(call_sid="SIMJOB" + uuid.uuid4().hex[:26], outcome=outcome, result=result)


class HttpVoiceDialer:
    def __init__(
        self, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._base = base_url.rstrip("/")
        self._token = token
        self._transport = transport

    async def place(self, req: PlaceRequest) -> Placed:
        body = {
            "job_id": str(req.job_id),
            "business_id": str(req.business_id),
            "employee_id": str(req.employee_id),
            "contact_phone": req.phone_e164,
            "purpose": req.purpose,
            "caller_id": req.caller_id,
            "phone_number_id": str(req.phone_number_id),
            "attempt_id": str(req.attempt_id),
            "variables": req.variables,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=self._transport) as client:
                res = await client.post(
                    f"{self._base}/telephony/dialer/calls",
                    json=body,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.HTTPError as e:
            raise DialRejectedError(f"voice service unreachable: {type(e).__name__}") from e
        if res.status_code != 200:
            detail = res.json().get("detail", "") if res.content else ""
            raise DialRejectedError(
                f"voice service answered {res.status_code}", spam="spam" in str(detail).lower()
            )
        return Placed(call_sid=str(res.json().get("call_sid") or ""))


def make_voice_dialer(settings: DialerSettings) -> VoiceDialer:
    if settings.mode == "sim":
        return SimVoiceDialer()
    token = get_settings().effective_service_token
    if token is None:
        raise ValueError("MITRA_SERVICE_TOKEN is needed to place calls through the voice service")
    return HttpVoiceDialer(settings.voice_url, token)
