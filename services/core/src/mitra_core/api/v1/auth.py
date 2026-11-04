"""Phone OTP login and business switching (contract §1).

Pre-auth state lives in ``otp_request``, which the app role can only reach through the
``auth_otp_issue`` / ``auth_otp_verify`` SECURITY DEFINER functions (migration 0002).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError
from mitra_core.models import AppUser, Business, Membership
from mitra_core.otp import CodeGenerator, get_code_generator, hash_code
from mitra_core.pii import hash_phone, phone_last4
from mitra_core.schemas.auth import (
    AuthSession,
    AuthUserOut,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    SwitchBusinessIn,
)
from mitra_core.schemas.business import MembershipOut
from mitra_core.security import current_user, get_tenant_session
from mitra_core.tenancy import TenantContext, set_tenant
from mitra_core.tokens import mint

router = APIRouter(prefix="/auth", tags=["auth"])

_ISSUE = text(
    "SELECT outcome, retry_after FROM auth_otp_issue("
    ":id, :phone, :phone_hash, :code_hash, :ttl, :max_requests, :window)"
)
_VERIFY = text(
    "SELECT outcome, user_id, attempts_left FROM auth_otp_verify(:id, :code_hash, :max, :name)"
)


async def _memberships(session: AsyncSession, user_id: uuid.UUID) -> list[MembershipOut]:
    # RLS (membership.self_read, business.member_read) limits this to the user's own rows.
    rows = await session.execute(
        select(Membership.business_id, Business.name, Membership.role)
        .join(Business, Business.id == Membership.business_id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at, Membership.business_id)
    )
    return [MembershipOut(business_id=b, business_name=n, role=r) for b, n, r in rows]


def auth_session(
    user: AppUser, memberships: list[MembershipOut], scope: MembershipOut | None
) -> AuthSession:
    ttl = get_settings().access_token_ttl_seconds
    token = mint(
        user.id,
        business_id=scope.business_id if scope else None,
        role=scope.role if scope else None,
    )
    return AuthSession(
        access_token=token,
        expires_in=ttl,
        business_id=scope.business_id if scope else None,
        user=AuthUserOut(
            id=user.id,
            phone_last4=phone_last4(user.phone_e164),
            name=user.name,
            preferred_locale=user.preferred_locale,
        ),
        memberships=memberships,
    )


@router.post(
    "/otp/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OtpRequestOut,
    response_model_exclude_none=True,
    summary="Send a 6-digit login code to a phone (dev_code: env=local or a test staging)",
)
async def request_otp(
    body: OtpRequestIn,
    settings: Settings = Depends(get_settings),
    generate: CodeGenerator = Depends(get_code_generator),
    session: AsyncSession = Depends(get_session),
) -> OtpRequestOut:
    request_id = uuid.uuid4()
    code = generate()
    row = (
        await session.execute(
            _ISSUE,
            {
                "id": request_id,
                "phone": body.phone,
                "phone_hash": hash_phone(body.phone),
                "code_hash": hash_code(request_id, code),
                "ttl": settings.otp_ttl_seconds,
                "max_requests": settings.otp_max_requests,
                "window": settings.otp_window_seconds,
            },
        )
    ).one()
    await session.commit()
    if row.outcome == "rate_limited":
        raise AppError(
            429,
            "rate_limited",
            "Too many codes requested for this number. Please try again later.",
            details={"retry_after": row.retry_after},
            headers={"Retry-After": str(row.retry_after)},
        )
    # TODO(otp): deliver the code by SMS / WhatsApp once a provider is integrated.
    return OtpRequestOut(
        request_id=request_id,
        expires_in=settings.otp_ttl_seconds,
        resend_in=settings.otp_resend_seconds,
        dev_code=code if settings.env == "local" or settings.otp_show_code else None,
    )


@router.post("/otp/verify", response_model=AuthSession, summary="Exchange a login code for a token")
async def verify_otp(
    body: OtpVerifyIn,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> AuthSession:
    row = (
        await session.execute(
            _VERIFY,
            {
                "id": body.request_id,
                "code_hash": hash_code(body.request_id, body.code),
                "max": settings.otp_max_attempts,
                "name": body.name,
            },
        )
    ).one()
    # Commit even on failure: the attempt counter must stick.
    await session.commit()
    if row.outcome == "invalid":
        raise AppError(
            400,
            "otp_invalid",
            "That code is not correct.",
            details={"attempts_left": row.attempts_left},
        )
    if row.outcome == "locked":
        raise AppError(429, "otp_attempts_exceeded", "Too many wrong codes. Request a new one.")
    if row.outcome in {"expired", "consumed"}:
        raise AppError(400, "otp_expired", "This code has expired. Request a new one.")

    user_id: uuid.UUID = row.user_id
    await set_tenant(session, TenantContext(user_id=user_id))
    user = await session.get(AppUser, user_id)
    if user is None:  # pragma: no cover - the function just found or created it
        raise AppError(500, "internal_error", "User could not be loaded")
    memberships = await _memberships(session, user.id)
    return auth_session(user, memberships, memberships[0] if memberships else None)


@router.post(
    "/switch-business",
    response_model=AuthSession,
    summary="Get a token scoped to another business the caller belongs to",
)
async def switch_business(
    body: SwitchBusinessIn,
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(get_tenant_session),
) -> AuthSession:
    memberships = await _memberships(session, user.id)
    scope = next((m for m in memberships if m.business_id == body.business_id), None)
    if scope is None:
        raise AppError(403, "forbidden", "Not a member of this business")
    return auth_session(user, memberships, scope)
