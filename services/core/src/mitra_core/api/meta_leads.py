"""Meta Lead Ads webhook (INT-01): one app-wide endpoint for every connected Facebook page.

* ``GET /webhooks/meta/leadgen``: Meta's subscription check (``hub.verify_token``).
* ``POST /webhooks/meta/leadgen``: ``X-Hub-Signature-256`` = HMAC-SHA256 of the raw body with
  the app secret. Each ``leadgen`` change names a page and a lead id; the page maps to its
  business (SECURITY DEFINER ``lead_source_business``), the lead is fetched through the
  provider (simulator by default) and goes through the normal intake.

Meta retries anything but a 200, so per-lead problems are recorded on the source (shown to the
owner) and the request still answers 200. Only a bad signature is refused.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, text

from mitra_core.api.lead_intake import MAX_BODY, accept, intake_deps
from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_sessionmaker
from mitra_core.errors import AppError
from mitra_core.leads.adapters import AdapterError, parse_meta_lead
from mitra_core.leads.enums import LeadSourceKind
from mitra_core.leads.providers import MetaLeadsProvider, ProviderError, get_meta_provider
from mitra_core.leads.service import IntakeDeps
from mitra_core.logging import get_logger
from mitra_core.models import LeadSource
from mitra_core.tenancy import TenantContext, set_tenant

log = get_logger(__name__)
router = APIRouter(prefix="/webhooks/meta", tags=["lead intake"])

_BY_PAGE = text("SELECT lead_source_business('meta', :page)")


def meta_provider(settings: Settings = Depends(get_settings)) -> MetaLeadsProvider:
    return get_meta_provider(settings)


@router.get("/leadgen", response_class=PlainTextResponse, include_in_schema=False)
async def verify_subscription(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge", max_length=200),
    settings: Settings = Depends(get_settings),
) -> str:
    expected = settings.meta_verify_token.get_secret_value()
    if mode != "subscribe" or not expected or not hmac.compare_digest(token, expected):
        raise AppError(403, "forbidden", "Verification failed")
    return challenge


def signature_ok(secret: str, header: str, body: bytes) -> bool:
    if not secret or not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], digest)


def leadgen_changes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            if (
                change.get("field") == "leadgen"
                and value.get("leadgen_id")
                and value.get("page_id")
            ):
                out.append(value)
    return out


@router.post("/leadgen", include_in_schema=False)
async def receive_leadgen(
    request: Request,
    background: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
    provider: MetaLeadsProvider = Depends(meta_provider),
) -> dict[str, int]:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise AppError(413, "payload_too_large", "Payload is too large")
    header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_ok(settings.meta_app_secret.get_secret_value(), header, raw):
        raise AppError(401, "unauthenticated", "Bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise AppError(422, "validation_error", "Body must be JSON") from None
    accepted = 0
    for change in leadgen_changes(payload if isinstance(payload, dict) else {}):
        if await _one(change, background, clock, deps, provider):
            accepted += 1
    return {"accepted": accepted}


async def _one(
    change: dict[str, Any],
    background: BackgroundTasks,
    clock: Clock,
    deps: IntakeDeps,
    provider: MetaLeadsProvider,
) -> bool:
    page_id, leadgen_id = str(change["page_id"])[:64], str(change["leadgen_id"])[:80]
    async with get_sessionmaker()() as session:
        business_id: uuid.UUID | None = (
            await session.execute(_BY_PAGE, {"page": page_id})
        ).scalar_one_or_none()
        if business_id is None:
            log.info("meta.unknown_page")
            return False
        await set_tenant(session, TenantContext(business_id=business_id))
        source = await session.scalar(
            select(LeadSource).where(
                LeadSource.business_id == business_id, LeadSource.kind == LeadSourceKind.META
            )
        )
        token = source.credential if source else None
        try:
            lead = await provider.fetch_lead(leadgen_id, token)
            data = parse_meta_lead(lead)
            await accept(session, business_id, data, now_fn=clock, deps=deps, background=background)
            return True
        except (ProviderError, AdapterError, AppError) as exc:
            await session.rollback()
            message = exc.message if isinstance(exc, AppError) else str(exc)
            await _record_error(business_id, message)
            return False


async def _record_error(business_id: uuid.UUID, message: str) -> None:
    async with get_sessionmaker()() as session:
        await set_tenant(session, TenantContext(business_id=business_id))
        source = await session.scalar(
            select(LeadSource).where(
                LeadSource.business_id == business_id, LeadSource.kind == LeadSourceKind.META
            )
        )
        if source is not None:
            source.last_error = message[:300]
            await session.commit()
