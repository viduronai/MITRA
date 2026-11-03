"""The ``send_payment_link`` tool body (ACT-05): only grounded amounts, at most two per call.

An amount is grounded when it is written in the pack's facts or in the call's brief (an
outbound reminder carries ``payment amount: ₹2,000``). Anything else is refused, so the AI can
never invent a price. The link itself is created by core after the call
(``transports.payment_links``); a discount waits for the owner's OK there.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(lakh|lakhs|lac|crore|k)?\b"
    r"|(\d[\d,]*(?:\.\d{1,2})?)\s*(?=(?:rupees|/-))",
    re.IGNORECASE,
)
SCALE = {"lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "crore": 10_000_000, "k": 1_000}
MAX_PAYMENT_LINKS = 2

SPEC: tuple[str, dict[str, Any]] = (
    "Send the caller a UPI payment link on WhatsApp (ACT-05). Use ONLY an amount written in "
    "the business facts or in this call's brief; never invent or estimate one. A discount "
    "needs the owner's OK, so only pass one the caller was already offered.",
    {
        "type": "object",
        "properties": {
            "amount_rupees": {"type": "number", "description": "Amount in rupees, e.g. 2000."},
            "purpose": {"type": "string", "description": "What it pays for, e.g. 'MRI scan'."},
            "discount_percent": {
                "type": "integer",
                "description": "Discount already offered, 0-100 (default 0).",
            },
        },
        "required": ["amount_rupees", "purpose"],
    },
)


def known_amounts(texts: Iterable[str]) -> set[int]:
    """Every rupee amount written in ``texts``, in paise (₹2,000 -> 200000, ₹1.5 lakh -> ...)."""
    found: set[int] = set()
    for text in texts:
        for match in AMOUNT.finditer(text or ""):
            value = float((match.group(1) or match.group(3)).replace(",", ""))
            scale = SCALE.get((match.group(2) or "").lower(), 1)
            found.add(round(value * scale * 100))
    return found


def send_payment_link(
    a: dict[str, Any], *, grounded: set[int], already_sent: int
) -> dict[str, Any]:
    try:
        amount = round(float(a.get("amount_rupees") or 0) * 100)
        discount = int(a.get("discount_percent") or 0)
    except (TypeError, ValueError):
        return {"error": "amount must be a number of rupees"}
    purpose = str(a.get("purpose") or "").strip()[:200]
    if not purpose:
        return {"error": "say what the payment is for"}
    if amount < 100 or amount not in grounded:
        return {
            "status": "not_sent",
            "error": "that amount is not in the business facts; do not guess. "
            "Say the team will send the exact amount on WhatsApp, and schedule_callback.",
        }
    if not 0 <= discount <= 100:
        return {"error": "discount must be 0-100"}
    if already_sent >= MAX_PAYMENT_LINKS:
        return {"status": "not_sent", "error": "a payment link was already sent on this call"}
    final = amount * (100 - discount) // 100
    return {
        "ok": True,
        "status": "will_send",
        "amount_paise": final,
        "amount": f"₹{final / 100:,.0f}" if final % 100 == 0 else f"₹{final / 100:,.2f}",
        "channel": "WhatsApp, right after this call",
        "needs_owner_ok": discount > 0,
    }
