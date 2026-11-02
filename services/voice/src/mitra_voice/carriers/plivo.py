"""Plivo (secondary carrier, WORKFLOWS section 12): outbound calls, answer XML, signatures.

Outbound: ``POST https://api.plivo.com/v1/Account/{auth_id}/Call/`` with ``from``, ``to`` and
``answer_url`` = ``/telephony/plivo/answer`` on this service. Plivo fetches the answer URL when the
call connects; we reply with ``<Stream bidirectional="true">`` pointing at our WebSocket, adding a
per-call HMAC token so only streams we handed out are accepted. Plivo's ``start`` message has no
from/to, so they travel (signed) in the stream URL. Webhooks are verified with
``X-Plivo-Signature-V3`` (HMAC-SHA256 of URL + sorted POST params + nonce, base64).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import httpx
import structlog

from mitra_voice.carriers.base import CarrierError, CarrierName, OutboundIntent, PlacedCall
from mitra_voice.team.ladder import TransferOutcome

log = structlog.get_logger(__name__)

API = "https://api.plivo.com"
TIMEOUT_S = 10.0
RING_TIMEOUT_S = 30
CONTENT_TYPE = "audio/x-mulaw;rate=8000"


def _hmac(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def stream_token(secret: str, call_uuid: str, from_: str, to: str, employee_id: str) -> str:
    return _hmac(secret, "|".join((call_uuid, from_, to, employee_id)))


def stream_url(
    ws_base: str, secret: str, *, call_uuid: str, from_: str, to: str, employee_id: str = ""
) -> str:
    params = {"call": call_uuid, "from": from_, "to": to, "employee_id": employee_id}
    params["token"] = stream_token(secret, call_uuid, from_, to, employee_id)
    return f"{ws_base.rstrip('/')}/telephony/plivo/ws?{urlencode(params)}"


def verify_stream(secret: str, params: Mapping[str, str]) -> bool:
    expected = stream_token(
        secret,
        params.get("call", ""),
        params.get("from", ""),
        params.get("to", ""),
        params.get("employee_id", ""),
    )
    return hmac.compare_digest(expected, params.get("token", ""))


def answer_xml(url: str) -> str:
    """Bidirectional mu-law 8 kHz stream; keepCallAlive holds the call while it streams."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<Response>'
        f'<Stream bidirectional="true" keepCallAlive="true" contentType="{CONTENT_TYPE}">'
        f"{escape(url)}</Stream></Response>"
    )


def signature_v3(auth_token: str, url: str, nonce: str, params: Mapping[str, str]) -> str:
    base = url
    if params:
        base += "." + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), f"{base}.{nonce}".encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def verify_signature_v3(
    auth_token: str, url: str, nonce: str, params: Mapping[str, str], header: str
) -> bool:
    """``header`` may hold several comma-separated signatures (one per active token)."""
    if not nonce or not header:
        return False
    expected = signature_v3(auth_token, url, nonce, params)
    return any(hmac.compare_digest(expected, s.strip()) for s in header.split(","))


class PlivoCarrier:
    name: CarrierName = "plivo"

    def __init__(
        self,
        *,
        auth_id: str,
        auth_token: str,
        answer_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth_id = auth_id
        self._answer_url = answer_url
        self._client = httpx.AsyncClient(
            base_url=API, auth=(auth_id, auth_token), timeout=TIMEOUT_S, transport=transport
        )

    def request_body(self, intent: OutboundIntent) -> dict[str, object]:
        return {
            "from": intent.caller_id.lstrip("+"),
            "to": intent.contact_phone.lstrip("+"),
            "answer_url": self._answer_url,
            "answer_method": "POST",
            "ring_timeout": RING_TIMEOUT_S,
        }

    async def place_call(self, intent: OutboundIntent) -> PlacedCall:
        try:
            res = await self._client.post(
                f"/v1/Account/{self._auth_id}/Call/", json=self.request_body(intent)
            )
        except httpx.HTTPError as e:
            raise CarrierError(f"plivo unreachable: {type(e).__name__}") from e
        if res.status_code >= 300:
            log.warning("plivo.place_call_failed", status=res.status_code)
            raise CarrierError(f"plivo answered {res.status_code}")
        request_uuid = res.json().get("request_uuid")
        if isinstance(request_uuid, list):  # Plivo returns a list for multi-destination calls
            request_uuid = request_uuid[0] if request_uuid else None
        if not isinstance(request_uuid, str) or not request_uuid:
            raise CarrierError("plivo response had no request_uuid")
        return PlacedCall(carrier="plivo", call_sid=request_uuid, status="queued")

    async def transfer(
        self, call_sid: str, to_e164: str, *, whisper: str, ring_timeout_s: int
    ) -> TransferOutcome:
        """Warm transfer with whisper. Not wired to plivo yet: every step reports "failed",
        so the ladder ends in a message taken by the AI (no call is ever dropped).

        TODO(plivo): dial the staff leg, play ``whisper`` to it only, then bridge the legs.
        """
        log.warning("plivo.transfer_not_implemented", call_sid=call_sid)
        return "failed"

    async def aclose(self) -> None:
        await self._client.aclose()
