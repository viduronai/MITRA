"""services/core telephony endpoints (``/internal/v1/telephony``) used by the voice service.

- ``resolve(to, from)``: dialled number -> business, answering employee (inbound routing)
- ``compliance_check(...)``: ``compliance.check(contact, purpose, time, number)`` before dialling
- ``record_attempt`` / ``set_outcome``: frequency caps and per-number answer rate
- ``opt_out``: "don't call me" during a call (CMP-06)
- ``schedule_callback``: "call me back tomorrow at 5" -> core's dialer queue (CALL-05)
- ``send_payment_link``: the employee's payment link -> core's payments (ACT-05)
- ``report_missed_call``: a call to a missed-call number we did not answer (CALL-20)

Inbound resolution sits on the call-start path, so it has a hard timeout; everything else
happens before dialling or after hang-up. Phone numbers are sent to core (which hashes them) and
never logged here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from mitra_voice.config import Settings

log = structlog.get_logger(__name__)

RESOLVE_TIMEOUT_S = 1.5
TIMEOUT_S = 5.0
PREFIX = "/internal/v1/telephony"


class CoreTelephonyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Resolved:
    business_id: str
    business_name: str
    employee_id: str
    phone_number_id: str
    caller_known: bool
    missed_call: bool = False  # CALL-20: never answer; reject and report instead


class CoreTelephony:
    def __init__(
        self,
        core_url: str,
        service_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._dialer_url = core_url.rstrip("/") + "/internal/v1/dialer"
        self._payments_url = core_url.rstrip("/") + "/internal/v1/payments"
        self._whatsapp_url = core_url.rstrip("/") + "/internal/v1/whatsapp"
        self._client = httpx.AsyncClient(
            base_url=core_url.rstrip("/") + PREFIX,
            headers={"Authorization": f"Bearer {service_token}"},
            timeout=TIMEOUT_S,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> CoreTelephony | None:
        if not settings.mitra_core_url or not settings.mitra_core_service_token:
            return None
        return cls(settings.mitra_core_url, settings.mitra_core_service_token.get_secret_value())

    async def _send(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            return await self._client.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise CoreTelephonyError(f"core unreachable: {type(e).__name__}") from e

    async def resolve(self, to: str, from_: str | None) -> Resolved | None:
        """None when core does not know the number (404); raises when core is unavailable."""
        params = {"to": to} | ({"from": from_} if from_ else {})
        res = await self._send("GET", "/resolve", params=params, timeout=RESOLVE_TIMEOUT_S)
        if res.status_code == 404:
            return None
        if res.status_code != 200:
            raise CoreTelephonyError(f"core answered {res.status_code}")
        body = res.json()
        return Resolved(
            business_id=body["business_id"],
            business_name=body["business_name"],
            employee_id=body["employee_id"],
            phone_number_id=body["phone_number_id"],
            caller_known=bool(body.get("caller_known")),
            missed_call=bool(body.get("missed_call")),
        )

    async def compliance_check(self, body: dict[str, Any]) -> dict[str, Any]:
        res = await self._send("POST", "/compliance/check", json=body)
        if res.status_code != 200:
            raise CoreTelephonyError(f"compliance check failed: {res.status_code}")
        out: dict[str, Any] = res.json()
        return out

    async def record_attempt(self, body: dict[str, Any]) -> str | None:
        res = await self._send("POST", "/attempts", json=body)
        if res.status_code != 201:
            log.warning("core.attempt_failed", status=res.status_code)
            return None
        return str(res.json()["id"])

    async def set_outcome(self, attempt_id: str, business_id: str, outcome: str) -> None:
        res = await self._send(
            "PATCH",
            f"/attempts/{attempt_id}",
            json={"business_id": business_id, "outcome": outcome},
        )
        if res.status_code != 200:
            log.warning("core.outcome_failed", status=res.status_code)

    async def opt_out(self, business_id: str, contact_phone: str, purpose: str | None) -> None:
        body = {"business_id": business_id, "contact_phone": contact_phone, "purpose": purpose}
        res = await self._send("POST", "/opt-outs", json=body)
        if res.status_code != 201:
            log.warning("core.opt_out_failed", status=res.status_code)

    async def schedule_callback(self, body: dict[str, Any]) -> str | None:
        """CALL-05: queue a call back in core's dialer; returns the job id."""
        res = await self._send("POST", f"{self._dialer_url}/callbacks", json=body)
        if res.status_code != 201:
            log.warning("core.callback_failed", status=res.status_code)
            return None
        return str(res.json()["job_id"])

    async def report_missed_call(self, to: str, from_: str, call_sid: str | None) -> str | None:
        """CALL-20: core queues the callback; returns its status (queued, deduped, ...)."""
        body = {"to": to, "from": from_} | ({"carrier_call_sid": call_sid} if call_sid else {})
        res = await self._send("POST", "/missed-calls", json=body)
        if res.status_code != 200:
            log.warning("core.missed_call_failed", status=res.status_code)
            return None
        return str(res.json()["status"])

    async def send_payment_link(self, body: dict[str, Any]) -> str | None:
        """ACT-05: core creates the link (or asks the owner first) and WhatsApps it."""
        res = await self._send("POST", f"{self._payments_url}/links", json=body)
        if res.status_code != 201:
            log.warning("core.payment_link_failed", status=res.status_code)
            return None
        return str(res.json()["status"])

    async def send_whatsapp(self, body: dict[str, Any]) -> str | None:
        """ACT-02: core WhatsApps what the employee promised (links from its own knowledge)."""
        res = await self._send("POST", f"{self._whatsapp_url}/sends", json=body)
        if res.status_code != 201:
            log.warning("core.whatsapp_send_failed", status=res.status_code)
            return None
        return str(res.json()["status"])

    async def aclose(self) -> None:
        await self._client.aclose()
