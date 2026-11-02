"""WhatsApp channel (CHAN-01 groundwork, MGR alerts/reports, APPR-02 approval cards).

Public API (session bound to the business, caller commits):

* ``notify_owner(session, business_id, kind, text, *, buttons=None, ref=None, dedupe_key=None)``
* ``notify_staff(session, business_id, *, text, user_id=None, to_phone=None, ref=None)``
* ``send_template(session, business_id, *, to_phone, template, language="en", params=None, ...)``
* ``send_text(session, business_id, *, to_phone, text, purpose="customer", ...)``

The provider is the simulator unless ``MITRA_WHATSAPP_PROVIDER=cloud`` and Meta credentials
are configured.
"""

from mitra_core.whatsapp.provider import (
    Button,
    CloudApiProvider,
    SendResult,
    SimulatorProvider,
    WhatsAppProvider,
    get_provider,
    set_provider,
)
from mitra_core.whatsapp.service import (
    ALERT_KINDS,
    manager_settings,
    notify_owner,
    notify_staff,
    owner_recipients,
    send_buttons,
    send_heads_up,
    send_template,
    send_text,
)

__all__ = [
    "ALERT_KINDS",
    "Button",
    "CloudApiProvider",
    "SendResult",
    "SimulatorProvider",
    "WhatsAppProvider",
    "get_provider",
    "manager_settings",
    "notify_owner",
    "notify_staff",
    "owner_recipients",
    "send_buttons",
    "send_heads_up",
    "send_template",
    "send_text",
    "set_provider",
]
