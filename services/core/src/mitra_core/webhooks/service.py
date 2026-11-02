"""Outgoing webhooks (INT-13): emit into an outbox, deliver with retries, keep a delivery log.

Any feature can emit::

    from mitra_core.webhooks.service import emit_event
    emit_event(session, business_id, "campaign.finished", {...})  # inside your transaction
    await session.commit()
    background.add_task(deliver_due, business_id)                  # optional: send right away

``emit_event`` makes no network calls; rows are delivered by :func:`deliver_due`, either right
after commit (background task) or by the ``POST /internal/v1/webhooks/run`` job, which also
retries failures: after 1 min, 5 min, 30 min, 2 h, 6 h and 24 h, then the delivery is FAILED.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.db import tenant_session
from mitra_core.logging import get_logger
from mitra_core.models import WebhookDelivery, WebhookEndpoint
from mitra_core.tenancy import TenantContext
from mitra_core.webhooks import sender as sender_mod
from mitra_core.webhooks import signing
from mitra_core.webhooks.enums import SUBSCRIBABLE, DeliveryStatus, WebhookEvent
from mitra_core.webhooks.sender import SendResult, WebhookSender

log = get_logger(__name__)

RETRY_DELAYS = (60, 300, 1800, 7200, 21600, 86400)  # seconds after attempt 1, 2, ...
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
BATCH = 50
USER_AGENT = "Mitra-Webhooks/1.0"


def _now() -> datetime:
    return datetime.now(UTC)


def envelope(
    event_id: uuid.UUID, event: str, business_id: uuid.UUID, data: dict[str, Any], at: datetime
) -> dict[str, Any]:
    return {
        "id": str(event_id),
        "event": event,
        "created_at": at.isoformat(),
        "business_id": str(business_id),
        "data": data,
    }


async def emit_event(
    session: AsyncSession,
    business_id: uuid.UUID,
    event: str,
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[WebhookDelivery]:
    """Queue ``event`` for every enabled endpoint subscribed to it. The caller commits."""
    if event not in {e.value for e in SUBSCRIBABLE}:
        raise ValueError(f"Unknown webhook event: {event}")
    at = now or _now()
    endpoints = await session.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.business_id == business_id,
            WebhookEndpoint.enabled.is_(True),
            WebhookEndpoint.events.contains([event]),
        )
    )
    event_id = uuid.uuid4()
    body = envelope(event_id, event, business_id, payload, at)
    rows = [_delivery(business_id, ep.id, event_id, event, body, at) for ep in endpoints]
    session.add_all(rows)
    return rows


def _delivery(
    business_id: uuid.UUID,
    endpoint_id: uuid.UUID,
    event_id: uuid.UUID,
    event: str,
    body: dict[str, Any],
    at: datetime,
) -> WebhookDelivery:
    return WebhookDelivery(
        id=uuid.uuid4(),
        business_id=business_id,
        endpoint_id=endpoint_id,
        event_id=event_id,
        event=event,
        payload=body,
        status=DeliveryStatus.PENDING.value,
        attempts=0,
        next_attempt_at=at,
        created_at=at,
    )


def test_delivery(endpoint: WebhookEndpoint, at: datetime) -> WebhookDelivery:
    data = {"message": "This is a test event from Mitra. Your webhook is connected."}
    event_id = uuid.uuid4()
    body = envelope(event_id, WebhookEvent.TEST.value, endpoint.business_id, data, at)
    return _delivery(endpoint.business_id, endpoint.id, event_id, WebhookEvent.TEST, body, at)


def request_for(
    endpoint: WebhookEndpoint, delivery: WebhookDelivery, at: datetime
) -> tuple[dict[str, str], bytes]:
    body = json.dumps(delivery.payload, separators=(",", ":"), ensure_ascii=False).encode()
    timestamp = int(at.timestamp())
    headers = {str(k): str(v) for k, v in (endpoint.headers or {}).items()}
    headers.update(
        {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Mitra-Event": delivery.event,
            "X-Mitra-Event-Id": str(delivery.event_id),
            "X-Mitra-Delivery": str(delivery.id),
            "X-Mitra-Timestamp": str(timestamp),
            signing.SIGNATURE_HEADER: signing.header_value(endpoint.secret, timestamp, body),
        }
    )
    return headers, body


def record_result(
    endpoint: WebhookEndpoint, delivery: WebhookDelivery, result: SendResult, at: datetime
) -> None:
    delivery.attempts += 1
    delivery.last_attempt_at = at
    delivery.response_status = result.status
    delivery.duration_ms = result.duration_ms
    delivery.error = result.error[:300] if result.error else None
    if result.ok:
        delivery.status = DeliveryStatus.SUCCEEDED.value
        delivery.next_attempt_at = None
        endpoint.consecutive_failures = 0
        return
    endpoint.consecutive_failures += 1
    if delivery.event == WebhookEvent.TEST or delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = DeliveryStatus.FAILED.value
        delivery.next_attempt_at = None
    else:
        delivery.next_attempt_at = at + timedelta(seconds=RETRY_DELAYS[delivery.attempts - 1])


async def attempt(
    endpoint: WebhookEndpoint, delivery: WebhookDelivery, sender: WebhookSender, at: datetime
) -> SendResult:
    headers, body = request_for(endpoint, delivery, at)
    result = await sender.send(endpoint.url, headers, body)
    record_result(endpoint, delivery, result, at)
    return result


async def deliver_due_in(
    session: AsyncSession, business_id: uuid.UUID, sender: WebhookSender, now: datetime
) -> int:
    """Deliver due rows one by one, committing after each (a crash loses at most one try)."""
    ids = list(
        await session.scalars(
            select(WebhookDelivery.id)
            .where(
                WebhookDelivery.business_id == business_id,
                WebhookDelivery.status == DeliveryStatus.PENDING.value,
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(BATCH)
        )
    )
    sent = 0
    for delivery_id in ids:
        delivery = await session.scalar(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.status == DeliveryStatus.PENDING.value,
            )
            .with_for_update(skip_locked=True)
        )
        if delivery is None:  # taken by a concurrent run
            await session.commit()
            continue
        endpoint = await session.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None or not endpoint.enabled:
            delivery.status = DeliveryStatus.FAILED.value
            delivery.error = "Webhook is switched off"
            delivery.next_attempt_at = None
        else:
            await attempt(endpoint, delivery, sender, now)
            sent += 1
        await session.commit()
    return sent


async def deliver_due(
    business_id: uuid.UUID, sender: WebhookSender | None = None, now: datetime | None = None
) -> int:
    """Background-task entry: never raises."""
    try:
        async with tenant_session(TenantContext(business_id=business_id)) as session:
            return await deliver_due_in(
                session, business_id, sender or sender_mod.default_sender(), now or _now()
            )
    except Exception as exc:
        log.error(
            "webhooks.deliver_failed", business_id=str(business_id), exc_type=type(exc).__name__
        )
        return 0
