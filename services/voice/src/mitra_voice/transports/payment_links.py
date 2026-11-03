"""After a phone call: hand the payment links the employee promised to core (ACT-05).

Only links the brain accepted (``send_payment_link`` result ``ok``: a grounded amount) are sent.
A link the caller asked for is still sent after "don't call me": it is the service they
requested, not a call. Core decides whether the owner must approve first and WhatsApps it.
"""

from __future__ import annotations

import uuid
from typing import Any

from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.session import CallSession


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


async def send_payment_links(
    core: CoreTelephony, session: CallSession, caller_phone: str, actions: list[dict[str, Any]]
) -> int:
    """Returns how many links were handed to core (idempotent there by ``client_ref``)."""
    links = [
        a
        for a in actions
        if a.get("name") == "send_payment_link" and (a.get("result") or {}).get("ok")
    ]
    ref = "".join(c for c in session.id if c.isalnum() or c in "-_.")[:80] or "call"
    for n, action in enumerate(links, start=1):
        result, args = action["result"], dict(action.get("args") or {})
        await core.send_payment_link(
            {
                "employee_id": session.pack.employee_id,
                "contact_phone": caller_phone,
                "amount_paise": int(result["amount_paise"]),
                "purpose": str(args.get("purpose") or "")[:200],
                "discount_percent": int(args.get("discount_percent") or 0),
                "call_id": session.id if _is_uuid(session.id) else None,
                "client_ref": f"call:{ref}:{n}",
            }
        )
    return len(links)
