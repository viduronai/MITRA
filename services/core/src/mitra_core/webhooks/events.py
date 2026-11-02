"""Payloads for Mitra's own events, and the ``call.ended`` hook on the call-end flow.

Payloads carry ids, results and the last 4 digits of a phone number, never the full number
(Mitra does not keep it; the business's own system already has it).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from mitra_core.db import tenant_session
from mitra_core.logging import get_logger
from mitra_core.models import Call, Lead
from mitra_core.models.enums import CallDirection
from mitra_core.tenancy import TenantContext
from mitra_core.webhooks.enums import WebhookEvent
from mitra_core.webhooks.sender import WebhookSender
from mitra_core.webhooks.service import deliver_due, emit_event

log = get_logger(__name__)


def call_ended_payload(call: Call) -> dict[str, Any]:
    return {
        "call_id": str(call.id),
        "employee_id": str(call.employee_id) if call.employee_id else None,
        "contact_id": str(call.contact_id) if call.contact_id else None,
        "direction": call.direction.value,
        "status": call.status.value,
        "phone_last4": call.phone_last4,
        "language": call.language.value if call.language else None,
        "started_at": call.started_at.isoformat(),
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": call.duration_seconds,
        "result": call.result.value if call.result else None,
        "summary": call.summary,
        "next_step": call.next_step,
        "fields": call.fields or {},
        "recording_url": None,  # TODO(recordings): signed, short-lived URL once S3 exists
    }


def lead_created_payload(lead: Lead) -> dict[str, Any]:
    return {
        "lead_id": str(lead.id),
        "source": lead.source,
        "source_detail": lead.source_detail,
        "external_id": lead.external_id,
        "contact_id": str(lead.contact_id) if lead.contact_id else None,
        "name": lead.name,
        "phone_last4": lead.phone_last4,
        "fields": lead.fields or {},
        "status": lead.status,
        "call_at": lead.call_at.isoformat() if lead.call_at else None,
        "received_at": lead.received_at.isoformat(),
    }


async def call_ended(
    call_id: uuid.UUID, business_id: uuid.UUID, sender: WebhookSender | None = None
) -> None:
    """Background task queued after post-call processing, so the summary and result are in.

    Browser test calls are skipped. Never raises: the call flow must not depend on webhooks.
    """
    try:
        async with tenant_session(TenantContext(business_id=business_id)) as session:
            call = await session.scalar(
                select(Call).where(Call.id == call_id, Call.business_id == business_id)
            )
            if call is None or call.direction == CallDirection.WEB:
                return
            rows = await emit_event(
                session, business_id, WebhookEvent.CALL_ENDED, call_ended_payload(call)
            )
            await session.commit()
        if rows:
            await deliver_due(business_id, sender)
    except Exception as exc:
        log.error("webhooks.call_ended_failed", call_id=str(call_id), exc_type=type(exc).__name__)
