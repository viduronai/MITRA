from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from mitra_core.models.enums import Locale
from mitra_core.schemas.auth import IndianMobile
from mitra_core.schemas.common import RequestModel, ResponseModel

DemoIndustry = Literal["clinic", "real_estate", "coaching"]


class DemoCallIn(RequestModel):
    phone: IndianMobile
    language: Locale = Locale.TE
    industry: DemoIndustry = "clinic"
    # The visitor must tick/accept the consent line; anything but ``true`` is a 422.
    consent: Literal[True] = Field(
        description="The visitor agreed to receive one AI demo call on this number."
    )


class DemoCallOut(ResponseModel):
    id: uuid.UUID
    status: Literal["queued"]
    phone_last4: str
    eta_seconds: int
    # Always true until the Exotel dialer is integrated: nothing is actually dialled.
    simulated: bool
