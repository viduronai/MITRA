"""Approvals — "Ask me first" (APPR-01..06). See ``service.py`` for the safety rules.

Public API:

* ``await request_approval(session, business_id, *, kind, summary, payload, requested_by,
  expires_at=None, default_action=None) -> Approval``
* ``register_handler(kind, async fn(session, approval))`` — runs once after the decision.
* ``await needs_approval(session, business_id, kind, *, amount=None) -> bool`` (APPR-01 rules).
"""

from mitra_core.approvals.rules import DEFAULT_RULES, RuleSpec, get_rules, needs_approval
from mitra_core.approvals.service import (
    Action,
    Handler,
    button_id,
    cancel,
    decide,
    edit_approval,
    expire_due,
    parse_button_id,
    register_handler,
    request_approval,
)

__all__ = [
    "DEFAULT_RULES",
    "Action",
    "Handler",
    "RuleSpec",
    "button_id",
    "cancel",
    "decide",
    "edit_approval",
    "expire_due",
    "get_rules",
    "needs_approval",
    "parse_button_id",
    "register_handler",
    "request_approval",
]
