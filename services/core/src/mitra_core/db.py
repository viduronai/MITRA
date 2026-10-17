"""Async SQLAlchemy engine and session management.

The API engine connects as the non-superuser app role (``MITRA_DATABASE_URL``), so RLS applies.
Route handlers commit explicitly; the session dependency only closes (and rolls back anything
uncommitted). Tenant context is bound by the auth dependencies, see ``tenancy.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mitra_core import tenancy  # noqa: F401  (registers the after_begin RLS listener)
from mitra_core.config import get_settings
from mitra_core.tenancy import TenantContext, set_tenant

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a session with no tenant bound (RLS tables appear empty)."""
    async with get_sessionmaker()() as session:
        yield session


@asynccontextmanager
async def tenant_session(ctx: TenantContext) -> AsyncIterator[AsyncSession]:
    """Session bound to a tenant, for code outside the request cycle (workers, scripts)."""
    async with get_sessionmaker()() as session:
        await set_tenant(session, ctx)
        yield session
