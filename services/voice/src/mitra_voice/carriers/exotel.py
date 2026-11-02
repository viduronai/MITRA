"""Exotel outbound: "connect a number to a call flow" (Voice v1).

``POST https://{subdomain}/v1/Accounts/{sid}/Calls/connect.json`` (HTTP Basic: API key / token)
with ``From`` = the customer (dialled first), ``CallerId`` = our ExoPhone, ``Url`` = the call
flow whose Voicebot applet points at ``wss://<voice>/telephony/exotel/ws``. When the customer
answers, Exotel opens the stream; the ``start`` message carries this call's ``call_sid``, which
the OutboundRegistry maps back to the intent. See docs/telephony.md for sources.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from mitra_voice.carriers.base import CarrierError, CarrierName, OutboundIntent, PlacedCall
from mitra_voice.team.ladder import TransferOutcome

log = structlog.get_logger(__name__)

TIMEOUT_S = 10.0
RING_TIMEOUT_S = 30
MAX_CALL_S = 900


class ExotelCarrier:
    name: CarrierName = "exotel"

    def __init__(
        self,
        *,
        account_sid: str,
        api_key: str,
        api_token: str,
        app_id: str,
        subdomain: str = "api.in.exotel.com",
        status_callback: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._sid = account_sid
        self._flow_url = f"http://my.exotel.com/{account_sid}/exoml/start_voice/{app_id}"
        self._status_callback = status_callback
        self._client = httpx.AsyncClient(
            base_url=f"https://{subdomain}",
            auth=(api_key, api_token),
            timeout=TIMEOUT_S,
            transport=transport,
        )

    def request_body(self, intent: OutboundIntent) -> dict[str, Any]:
        body: dict[str, Any] = {
            "From": intent.contact_phone,
            "CallerId": intent.caller_id,
            "Url": self._flow_url,
            "CallType": "trans",  # transactional / service, never promotional (08 section 8.1)
            "TimeOut": RING_TIMEOUT_S,
            "TimeLimit": MAX_CALL_S,
            # Echoed to the flow's Passthru applets; ids only (128 chars max), never numbers.
            "CustomField": f"e={intent.employee_id}",
        }
        if self._status_callback:
            body["StatusCallback"] = self._status_callback
            body["StatusCallbackEvents[0]"] = "terminal"
            body["StatusCallbackEvents[1]"] = "answered"
            body["StatusCallbackContentType"] = "application/json"
        return body

    async def place_call(self, intent: OutboundIntent) -> PlacedCall:
        path = f"/v1/Accounts/{self._sid}/Calls/connect.json"
        try:
            res = await self._client.post(path, data=self.request_body(intent))
        except httpx.HTTPError as e:
            raise CarrierError(f"exotel unreachable: {type(e).__name__}") from e
        if res.status_code >= 300:
            log.warning("exotel.place_call_failed", status=res.status_code)
            raise CarrierError(f"exotel answered {res.status_code}")
        call = res.json().get("Call") or {}
        sid = call.get("Sid")
        if not isinstance(sid, str) or not sid:
            raise CarrierError("exotel response had no Call.Sid")
        return PlacedCall(carrier="exotel", call_sid=sid, status=str(call.get("Status", "queued")))

    async def transfer(
        self, call_sid: str, to_e164: str, *, whisper: str, ring_timeout_s: int
    ) -> TransferOutcome:
        """Warm transfer with whisper. Not wired to exotel yet: every step reports "failed",
        so the ladder ends in a message taken by the AI (no call is ever dropped).

        TODO(exotel): dial the staff leg, play ``whisper`` to it only, then bridge the legs.
        """
        log.warning("exotel.transfer_not_implemented", call_sid=call_sid)
        return "failed"

    async def aclose(self) -> None:
        await self._client.aclose()
