"""Carrier adapter interface: place an outbound call that streams into our WebSocket.

Every carrier connects the answered call to ``/telephony/<carrier>/ws`` on this service, the same
pipeline as browser calls. The carrier's call id ties the stream back to what we dialled: the
:class:`OutboundRegistry` remembers each placed call's intent (business, employee, contact,
purpose, core attempt id) until its stream starts or it expires.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

CarrierName = Literal["sim", "exotel", "plivo"]
Purpose = Literal["callback", "service", "mandated_service", "promotional"]


class CarrierError(RuntimeError):
    """The carrier refused or could not be reached; never contains credentials or numbers."""


@dataclass(frozen=True, slots=True)
class OutboundIntent:
    business_id: str
    employee_id: str
    contact_phone: str  # E.164; never logged
    caller_id: str  # E.164 chosen by compliance.check
    purpose: Purpose
    phone_number_id: str | None = None
    attempt_id: str | None = None  # core outbound_attempt row, for the outcome update
    scenario: str = "clinic"  # fixture fallback in local dev only


@dataclass(frozen=True, slots=True)
class PlacedCall:
    carrier: CarrierName
    call_sid: str
    status: str


class Carrier(Protocol):
    name: CarrierName

    async def place_call(self, intent: OutboundIntent) -> PlacedCall: ...

    async def aclose(self) -> None: ...


@dataclass
class OutboundRegistry:
    """Pending outbound calls by carrier call id. In-memory: one voice instance per call.

    TODO(scale): move to Valkey when more than one voice instance takes carrier streams.
    """

    ttl_s: float = 600.0
    _items: dict[str, tuple[float, OutboundIntent]] = field(default_factory=dict)

    def add(self, call_sid: str, intent: OutboundIntent) -> None:
        self._expire()
        self._items[call_sid] = (time.monotonic(), intent)

    def get(self, call_sid: str | None) -> OutboundIntent | None:
        self._expire()
        item = self._items.get(call_sid or "")
        return item[1] if item else None

    def pop(self, call_sid: str | None) -> OutboundIntent | None:
        self._expire()
        item = self._items.pop(call_sid or "", None)
        return item[1] if item else None

    def _expire(self) -> None:
        cutoff = time.monotonic() - self.ttl_s
        for sid in [s for s, (at, _) in self._items.items() if at < cutoff]:
            del self._items[sid]


def new_sim_sid() -> str:
    return "SIM" + uuid.uuid4().hex[:29]
