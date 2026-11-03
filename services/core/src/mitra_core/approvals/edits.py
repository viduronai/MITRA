"""What an owner may change on a pending approval before approving it (APPR-06).

Kinds listed in ``EDIT_RULES`` accept edits only to the named payload fields; every other
field must stay as it was. Kinds not listed accept any payload edit. The app reads
``editable_fields`` so it only offers fields the server will accept.
"""

from __future__ import annotations

from typing import Any, Literal, TypeGuard

from mitra_core.errors import AppError

Rule = Literal["lower_int"]  # a whole number from 1 up to the requested value

EDIT_RULES: dict[str, dict[str, Rule]] = {
    # Calling a list: the owner can call fewer people, never more and never another list.
    "list_call": {"contacts": "lower_int"},
    # A payment link: the owner can ask for less, never more and never another customer.
    "payment_link": {"amount_paise": "lower_int"},
}


def editable_fields(kind: str) -> list[str] | None:
    """Payload fields the owner may edit, or ``None`` when any field may change."""
    rules = EDIT_RULES.get(kind)
    return None if rules is None else sorted(rules)


def _whole(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def check_edit(kind: str, before: dict[str, Any], after: dict[str, Any]) -> None:
    rules = EDIT_RULES.get(kind)
    if rules is None:
        return
    for key in before.keys() | after.keys():
        if key not in rules and before.get(key) != after.get(key):
            raise AppError(422, "not_editable", f"'{key}' can't be changed on this request")
    for key, rule in rules.items():
        old, new = before.get(key), after.get(key)
        if new == old:
            continue
        if rule == "lower_int" and not (_whole(old) and _whole(new) and 1 <= new <= old):
            message = f"'{key}' can only be lowered to a whole number from 1 to {old}"
            raise AppError(422, "invalid_edit", message)
