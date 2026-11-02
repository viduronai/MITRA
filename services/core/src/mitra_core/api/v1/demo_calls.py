"""Public "Call me now" demo calls from the marketing site (07-SCREENS §2.3 #3).

No auth: anyone on the landing page can ask Mitra to call them. Abuse is bounded by the
``demo_call_request`` SECURITY DEFINER function (migration 0004), which rate-limits per phone
and per client IP. The phone number and IP are only ever stored as HMACs.

SIMULATED until the Exotel dialer exists: the request is recorded and answered with
``simulated: true``; nothing is dialled.

The client IP is ``request.client.host``. Behind a proxy, run uvicorn with ``--proxy-headers``
and ``--forwarded-allow-ips`` set to the proxy so this is the visitor's address, not the proxy's.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError
from mitra_core.pii import hash_ip, hash_phone, phone_last4
from mitra_core.schemas.demo_call import DemoCallIn, DemoCallOut

router = APIRouter(prefix="/demo-calls", tags=["demo calls"])

_REQUEST = text(
    "SELECT outcome, retry_after FROM demo_call_request("
    ":id, :phone_hash, :last4, :ip_hash, :language, :industry, "
    ":max_phone, :phone_window, :max_ip, :ip_window)"
)
_ETA_SECONDS = 30
_LIMIT_MESSAGES = {
    "phone_limited": "This number already had a demo call today. Please try again later.",
    "ip_limited": "Too many demo calls requested from this network. Please try again later.",
}


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DemoCallOut,
    summary="Ask Mitra to call a phone with a live demo (public, rate-limited, simulated)",
)
async def create_demo_call(
    body: DemoCallIn,
    request: Request,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> DemoCallOut:
    client_ip = request.client.host if request.client else "unknown"
    call_id = uuid.uuid4()
    row = (
        await session.execute(
            _REQUEST,
            {
                "id": call_id,
                "phone_hash": hash_phone(body.phone),
                "last4": phone_last4(body.phone),
                "ip_hash": hash_ip(client_ip),
                "language": body.language.value,
                "industry": body.industry,
                "max_phone": settings.demo_call_max_per_phone,
                "phone_window": settings.demo_call_phone_window_seconds,
                "max_ip": settings.demo_call_max_per_ip,
                "ip_window": settings.demo_call_ip_window_seconds,
            },
        )
    ).one()
    await session.commit()
    if row.outcome in _LIMIT_MESSAGES:
        raise AppError(
            429,
            "rate_limited",
            _LIMIT_MESSAGES[row.outcome],
            details={"reason": row.outcome, "retry_after": row.retry_after},
            headers={"Retry-After": str(row.retry_after)},
        )
    # TODO(telephony): hand the number to the Exotel dialer queue (in memory only, never
    # persisted) and expose GET /v1/demo-calls/{id} for live status.
    return DemoCallOut(
        id=call_id,
        status="queued",
        phone_last4=phone_last4(body.phone),
        eta_seconds=_ETA_SECONDS,
        simulated=True,
    )
