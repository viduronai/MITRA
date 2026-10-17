from __future__ import annotations

import uuid

from mitra_core.models.enums import Locale
from mitra_core.schemas.business import MembershipOut
from mitra_core.schemas.common import ResponseModel


class UserOut(ResponseModel):
    id: uuid.UUID
    phone_e164: str
    name: str | None
    email: str | None
    preferred_locale: Locale


class MeResponse(ResponseModel):
    user: UserOut
    memberships: list[MembershipOut]
