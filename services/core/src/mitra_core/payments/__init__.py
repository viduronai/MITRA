"""UPI collections with auto-matching (ACT-05, ACT-11, INT-08): the business's own money.

Kept apart from Mitra's wallet billing (``mitra_core.billing``): different tables, different
Razorpay account (the business's), different webhook URL.

Public API (session bound to the business, caller commits):

* ``create_request(session, business_id, NewRequest(...), now=...)`` -> ``PaymentRequest``
* ``mark_paid`` / ``mark_failed`` / ``mark_expired`` / ``cancel`` / ``resend``
* ``register_sms_sender(fn)``: optional SMS fallback when WhatsApp cannot deliver
* ``scheduler.tick(now)``: the reminder step for links unpaid after their due date
"""

from mitra_core.payments.service import (
    APPROVAL_KIND,
    NewRequest,
    cancel,
    create_request,
    mark_expired,
    mark_failed,
    mark_paid,
    register_sms_sender,
    resend,
)

__all__ = [
    "APPROVAL_KIND",
    "NewRequest",
    "cancel",
    "create_request",
    "mark_expired",
    "mark_failed",
    "mark_paid",
    "register_sms_sender",
    "resend",
]
