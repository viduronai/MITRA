"""Approval summaries built from the payload, so they never go stale and can be translated.

For a kind listed here the server owns the summary: it is rebuilt from the payload when the
approval is created and after every edit, stored as English text (``approval.summary``, the
fallback everywhere) plus ``summary_key`` / ``summary_params`` that the app renders in the
viewer's language (``approvals.summaries.<key>`` in the web messages). The owner can't type a
summary for these kinds; they change the payload and the summary follows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Summary:
    key: str
    params: dict[str, str]
    english: str


def _rupees(paise: object) -> str:
    try:
        value = int(str(paise))
    except ValueError:
        return "₹?"
    rupees, rest = divmod(value, 100)
    return f"₹{rupees:,}" + (f".{rest:02d}" if rest else "")


def _list_call(p: dict[str, Any]) -> Summary:
    count, name = str(p.get("contacts", "?")), str(p.get("name") or "")
    if not name:
        return Summary("list_call_unnamed", {"count": count}, f"Call a list of {count} people")
    return Summary(
        "list_call", {"count": count, "name": name}, f"Call a list of {count} people: “{name}”"
    )


def _payment_link(p: dict[str, Any]) -> Summary:
    params = {
        "customer": str(p.get("customer") or "a customer"),
        "amount": _rupees(p.get("amount_paise")),
        "purpose": str(p.get("purpose") or ""),
        "discount": str(p.get("discount_percent") or 0),
    }
    english = f"Send {params['customer']} a payment link: {params['amount']}"
    if params["discount"] != "0":
        english += f" ({params['discount']}% off)"
        key = "payment_link_discount"
    else:
        key = "payment_link"
    if params["purpose"]:
        english += f" for {params['purpose']}"
    return Summary(key, params, english)


BUILDERS: dict[str, Callable[[dict[str, Any]], Summary]] = {
    "list_call": _list_call,
    "payment_link": _payment_link,
}


def build(kind: str, payload: dict[str, Any]) -> Summary | None:
    builder = BUILDERS.get(kind)
    return builder(payload) if builder else None
