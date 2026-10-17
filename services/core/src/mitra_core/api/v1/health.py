from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.db import get_session
from mitra_core.errors import AppError
from mitra_core.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
log = get_logger(__name__)


@router.get("", summary="Liveness")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness (checks the database)")
async def readiness(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        log.warning("readiness_db_failed", exc_type=type(exc).__name__)
        raise AppError(503, "not_ready", "Database unavailable") from exc
    return {"status": "ok", "database": "ok"}
