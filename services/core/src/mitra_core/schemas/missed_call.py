"""Missed-call number (CALL-20): setup card, poster lines, stats, block list."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from mitra_core.schemas.common import E164Phone, RequestModel, ResponseModel

MissedStatus = Literal["queued", "deduped", "rate_limited", "blocked"]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CarrierSid = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,64}$")]


class MissedNumberIn(RequestModel):
    """``phone_number_id`` = null switches the missed-call number off."""

    phone_number_id: uuid.UUID | None


class PosterLines(ResponseModel):
    en: str
    hi: str
    te: str


class MissedCallStatsOut(ResponseModel):
    days: int
    missed: int
    called_back: int
    answered: int


class MissedCallRow(ResponseModel):
    id: uuid.UUID
    phone_masked: str | None
    status: MissedStatus
    received_at: datetime
    call_back_at: datetime | None
    outcome: str | None  # the callback's dialer status / last outcome


class CallerBlockOut(ResponseModel):
    id: uuid.UUID
    phone_masked: str | None
    reason: str | None
    created_at: datetime


class MissedCallSetupOut(ResponseModel):
    phone_number_id: uuid.UUID | None
    e164: str | None
    display: str | None
    live: bool  # the number is approved and can take calls
    tel_uri: str | None  # what the QR code dials
    poster: PosterLines | None
    stats: MissedCallStatsOut
    recent: list[MissedCallRow]
    blocks: list[CallerBlockOut]


class CallerBlockIn(RequestModel):
    """Block a caller seen in the recent list (by its id) or by number."""

    missed_call_id: uuid.UUID | None = None
    phone: E164Phone | None = None
    reason: Reason | None = None


# ---- internal (voice service) ----------------------------------------------------------------


class MissedCallIn(RequestModel):
    to: E164Phone
    from_: E164Phone = Field(alias="from")
    carrier_call_sid: CarrierSid | None = None
    at: datetime | None = None


class MissedCallOut(ResponseModel):
    id: uuid.UUID
    status: MissedStatus
    call_back_at: datetime | None
    deferred: bool
