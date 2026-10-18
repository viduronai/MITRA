"""``Idempotency-Key`` support for POST endpoints (TRD §11).

Flow inside the request transaction: take an advisory lock on the key (serialises concurrent
retries), look up a stored record, and either replay it or run the handler and store its
response in the same transaction. Records expire after ``idempotency_ttl_hours``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Header
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mitra_core.config import get_settings
from mitra_core.errors import AppError
from mitra_core.models import IdempotencyRecord

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r"^[\x21-\x7e]+$",
        description="Client-generated key; retries with the same key replay the first response.",
    ),
]


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def lock_key(session: AsyncSession, scope: str, key: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"{scope}|{key}"}
    )


async def find(
    session: AsyncSession,
    *,
    endpoint: str,
    key: str,
    business_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> IdempotencyRecord | None:
    """Find a live record by business scope, or by user (for business creation)."""
    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.endpoint == endpoint, IdempotencyRecord.key == key
    )
    if business_id is not None:
        stmt = stmt.where(IdempotencyRecord.business_id == business_id)
    if user_id is not None:
        stmt = stmt.where(IdempotencyRecord.user_id == user_id)
    record = await session.scalar(stmt)
    if record is None:
        return None
    ttl = timedelta(hours=get_settings().idempotency_ttl_hours)
    if record.created_at < datetime.now(UTC) - ttl:
        await session.delete(record)
        await session.flush()
        return None
    return record


def ensure_same_request(record: IdempotencyRecord, req_hash: str) -> None:
    if record.request_hash != req_hash:
        raise AppError(
            422,
            "idempotency_key_reused",
            "Idempotency-Key was already used with a different request body",
        )


def replay(
    record: IdempotencyRecord, req_hash: str, extra: dict[str, Any] | None = None
) -> JSONResponse:
    """Replay the stored response; ``extra`` adds fields that must not be stored (tokens)."""
    ensure_same_request(record, req_hash)
    return JSONResponse(
        record.response_body | (extra or {}),
        record.response_status,
        headers={"Idempotent-Replayed": "true"},
    )


def save(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    endpoint: str,
    key: str,
    req_hash: str,
    status: int,
    body: dict[str, Any],
) -> None:
    session.add(
        IdempotencyRecord(
            business_id=business_id,
            user_id=user_id,
            endpoint=endpoint,
            key=key,
            request_hash=req_hash,
            response_status=status,
            response_body=body,
        )
    )


async def lookup_for_business(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    endpoint: str,
    key: str | None,
    payload: dict[str, Any],
) -> tuple[str, JSONResponse | None]:
    """Common start of a business-scoped idempotent create: (request hash, replay or None)."""
    req_hash = request_hash(payload)
    if not key:
        return req_hash, None
    await lock_key(session, f"business:{business_id}:{endpoint}", key)
    record = await find(session, endpoint=endpoint, key=key, business_id=business_id)
    return req_hash, (replay(record, req_hash) if record is not None else None)
