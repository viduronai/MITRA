"""WhatsApp channel via Meta Cloud API (direct): alerts, reports, approval cards, customer
messages. Sending follows Meta's 24-hour rule (``outbox.py``); templates are in
``templates.py`` (docs/whatsapp-templates.md).

Public API (session bound to the business, caller commits):

* ``send_customer_message(session, business_id, *, to_phone, template, params, text=None, ...)``
* ``notify_owner(session, business_id, kind, text, *, template=None, params=None, ...)``
* ``send_staff_task(session, business_id, *, text, action, customer, brief, to_phone|user_id)``
* ``send_heads_up(...)`` (NUM-07), ``send_template(...)``, ``send_text(...)``, ``notify_staff(...)``

Every send returns the stored ``WaMessage`` (``status``: sent / failed / blocked) or ``None``
when its ``dedupe_key`` was already used. The provider is the simulator unless
``MITRA_WHATSAPP_PROVIDER=cloud`` and Meta credentials are configured.
"""

from mitra_core.whatsapp.outbox import deliver, opted_out, window_open
from mitra_core.whatsapp.provider import (
    Button,
    CloudApiProvider,
    Document,
    SendResult,
    SimulatorProvider,
    TemplateMessage,
    WhatsAppProvider,
    get_provider,
    set_provider,
)
from mitra_core.whatsapp.service import (
    ALERT_KINDS,
    language_for,
    manager_settings,
    notify_owner,
    notify_staff,
    owner_recipients,
    send_buttons,
    send_customer_message,
    send_heads_up,
    send_staff_task,
    send_template,
    send_text,
)
from mitra_core.whatsapp.team_messages import send_team_message
from mitra_core.whatsapp.templates import TEMPLATES, TemplateError

__all__ = [
    "ALERT_KINDS",
    "TEMPLATES",
    "Button",
    "CloudApiProvider",
    "Document",
    "SendResult",
    "SimulatorProvider",
    "TemplateError",
    "TemplateMessage",
    "WhatsAppProvider",
    "deliver",
    "get_provider",
    "language_for",
    "manager_settings",
    "notify_owner",
    "notify_staff",
    "opted_out",
    "owner_recipients",
    "send_buttons",
    "send_customer_message",
    "send_heads_up",
    "send_staff_task",
    "send_team_message",
    "send_template",
    "send_text",
    "set_provider",
    "window_open",
]
