"""Test fixtures. Tests run against the ``mitra_test`` database (schema recreated per session).

The API under test connects as the non-superuser app role, exactly like production, so every
test exercises RLS. ``admin_engine`` (schema owner / superuser) is only for setup and cleanup.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path

_HOST = os.environ.get("MITRA_TEST_DB_HOST", "localhost:5433")
os.environ["MITRA_ENV"] = "test"
os.environ["MITRA_DATABASE_URL"] = (
    f"postgresql+asyncpg://mitra_app:mitra_app_dev_password@{_HOST}/mitra_test"
)
os.environ["MITRA_MIGRATION_DATABASE_URL"] = (
    f"postgresql+asyncpg://mitra:mitra_dev_password@{_HOST}/mitra_test"
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine  # noqa: E402

from mitra_core.clock import get_clock  # noqa: E402
from mitra_core.config import get_settings  # noqa: E402
from mitra_core.db import dispose_engine  # noqa: E402
from mitra_core.main import app  # noqa: E402
from mitra_core.otp import get_code_generator  # noqa: E402
from tests.helpers import FIXED_CODE, Actor, FakeClock, new_actor  # noqa: E402

CORE_DIR = Path(__file__).resolve().parents[1]
TABLES = (
    "otp_request",
    "test_call",
    "fact",
    "knowledge_source",
    "idempotency_record",
    "contact",
    "employee",
    "membership",
    "branch",
    "app_user",
    "business",
    "agency",
)


async def _reset_schema() -> None:
    engine = create_async_engine(get_settings().migration_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        # Restore what infra/postgres/init.sql set up (dropped with the schema).
        for ext in ("vector", "pgcrypto", "citext"):
            await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    asyncio.run(_reset_schema())
    cfg = Config(str(CORE_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().migration_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def app_engine() -> AsyncIterator[AsyncEngine]:
    """A raw engine connecting as the app role (for direct RLS checks)."""
    engine = create_async_engine(get_settings().database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
async def _dispose_api_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_tables(admin_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))


@pytest.fixture
def make_actor() -> Callable[..., Actor]:
    return new_actor


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def fixed_code() -> str:
    """Pin OTP codes so tests can log in (codes are random and never returned in env=test)."""
    app.dependency_overrides[get_code_generator] = lambda: lambda: FIXED_CODE
    return FIXED_CODE


@pytest.fixture
def clock() -> FakeClock:
    fake = FakeClock()
    app.dependency_overrides[get_clock] = lambda: fake
    return fake
