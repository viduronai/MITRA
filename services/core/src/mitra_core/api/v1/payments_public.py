"""Unauthenticated payment endpoints: the business's Razorpay webhook and the local simulator.

* ``POST /v1/payments/webhooks/razorpay/{token}``: signature-verified with that business's own
  webhook secret, idempotent (``payments.webhook``).
* ``GET /v1/payments/sim/{link_id}`` and ``POST .../{pay|fail}``: a stand-in for Razorpay's
  hosted payment page, so the whole flow works without accounts. The buttons build a
  Razorpay-shaped event, sign it with the business's webhook secret and run it through the same
  webhook code. Only when ``MITRA_COLLECTIONS_PROVIDER=sim`` outside staging/prod.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError
from mitra_core.models import Business, PaymentRequest
from mitra_core.payments import service, webhook
from mitra_core.payments.messages import rupees
from mitra_core.payments.settings import get_settings_row, webhook_secret_for
from mitra_core.tenancy import TenantContext, set_tenant

router = APIRouter(prefix="/payments", tags=["payments"], include_in_schema=False)
_LINK_LOOKUP = text("SELECT payments_link_business(:link_id)")


@router.post("/webhooks/razorpay/{token}", summary="Razorpay Payment Links webhook")
async def razorpay_webhook(
    token: str,
    request: Request,
    signature: str = Header("", alias="X-Razorpay-Signature"),
    event_id: str | None = Header(None, alias="X-Razorpay-Event-Id"),
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
) -> dict[str, str]:
    raw = await request.body()
    outcome = await webhook.handle(
        session, token=token, raw=raw, signature=signature, event_id=event_id, now=clock()
    )
    await session.commit()
    return {"status": outcome}


def _require_sim(settings: Settings) -> None:
    if settings.collections_provider != "sim" or settings.env in {"staging", "prod"}:
        raise AppError(404, "not_found", "Not found")


async def _sim_request(session: AsyncSession, link_id: str, now: datetime) -> PaymentRequest:
    business_id = (await session.execute(_LINK_LOOKUP, {"link_id": link_id[:64]})).scalar()
    if business_id is None:
        raise AppError(404, "not_found", "Unknown payment link")
    await set_tenant(session, TenantContext(business_id=business_id))
    req = await session.scalar(
        select(PaymentRequest).where(
            PaymentRequest.business_id == business_id, PaymentRequest.provider_link_id == link_id
        )
    )
    if req is None:  # pragma: no cover - the lookup just found it
        raise AppError(404, "not_found", "Unknown payment link")
    if req.expires_at is not None and req.expires_at <= now and req.status in ("sent", "failed"):
        await service.mark_expired(session, req, now=now)  # as Razorpay's page would show it
        await session.commit()
    return req


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pay {business} (simulator)</title>
<style>body{{font-family:system-ui,sans-serif;max-width:420px;margin:40px auto;padding:0 16px;
color:#1f2328}}.card{{border:1px solid #d0d7de;border-radius:12px;padding:20px}}
.amt{{font-size:32px;font-weight:600;margin:8px 0}}.note{{color:#656d76;font-size:14px}}
button{{font-size:16px;padding:12px;border-radius:8px;border:0;width:100%;margin-top:10px;
cursor:pointer}}.pay{{background:#1a7f37;color:#fff}}.fail{{background:#eaeef2;color:#cf222e}}
</style></head><body><div class="card">
<p class="note">Payment Links simulator · no real money moves</p>
<h1 style="font-size:20px;margin:0">{business}</h1><p>{purpose}</p>
<div class="amt">{amount}</div><p class="note">Status: <b>{status}</b></p>{actions}
</div></body></html>"""
_ACTIONS = """<form method="post" action="{base}/pay"><button class="pay">Pay with UPI</button>
</form><form method="post" action="{base}/fail"><button class="fail">Make it fail</button></form>"""


@router.get("/sim/{link_id}", response_class=HTMLResponse, summary="Simulated payment page")
async def sim_page(
    link_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> HTMLResponse:
    _require_sim(settings)
    req = await _sim_request(session, link_id, clock())
    business = await session.scalar(select(Business.name).where(Business.id == req.business_id))
    payable = req.status in ("sent", "failed")
    base = f"/v1/payments/sim/{html.escape(link_id)}"
    page = _PAGE.format(
        business=html.escape(business or ""),
        purpose=html.escape(req.purpose),
        amount=html.escape(rupees(req.amount_paise)),
        status=html.escape(req.status),
        actions=_ACTIONS.format(base=base) if payable else "",
    )
    return HTMLResponse(page)


@router.post("/sim/{link_id}/{outcome}", response_class=HTMLResponse, summary="Simulate payment")
async def sim_pay(
    link_id: str,
    outcome: Literal["pay", "fail"],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> HTMLResponse:
    _require_sim(settings)
    now = clock()
    req = await _sim_request(session, link_id, now)
    if req.status not in ("sent", "failed"):
        raise AppError(409, "not_payable", f"This payment link is {req.status}")
    row = await get_settings_row(session, req.business_id)
    secret = webhook_secret_for(row)
    if not secret:
        raise AppError(409, "collections_not_connected", "Razorpay is not connected")
    raw, signature, event_id = webhook.simulated_event(req, outcome, secret=secret, now=now)
    result = await webhook.handle(
        session, token=row.webhook_token, raw=raw, signature=signature, event_id=event_id, now=now
    )
    await session.commit()
    message = (
        "Payment received. You can close this page."
        if result == "paid"
        else ("The payment failed (simulated). You can try again from the link.")
    )
    return HTMLResponse(
        f'<!doctype html><meta charset="utf-8"><p style="font-family:system-ui;margin:40px">'
        f'{html.escape(message)} <a href="/v1/payments/sim/{html.escape(link_id)}">Back</a></p>'
    )
