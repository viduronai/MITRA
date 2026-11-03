"""Missed-call numbers (CALL-20): never answer, so the call is free for the caller.

- Plivo: the answer URL returns ``<Hangup reason="rejected"/>`` before any audio, which rejects
  the call unanswered (``plivo_answer`` asks :func:`reject_if_missed_call` first).
- Exotel: the ExoPhone's flow is a Passthru applet pointing at
  ``GET /telephony/exotel/missed-call`` followed by a Hangup, so the call is never picked up.
  Attaching that flow to a number needs Exotel's flow API (``ExotelCarrier.use_missed_call_flow``,
  stubbed until the account exists).
- A media stream that reaches us anyway for a missed-call number (misconfigured flow) is closed
  at once and reported the same way.

Each missed call is reported to core (``POST /internal/v1/telephony/missed-calls``), which queues
the callback through the dialer. Numbers are never logged here.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request

from mitra_voice.carriers.core_api import CoreTelephony, CoreTelephonyError
from mitra_voice.config import Settings
from mitra_voice.transports.routing import exotel_authorized, to_e164

log = structlog.get_logger(__name__)

PLIVO_REJECT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<Response><Hangup reason="rejected"/></Response>'
)


async def report(core: CoreTelephony, to: str, from_: str | None, call_sid: str | None) -> None:
    if not from_:  # withheld caller id: nobody to call back
        log.info("missed_call.no_caller_id")
        return
    try:
        status = await core.report_missed_call(to, from_, call_sid)
    except CoreTelephonyError as e:
        log.warning("missed_call.report_failed", error=str(e))
        return
    log.info("missed_call.reported", status=status)


async def reject_if_missed_call(
    core: CoreTelephony | None, to: str | None, from_: str | None, call_sid: str | None
) -> bool:
    """True (and reported) when ``to`` is a missed-call number: the caller must reject it."""
    if core is None or not to:
        return False
    try:
        resolved = await core.resolve(to, from_)
    except CoreTelephonyError:
        return False  # core down: answer normally rather than drop a real customer
    if resolved is None or not resolved.missed_call:
        return False
    await report(core, to, from_, call_sid)
    return True


def add_missed_call_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/exotel/missed-call", include_in_schema=False)
    async def exotel_missed_call(request: Request) -> dict[str, str]:
        """Exotel Passthru applet (query string: CallSid, CallFrom, CallTo)."""
        if not exotel_authorized(request.headers, settings):
            raise HTTPException(status_code=403, detail="not authorized")
        params = request.query_params
        to = to_e164(params.get("CallTo") or params.get("To"))
        from_ = to_e164(params.get("CallFrom") or params.get("From"))
        core: CoreTelephony | None = request.app.state.telephony.core
        if core is not None and to:
            await report(core, to, from_, params.get("CallSid"))
        return {"status": "ok"}
