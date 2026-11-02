"""DND / NCPR lookup behind a provider interface (CMP-04). Only ``mock`` exists today.

The real scrub provider (TRAI DND registry access through the carrier or a DLT-registered
vendor) plugs in by implementing :class:`DndProvider`. Results are cached per business for at
most 24 h in ``dnd_cache`` (``service.dnd_status``); the raw number is never stored, only its
HMAC.
"""

from __future__ import annotations

from typing import Protocol

from mitra_core.config import Settings, get_settings
from mitra_core.telephony.enums import DndStatus

CACHE_HOURS = 24


class DndProvider(Protocol):
    name: str

    async def lookup(self, phone_e164: str) -> DndStatus: ...


class MockDndProvider:
    """Registered = any number listed in ``MITRA_DND_MOCK_REGISTERED``. Never calls out."""

    name = "mock"

    def __init__(self, registered: frozenset[str] = frozenset(), *, down: bool = False) -> None:
        self.registered = registered
        self.down = down
        self.lookups = 0

    async def lookup(self, phone_e164: str) -> DndStatus:
        self.lookups += 1
        if self.down:
            return DndStatus.UNKNOWN
        if phone_e164 in self.registered:
            return DndStatus.REGISTERED
        return DndStatus.NOT_REGISTERED


def make_dnd_provider(settings: Settings) -> DndProvider:
    if settings.dnd_provider == "mock":
        return MockDndProvider(frozenset(settings.dnd_mock_registered))
    raise ValueError(f"unknown DND provider: {settings.dnd_provider}")  # pragma: no cover


def get_dnd_provider() -> DndProvider:
    """FastAPI dependency (tests override it)."""
    return make_dnd_provider(get_settings())
