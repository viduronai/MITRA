"""Meta WhatsApp Cloud API webhook (``/webhooks/whatsapp``) and the Manager tick (internal).

* ``GET /webhooks/whatsapp`` — Meta's subscription check (``hub.verify_token``).
* ``POST /webhooks/whatsapp`` — inbound messages. The body must carry a valid
  ``X-Hub-Signature-256`` (HMAC with the app secret); unsigned requests are refused, so a
  forged "Approve" tap cannot reach the approval flow. Always answers 200 quickly once the
  signature is valid (Meta retries non-2xx).
* ``POST /internal/v1/manager/tick`` — service-token; sends due morning reports and applies
  approval timeouts. Call it every few minutes (cron / Temporal schedule).
"""

from __future__ import annotations

import hmac
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from mitra_core.api.internal import require_service
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.errors import AppError
from mitra_core.logging import get_logger
from mitra_core.manager.inbound import handle_inbound
from mitra_core.manager.planner import get_planner, get_transcriber
from mitra_core.manager.report import tick
from mitra_core.schemas.manager import TickOut
from mitra_core.whatsapp.inbound import parse_cloud_webhook, verify_signature

log = get_logger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"], include_in_schema=False)
internal_router = APIRouter(
    prefix="/internal/v1/manager",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)
MAX_BODY = 256_000


@router.get("", response_class=PlainTextResponse)
async def verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge", max_length=200),
    settings: Settings = Depends(get_settings),
) -> str:
    expected = settings.whatsapp_verify_token.get_secret_value()
    if mode != "subscribe" or not expected or not hmac.compare_digest(token, expected):
        raise AppError(403, "forbidden", "Verification failed")
    return challenge


@router.post("")
async def receive(
    request: Request,
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> dict[str, int]:
    body = await request.body()
    if len(body) > MAX_BODY:
        raise AppError(413, "too_large", "Payload too large")
    secret = settings.whatsapp_app_secret.get_secret_value()
    if not verify_signature(body, request.headers.get("x-hub-signature-256"), secret):
        raise AppError(401, "invalid_signature", "Invalid signature")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise AppError(400, "bad_request", "Invalid JSON") from exc
    messages = parse_cloud_webhook(payload if isinstance(payload, dict) else {})
    planner, transcriber = get_planner(settings), get_transcriber(settings)
    handled = 0
    for msg in messages:
        try:
            # TODO(whatsapp): download voice-note media (GET /{media_id}) for transcription.
            await handle_inbound(
                msg, provider="cloud", planner=planner, transcriber=transcriber, now=clock()
            )
            handled += 1
        except Exception as exc:
            log.error("whatsapp.inbound_failed", error=type(exc).__name__)
    return {"received": len(messages), "handled": handled}


@internal_router.post("/tick", response_model=TickOut)
async def manager_tick(clock: Clock = Depends(get_clock)) -> TickOut:
    result = await tick(clock())
    return TickOut(reports=result.reports, expired=result.expired)
