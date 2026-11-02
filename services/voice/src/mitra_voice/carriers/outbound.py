"""Place one outbound call: compliance first, then the carrier (WORKFLOWS sections 2, 11b, 12).

``Queued -> ComplianceCheck -> Blocked | Dialing``: core's ``compliance.check`` decides and picks
the caller ID; a blocked or deferred call is never dialled. The attempt is recorded before
dialling (frequency caps count it even if the carrier fails). If the primary carrier is down the
secondary carrier is tried once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from mitra_voice.carriers.base import (
    Carrier,
    CarrierError,
    OutboundIntent,
    OutboundRegistry,
    PlacedCall,
    Purpose,
)
from mitra_voice.carriers.core_api import CoreTelephony

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DialRequest:
    business_id: str
    employee_id: str
    contact_phone: str
    purpose: Purpose
    number_id: str | None = None
    called_number_id: str | None = None
    caller_id: str | None = None  # only without core (local sim): nothing checks it


@dataclass(frozen=True, slots=True)
class DialResult:
    decision: str  # allow | block | defer
    reasons: list[dict[str, Any]] = field(default_factory=list)
    defer_until: str | None = None
    call: PlacedCall | None = None
    caller_id: str | None = None
    intent: OutboundIntent | None = None


async def dial(
    req: DialRequest,
    *,
    carrier: Carrier,
    registry: OutboundRegistry,
    core: CoreTelephony | None,
    fallback: Carrier | None = None,
) -> DialResult:
    if core is None:
        if carrier.name != "sim":
            raise CarrierError("real carriers need services/core for compliance checks")
        caller_id, number_id = req.caller_id or "+910000000000", req.number_id
        attempt_id = None
    else:
        check = await core.compliance_check(
            {
                "business_id": req.business_id,
                "contact_phone": req.contact_phone,
                "purpose": req.purpose,
                "number_id": req.number_id,
                "called_number_id": req.called_number_id,
            }
        )
        if not check["allowed"]:
            return DialResult(
                decision=check["decision"],
                reasons=check["reasons"],
                defer_until=check.get("defer_until"),
            )
        caller_id = check["caller_id"]["e164"]
        number_id = check["caller_id"]["phone_number_id"]
        attempt_id = await core.record_attempt(
            {
                "business_id": req.business_id,
                "contact_phone": req.contact_phone,
                "purpose": req.purpose,
                "phone_number_id": number_id,
            }
        )

    intent = OutboundIntent(
        business_id=req.business_id,
        employee_id=req.employee_id,
        contact_phone=req.contact_phone,
        caller_id=caller_id,
        purpose=req.purpose,
        phone_number_id=number_id,
        attempt_id=attempt_id,
    )
    try:
        placed = await place_intent(intent, carrier=carrier, registry=registry, fallback=fallback)
    except CarrierError:
        if core is not None and attempt_id is not None:
            await core.set_outcome(attempt_id, req.business_id, "failed")
        raise
    return DialResult(decision="allow", call=placed, caller_id=caller_id, intent=intent)


async def place_intent(
    intent: OutboundIntent,
    *,
    carrier: Carrier,
    registry: OutboundRegistry,
    fallback: Carrier | None = None,
) -> PlacedCall:
    """Primary carrier, then the secondary once; the placed call is registered for routing."""
    placed: PlacedCall | None = None
    for option in (carrier, fallback):
        if option is None:
            continue
        try:
            placed = await option.place_call(intent)
            break
        except CarrierError as e:
            log.warning("outbound.carrier_failed", carrier=option.name, error=str(e))
    if placed is None:
        raise CarrierError("no carrier could place the call")
    registry.add(placed.call_sid, intent)
    log.info("outbound.placed", carrier=placed.carrier, call_sid=placed.call_sid)
    return placed
