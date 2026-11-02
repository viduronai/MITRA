"""Public lead intake (INT-12) and source adapters (INT-01/02/03/06/14). No user auth.

* ``POST /lead-intake/{slug}``: generic JSON (own code, Sheets/Forms Apps Script, Zapier, Make,
  Pabbly, n8n). Secret in the ``X-Mitra-Secret`` header.
* ``POST /lead-intake/{slug}/google-ads``: Google Ads lead form webhook (secret = ``google_key``).
* ``POST /lead-intake/{slug}/indiamart`` and ``/justdial``: portal push (secret in the header or,
  because portals cannot add headers, the ``key`` query parameter; access logs never contain
  query strings).
* ``POST /lead-intake/{slug}/form``: the website form snippet. A browser cannot keep a secret, so
  this works only while the owner has the website form switched on, needs the consent box ticked,
  has a honeypot field and is rate-limited per client IP.

Every endpoint answers 202 quickly; the call is queued on the dialer. Unknown slug and wrong
secret get the same 401, so slugs cannot be probed.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError, not_found
from mitra_core.leads import adapters
from mitra_core.leads.adapters import AdapterError, LeadInput
from mitra_core.leads.calling import HeadsUp, LeadDialer, get_heads_up, get_lead_dialer
from mitra_core.leads.enums import LeadSourceKind, LeadStatus
from mitra_core.leads.intake import SECRET_HEADER, get_intake, hash_secret
from mitra_core.leads.service import IntakeDeps, IntakeResult, check_ip_rate, check_rate, ingest
from mitra_core.leads.service import source_for as get_source
from mitra_core.models import Business
from mitra_core.pii import hash_ip
from mitra_core.schemas.leads import IntakeOut
from mitra_core.telephony.dnd import DndProvider, get_dnd_provider
from mitra_core.tenancy import TenantContext, set_tenant
from mitra_core.webhooks.service import deliver_due

router = APIRouter(prefix="/lead-intake", tags=["lead intake"])

MAX_BODY = 64 * 1024
_BY_SECRET = text("SELECT lead_intake_business(:slug, :hash)")
_BY_FORM = text("SELECT lead_intake_form_business(:slug)")
_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "600",
}
_BAD_SECRET = AppError(401, "unauthenticated", "Unknown intake URL or wrong secret")


def intake_deps(
    settings: Settings = Depends(get_settings),
    dialer: LeadDialer = Depends(get_lead_dialer),
    heads_up: HeadsUp = Depends(get_heads_up),
    dnd: DndProvider = Depends(get_dnd_provider),
) -> IntakeDeps:
    return IntakeDeps(settings=settings, dialer=dialer, heads_up=heads_up, dnd=dnd)


async def read_body(request: Request) -> dict[str, Any]:
    """JSON object or form fields (urlencoded); anything else is a 422."""
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise AppError(413, "payload_too_large", "Lead payload is too large")
    ctype = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in ctype:
        return dict(parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True))
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        raise AppError(422, "validation_error", "Body must be a JSON object") from None
    if not isinstance(data, dict):
        raise AppError(422, "validation_error", "Body must be a JSON object")
    return data


async def _business_by_secret(session: AsyncSession, slug: str, secret: str | None) -> uuid.UUID:
    if not secret or len(secret) > 200 or len(slug) > 40:
        raise _BAD_SECRET
    found = (
        await session.execute(_BY_SECRET, {"slug": slug, "hash": hash_secret(secret)})
    ).scalar_one_or_none()
    if found is None:
        raise _BAD_SECRET
    return found  # type: ignore[no-any-return]


def _parse(parser: Callable[[Mapping[str, Any]], LeadInput], body: Mapping[str, Any]) -> LeadInput:
    try:
        return parser(body)
    except AdapterError as exc:
        raise AppError(422, "invalid_lead", str(exc)) from None


async def accept(
    session: AsyncSession,
    business_id: uuid.UUID,
    data: LeadInput,
    *,
    now_fn: Clock,
    deps: IntakeDeps,
    background: BackgroundTasks,
    ip_hash: str | None = None,
) -> IntakeResult:
    """Shared by every adapter: bind the tenant, rate-limit, ingest, commit, send webhooks."""
    await set_tenant(session, TenantContext(business_id=business_id))
    business = await session.get(Business, business_id)
    intake = await get_intake(session, business_id)
    if business is None or intake is None:
        raise not_found("Business")
    now = now_fn()
    await check_rate(session, business_id, now, deps.settings)
    if ip_hash is not None:
        await check_ip_rate(
            session, business_id, ip_hash, now, deps.settings.lead_form_max_per_ip_hour
        )
    source = await get_source(session, business_id, data.source)
    if not source.enabled:
        raise AppError(409, "source_disabled", "This lead source is switched off in Mitra")
    result = await ingest(
        session, business, intake, source, data, now=now, deps=deps, ip_hash=ip_hash
    )
    await session.commit()
    if result.webhooks:
        background.add_task(deliver_due, business_id, None, now)
    return result


def _out(result: IntakeResult) -> IntakeOut:
    lead = result.lead
    return IntakeOut(
        lead_id=lead.id,
        status=LeadStatus(lead.status),
        duplicate=result.duplicate,
        call_at=lead.call_at,
    )


@router.post("/{slug}", status_code=202, response_model=IntakeOut, summary="Send a lead")
async def intake_generic(
    slug: str,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
) -> IntakeOut:
    business_id = await _business_by_secret(session, slug, request.headers.get(SECRET_HEADER))
    body = await read_body(request)
    data = _parse(lambda b: adapters.parse_generic(b, LeadSourceKind.API), body)
    return _out(
        await accept(session, business_id, data, now_fn=clock, deps=deps, background=background)
    )


@router.post("/{slug}/google-ads", status_code=202, response_model=IntakeOut)
async def intake_google_ads(
    slug: str,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
) -> IntakeOut:
    body = await read_body(request)
    key = body.get("google_key")
    business_id = await _business_by_secret(session, slug, key if isinstance(key, str) else None)
    data = _parse(adapters.parse_google_ads, body)
    return _out(
        await accept(session, business_id, data, now_fn=clock, deps=deps, background=background)
    )


async def _portal(
    slug: str,
    request: Request,
    key: str | None,
    parser: Callable[[Mapping[str, Any]], LeadInput],
    background: BackgroundTasks,
    session: AsyncSession,
    clock: Clock,
    deps: IntakeDeps,
) -> IntakeOut:
    secret = request.headers.get(SECRET_HEADER) or key
    business_id = await _business_by_secret(session, slug, secret)
    body = await read_body(request) if request.method == "POST" else {}
    params = {k: v for k, v in request.query_params.items() if k != "key"}
    data = _parse(parser, {**params, **body})
    return _out(
        await accept(session, business_id, data, now_fn=clock, deps=deps, background=background)
    )


@router.post("/{slug}/indiamart", status_code=202, response_model=IntakeOut)
async def intake_indiamart(
    slug: str,
    request: Request,
    background: BackgroundTasks,
    key: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
) -> IntakeOut:
    return await _portal(
        slug, request, key, adapters.parse_indiamart_push, background, session, clock, deps
    )


@router.post("/{slug}/justdial", status_code=202, response_model=IntakeOut)
@router.get(
    "/{slug}/justdial",
    status_code=202,
    response_model=IntakeOut,
    operation_id="intake_justdial_get",
    summary="JustDial push as query parameters",
)
async def intake_justdial(
    slug: str,
    request: Request,
    background: BackgroundTasks,
    key: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
) -> IntakeOut:
    return await _portal(
        slug, request, key, adapters.parse_justdial, background, session, clock, deps
    )


@router.options("/{slug}/form", include_in_schema=False)
async def form_preflight(slug: str) -> Response:
    return Response(status_code=204, headers=_CORS)


@router.post("/{slug}/form", status_code=202, summary="Website form snippet (no secret)")
async def intake_form(
    slug: str,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    deps: IntakeDeps = Depends(intake_deps),
) -> JSONResponse:
    try:
        body = await read_body(request)
        if str(body.get("website") or "").strip():  # honeypot: humans never fill it
            return JSONResponse({"status": "received"}, 202, headers=_CORS)
        if adapters.consent_value(body.get("consent")) is not True:
            raise AppError(422, "consent_required", "Please tick the box to agree to a call back")
        business_id = (await session.execute(_BY_FORM, {"slug": slug[:40]})).scalar_one_or_none()
        if business_id is None:
            raise AppError(404, "not_found", "This form is not connected to Mitra")
        data = _parse(lambda b: adapters.parse_generic(b, LeadSourceKind.API), body)
        data.source = LeadSourceKind.WEBSITE_FORM
        data.consent = True
        client_ip = request.client.host if request.client else "unknown"
        await accept(
            session,
            business_id,
            data,
            now_fn=clock,
            deps=deps,
            background=background,
            ip_hash=hash_ip(client_ip),
        )
    except AppError as exc:
        body_out = {"error": {"code": exc.code, "message": exc.message}}
        return JSONResponse(body_out, exc.status_code, headers={**_CORS, **(exc.headers or {})})
    # The browser only learns that the enquiry arrived (no lead ids for anonymous visitors).
    return JSONResponse({"status": "received"}, 202, headers=_CORS)
