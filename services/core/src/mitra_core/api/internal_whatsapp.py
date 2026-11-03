"""Internal WhatsApp API for the voice service (``/internal/v1/whatsapp``), service-token auth.

* ``POST /sends`` — after a phone call, the WhatsApp messages the AI employee promised:
  booking confirmation, location, a document, a follow-up. The voice service names the message;
  core picks every link from the business's confirmed knowledge (``manager.customer_sends``)
  and sends through the 24-hour-window entry point. Idempotent by ``client_ref``.

Tenancy as in ``internal_calls``: the employee id maps to its business through the SECURITY
DEFINER lookup, then everything goes through RLS.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.api.internal import require_service
from mitra_core.api.internal_calls import _bind_employee_tenant
from mitra_core.db import get_session
from mitra_core.manager.customer_sends import send_from_call
from mitra_core.schemas.manager import InternalWhatsAppSendIn, InternalWhatsAppSendOut

router = APIRouter(
    prefix="/internal/v1/whatsapp",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_service)],
)


@router.post("/sends", response_model=InternalWhatsAppSendOut, status_code=status.HTTP_201_CREATED)
async def send(
    body: InternalWhatsAppSendIn, session: AsyncSession = Depends(get_session)
) -> InternalWhatsAppSendOut:
    business_id = await _bind_employee_tenant(session, body.employee_id)
    result = await send_from_call(
        session,
        business_id,
        to_phone=body.contact_phone,
        kind=body.kind,
        client_ref=body.client_ref,
        document=body.document,
        topic=body.topic,
        when=body.when,
    )
    out = InternalWhatsAppSendOut(status=result)
    await session.commit()
    return out
