from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import StringConstraints

from mitra_core.models.enums import TestCallStatus
from mitra_core.schemas.auth import IndianMobile
from mitra_core.schemas.common import RequestModel, ResponseModel

CorrectionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class TestCallIn(RequestModel):
    employee_id: uuid.UUID
    phone: IndianMobile | None = None


class TranscriptLine(ResponseModel):
    speaker: Literal["employee", "caller"]
    text: str
    at_ms: int


class TestCallCreated(ResponseModel):
    id: uuid.UUID
    status: TestCallStatus
    simulated: Literal[True] = True


class TestCallOut(TestCallCreated):
    employee_id: uuid.UUID
    phone_last4: str
    created_at: datetime
    transcript: list[TranscriptLine]
    summary: str | None


class CorrectionIn(RequestModel):
    text: CorrectionText


class CorrectionOut(ResponseModel):
    id: uuid.UUID
    applied_to: Literal["knowledge", "behaviour"]
    change_summary: str
    fact_id: uuid.UUID | None = None
