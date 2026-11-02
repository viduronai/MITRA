"""Outgoing webhooks settings (INT-13): endpoints, secrets, test event, delivery log."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.clock import Clock, get_clock
from mitra_core.config import Settings, get_settings
from mitra_core.errors import AppError, not_found
from mitra_core.models import WebhookDelivery, WebhookEndpoint
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.webhooks import (
    DeliveryList,
    DeliveryOut,
    WebhookIn,
    WebhookList,
    WebhookOut,
    WebhookPatch,
)
from mitra_core.security import Tenant, get_tenant_session, require_role
from mitra_core.webhooks import service, signing
from mitra_core.webhooks.enums import SUBSCRIBABLE, DeliveryStatus
from mitra_core.webhooks.sender import (
    UnsafeUrlError,
    WebhookSender,
    get_webhook_sender,
    validate_url,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_can_manage = require_role(MemberRole.OWNER, MemberRole.MANAGER)
MAX_ENDPOINTS = 10


def _check_url(url: str, settings: Settings) -> str:
    try:
        return validate_url(url, allow_private=settings.webhook_allow_private_urls)
    except UnsafeUrlError as exc:
        raise AppError(422, "invalid_url", str(exc)) from None


def _out(
    ep: WebhookEndpoint, last: WebhookDelivery | None = None, secret: str | None = None
) -> WebhookOut:
    return WebhookOut(
        id=ep.id,
        url=ep.url,
        description=ep.description,
        events=list(ep.events),
        secret_hint=ep.secret_hint,
        secret=secret,
        headers={str(k): str(v) for k, v in (ep.headers or {}).items()},
        enabled=ep.enabled,
        consecutive_failures=ep.consecutive_failures,
        last_delivery_at=last.last_attempt_at if last else None,
        last_delivery_ok=(last.status == DeliveryStatus.SUCCEEDED) if last else None,
        created_at=ep.created_at,
    )


async def _get(session: AsyncSession, tenant: Tenant, endpoint_id: uuid.UUID) -> WebhookEndpoint:
    ep = await session.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id, WebhookEndpoint.business_id == tenant.business_id
        )
    )
    if ep is None:
        raise not_found("Webhook")
    return ep


async def _last(session: AsyncSession, endpoint_id: uuid.UUID) -> WebhookDelivery | None:
    return await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.endpoint_id == endpoint_id,
            WebhookDelivery.last_attempt_at.is_not(None),
        )
        .order_by(WebhookDelivery.last_attempt_at.desc())
        .limit(1)
    )


@router.get("", response_model=WebhookList)
async def list_webhooks(
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> WebhookList:
    eps = await session.scalars(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.business_id == tenant.business_id)
        .order_by(WebhookEndpoint.created_at, WebhookEndpoint.id)
    )
    items = [_out(ep, await _last(session, ep.id)) for ep in eps]
    return WebhookList(items=items, events=[e.value for e in SUBSCRIBABLE])


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookIn,
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> WebhookOut:
    count = await session.scalar(
        select(func.count())
        .select_from(WebhookEndpoint)
        .where(WebhookEndpoint.business_id == tenant.business_id)
    )
    if (count or 0) >= MAX_ENDPOINTS:
        raise AppError(409, "limit_reached", f"At most {MAX_ENDPOINTS} webhooks per business")
    secret = signing.generate_secret()
    ep = WebhookEndpoint(
        business_id=tenant.business_id,
        url=_check_url(body.url, settings),
        description=body.description,
        events=[e.value for e in body.events],
        secret=secret,
        secret_hint=signing.hint(secret),
        headers=body.headers,
    )
    session.add(ep)
    await session.commit()
    return _out(ep, secret=secret)


@router.patch("/{endpoint_id}", response_model=WebhookOut)
async def update_webhook(
    endpoint_id: uuid.UUID,
    body: WebhookPatch,
    settings: Settings = Depends(get_settings),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> WebhookOut:
    ep = await _get(session, tenant, endpoint_id)
    fields = body.model_fields_set
    if "url" in fields and body.url is not None:
        ep.url = _check_url(body.url, settings)
    if "events" in fields and body.events is not None:
        ep.events = [e.value for e in body.events]
    if "description" in fields:
        ep.description = body.description
    if "headers" in fields and body.headers is not None:
        ep.headers = body.headers
    if "enabled" in fields and body.enabled is not None:
        ep.enabled = body.enabled
        if body.enabled:
            ep.consecutive_failures = 0
    await session.commit()
    return _out(ep, await _last(session, ep.id))


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    endpoint_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    ep = await _get(session, tenant, endpoint_id)
    await session.delete(ep)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{endpoint_id}/rotate-secret", response_model=WebhookOut)
async def rotate_webhook_secret(
    endpoint_id: uuid.UUID,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> WebhookOut:
    ep = await _get(session, tenant, endpoint_id)
    secret = signing.generate_secret()
    ep.secret, ep.secret_hint = secret, signing.hint(secret)
    await session.commit()
    return _out(ep, await _last(session, ep.id), secret=secret)


def delivery_out(d: WebhookDelivery) -> DeliveryOut:
    return DeliveryOut.model_validate(d)


@router.post("/{endpoint_id}/test", response_model=DeliveryOut, summary="Send test event now")
async def send_test(
    endpoint_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    sender: WebhookSender = Depends(get_webhook_sender),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> DeliveryOut:
    ep = await _get(session, tenant, endpoint_id)
    now = clock()
    delivery = service.test_delivery(ep, now)
    session.add(delivery)
    await service.attempt(ep, delivery, sender, now)
    await session.commit()
    return delivery_out(delivery)


@router.get("/{endpoint_id}/deliveries", response_model=DeliveryList, summary="Delivery log")
async def list_deliveries(
    endpoint_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> DeliveryList:
    await _get(session, tenant, endpoint_id)
    rows = await session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id)
        .limit(limit)
    )
    return DeliveryList(items=[delivery_out(d) for d in rows])


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryOut)
async def retry_delivery(
    delivery_id: uuid.UUID,
    clock: Clock = Depends(get_clock),
    sender: WebhookSender = Depends(get_webhook_sender),
    tenant: Tenant = Depends(_can_manage),
    session: AsyncSession = Depends(get_tenant_session),
) -> DeliveryOut:
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.id == delivery_id,
            WebhookDelivery.business_id == tenant.business_id,
        )
        .with_for_update()
    )
    if delivery is None:
        raise not_found("Delivery")
    if delivery.status == DeliveryStatus.SUCCEEDED:
        raise AppError(409, "conflict", "This delivery already succeeded")
    ep = await _get(session, tenant, delivery.endpoint_id)
    # A manual resend is one extra try; it does not reset the automatic retry ladder.
    delivery.status = DeliveryStatus.PENDING.value
    await service.attempt(ep, delivery, sender, clock())
    await session.commit()
    return delivery_out(delivery)
