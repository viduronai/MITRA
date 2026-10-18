from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import StringConstraints

from mitra_core.models.enums import Locale
from mitra_core.schemas.business import MembershipOut
from mitra_core.schemas.common import Name120, RequestModel, ResponseModel

# India mobile numbers only for now (contract §1).
IndianMobile = Annotated[str, StringConstraints(pattern=r"^\+91[6-9][0-9]{9}$")]
OtpCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


class OtpRequestIn(RequestModel):
    phone: IndianMobile


class OtpRequestOut(ResponseModel):
    request_id: uuid.UUID
    expires_in: int
    resend_in: int
    dev_code: str | None = None


class OtpVerifyIn(RequestModel):
    request_id: uuid.UUID
    code: OtpCode
    name: Name120 | None = None


class SwitchBusinessIn(RequestModel):
    business_id: uuid.UUID


class AuthUserOut(ResponseModel):
    id: uuid.UUID
    phone_last4: str
    name: str | None
    preferred_locale: Locale


class AuthSession(ResponseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  (not a secret)
    expires_in: int
    # The business the token is scoped to (null = unscoped, e.g. before creating a business).
    business_id: uuid.UUID | None
    user: AuthUserOut
    memberships: list[MembershipOut]
