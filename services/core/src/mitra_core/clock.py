"""Injectable wall clock (a FastAPI dependency), so time-based behaviour is testable."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


def get_clock() -> Clock:
    return utcnow
