"""After a phone call: hand the WhatsApp messages the employee promised to core (ACT-02).

Only messages the brain accepted (``send_whatsapp_template`` result ``ok``) are sent. Core picks
every link from the business's confirmed knowledge and applies WhatsApp's 24-hour rule.
Idempotent in core by ``client_ref`` (``call:<call id>:wa:<n>``).
"""

from __future__ import annotations

from typing import Any

from mitra_voice.carriers.core_api import CoreTelephony
from mitra_voice.session import CallSession
from mitra_voice.transports.payment_links import _is_uuid


async def send_whatsapp_messages(
    core: CoreTelephony, session: CallSession, caller_phone: str, actions: list[dict[str, Any]]
) -> int:
    """Returns how many messages were handed to core."""
    accepted = [
        a
        for a in actions
        if a.get("name") == "send_whatsapp_template" and (a.get("result") or {}).get("ok")
    ]
    ref = "".join(c for c in session.id if c.isalnum() or c in "-_.")[:80] or "call"
    for n, action in enumerate(accepted, start=1):
        result = action["result"]
        body: dict[str, Any] = {
            "employee_id": session.pack.employee_id,
            "contact_phone": caller_phone,
            "kind": result["kind"],
            "call_id": session.id if _is_uuid(session.id) else None,
            "client_ref": f"call:{ref}:wa:{n}",
        }
        for key in ("document", "topic", "when"):
            if result.get(key):
                body[key] = str(result[key])[:120]
        await core.send_whatsapp(body)
    return len(accepted)
