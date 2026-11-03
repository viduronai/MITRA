"""APPR-01 approval rules: which kinds need "Ask me first", above what, and timeout defaults.

``threshold`` units per kind: discount = percent, refund / big_booking / payment_link = rupees,
list_call = number of contacts. ``None`` threshold = always ask. Owners change these in the
app; a business without a stored rule gets the default below.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.models import ApprovalRule


@dataclass(frozen=True, slots=True)
class RuleSpec:
    kind: str
    enabled: bool
    threshold: int | None
    timeout_minutes: int | None
    default_action: str | None


# Manager commands and coaching always need a confirm tap (WORKFLOWS §8); they are not
# owner-switchable, so they are not listed here.
DEFAULT_RULES: dict[str, RuleSpec] = {
    "discount": RuleSpec("discount", True, 0, 120, "decline"),
    "refund": RuleSpec("refund", True, 0, 240, "decline"),
    "cancellation": RuleSpec("cancellation", True, None, 60, "decline"),
    "big_booking": RuleSpec("big_booking", True, 50_000, 120, None),
    "list_call": RuleSpec("list_call", True, 50, None, None),
    # An AI employee sending a payment link above this many rupees (payments module).
    "payment_link": RuleSpec("payment_link", True, 10_000, 240, "decline"),
}
ALWAYS_ASK = frozenset({"manager_command", "behaviour_update"})


async def get_rules(session: AsyncSession, business_id: uuid.UUID) -> dict[str, RuleSpec]:
    rules = dict(DEFAULT_RULES)
    for row in await session.scalars(
        select(ApprovalRule).where(ApprovalRule.business_id == business_id)
    ):
        if row.kind in rules:
            rules[row.kind] = RuleSpec(
                row.kind, row.enabled, row.threshold, row.timeout_minutes, row.default_action
            )
    return rules


async def needs_approval(
    session: AsyncSession, business_id: uuid.UUID, kind: str, *, amount: float | None = None
) -> bool:
    """True when ``kind`` (with ``amount`` in the kind's unit) must wait for the owner.

    Unknown kinds always need approval (fail safe).
    """
    if kind in ALWAYS_ASK:
        return True
    rule = (await get_rules(session, business_id)).get(kind)
    if rule is None:
        return True
    if not rule.enabled:
        return False
    if rule.threshold is None or amount is None:
        return True
    return amount > rule.threshold


async def upsert_rule(session: AsyncSession, business_id: uuid.UUID, spec: RuleSpec) -> None:
    row = await session.get(ApprovalRule, (business_id, spec.kind))
    if row is None:
        row = ApprovalRule(business_id=business_id, kind=spec.kind)
        session.add(row)
    row.enabled = spec.enabled
    row.threshold = spec.threshold
    row.timeout_minutes = spec.timeout_minutes
    row.default_action = spec.default_action
    await session.flush()
