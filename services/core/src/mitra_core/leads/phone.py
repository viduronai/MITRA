"""Indian phone numbers as lead forms send them -> E.164.

Forms and portals send ``98765 43210``, ``098765-43210``, ``+91-9876543210`` (IndiaMART) or
``919876543210`` (Meta). Only Indian mobile numbers are accepted for now: lead calls go to the
person who enquired, and landline leads are rare enough to handle manually.
"""

from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s\-().]")
_MOBILE = re.compile(r"^[6-9][0-9]{9}$")


def normalize_indian_mobile(raw: object) -> str | None:
    """``"+91 98765-43210"`` -> ``"+919876543210"``; ``None`` when it is not an Indian mobile."""
    if not isinstance(raw, str | int):
        return None
    digits = _SEPARATORS.sub("", str(raw).strip())
    if digits.startswith("+"):
        if not digits.startswith("+91"):
            return None
        digits = digits[3:]
    elif digits.startswith("0091"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return f"+91{digits}" if _MOBILE.fullmatch(digits) else None
