"""Authentication and authorization dependencies.

TEMPORARY: tokens are HS256 JWTs signed with a dev secret from config (mint them with
``scripts/dev_token.py``). This will be replaced by verifying Better Auth-issued tokens (TRD §3);
only ``decode_token`` should need to change.

Claims: ``sub`` (user id), ``business_id`` (optional, the business the session acts in),
``role`` (advisory only; the authoritative role is read from ``membership`` on every request),
and optional ``phone``/``name`` used to provision the user row on first sight.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.config import Settings, get_settings
from mitra_core.db import get_session
from mitra_core.errors import AppError
from mitra_core.models import AppUser, Membership
from mitra_core.models.enums import MemberRole
from mitra_core.schemas.common import E164Phone, Name120
from mitra_core.tenancy import TenantContext, set_tenant

_bearer = HTTPBearer(auto_error=False, description="JWT access token")
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


class Principal(BaseModel):
    """Verified token claims."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    user_id: uuid.UUID = Field(alias="sub")
    business_id: uuid.UUID | None = None
    role: MemberRole | None = None
    phone: E164Phone | None = None
    name: Name120 | None = None


@dataclass(frozen=True, slots=True)
class Tenant:
    """An authenticated user acting inside a business they are a member of."""

    user: AppUser
    business_id: uuid.UUID
    role: MemberRole


def _unauthenticated(message: str) -> AppError:
    return AppError(401, "unauthenticated", message, headers=_UNAUTHORIZED_HEADERS)


def decode_token(token: str, settings: Settings) -> Principal:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
        return Principal.model_validate(claims)
    except jwt.ExpiredSignatureError as exc:
        raise _unauthenticated("Token expired") from exc
    except (jwt.InvalidTokenError, ValidationError) as exc:
        raise _unauthenticated("Invalid token") from exc


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if credentials is None:
        raise _unauthenticated("Missing bearer token")
    return decode_token(credentials.credentials, settings)


async def get_tenant_session(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> AsyncSession:
    """The request's DB session with RLS context (user + claimed business) bound."""
    await set_tenant(
        session, TenantContext(user_id=principal.user_id, business_id=principal.business_id)
    )
    return session


async def current_user(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> AppUser:
    user = await session.get(AppUser, principal.user_id)
    if user is not None:
        return user
    if principal.phone is None:
        raise _unauthenticated("Unknown user")
    # First request from this identity: mirror it locally (Better Auth owns identities later).
    user = AppUser(id=principal.user_id, phone_e164=principal.phone, name=principal.name)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Either a concurrent first request inserted this user, or the phone is taken.
        await session.rollback()
        existing = await session.get(AppUser, principal.user_id)
        if existing is None:
            raise AppError(
                409, "conflict", "Phone number already belongs to another user"
            ) from None
        return existing
    return user


async def require_business(
    request: Request,
    principal: Principal = Depends(get_principal),
    user: AppUser = Depends(current_user),
    session: AsyncSession = Depends(get_tenant_session),
) -> Tenant:
    if principal.business_id is None:
        raise AppError(403, "business_required", "Token is not scoped to a business")
    role = await session.scalar(
        select(Membership.role).where(
            Membership.business_id == principal.business_id, Membership.user_id == user.id
        )
    )
    if role is None:
        raise AppError(403, "forbidden", "Not a member of this business")
    request.state.business_id = str(principal.business_id)
    return Tenant(user=user, business_id=principal.business_id, role=role)


def require_role(*roles: MemberRole) -> Callable[..., Awaitable[Tenant]]:
    allowed = frozenset(roles)

    async def _dependency(tenant: Tenant = Depends(require_business)) -> Tenant:
        if tenant.role not in allowed:
            raise AppError(
                403,
                "forbidden",
                "Your role does not allow this action",
                details={"required": sorted(allowed), "role": tenant.role},
            )
        return tenant

    return _dependency
