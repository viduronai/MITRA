"""Per-request tenant context for Postgres Row-Level Security.

How it works:

* Every RLS policy compares a row's ``business_id`` with ``app_current_business_id()``, a SQL
  helper that reads the transaction-local setting ``app.business_id`` (see the initial migration).
* The tenant for a request is stored on ``session.info``. A SQLAlchemy ``after_begin`` listener
  runs ``set_config('app.business_id', ..., true)`` (``true`` = transaction-local) at the start
  of EVERY transaction the session opens, so the context can never be forgotten after a commit
  and can never leak to the next user of a pooled connection.
* When no tenant is bound, the settings are set to '' and policies match no rows (fail closed).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

_TENANT_KEY = "mitra_tenant"
_SET_TENANT_SQL = text(
    "SELECT set_config('app.business_id', :business_id, true),"
    " set_config('app.user_id', :user_id, true)"
)


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: uuid.UUID | None = None
    business_id: uuid.UUID | None = None

    def as_params(self) -> dict[str, str]:
        return {
            "business_id": str(self.business_id) if self.business_id else "",
            "user_id": str(self.user_id) if self.user_id else "",
        }


def get_tenant(session: AsyncSession | Session) -> TenantContext:
    ctx = session.info.get(_TENANT_KEY)
    return ctx if isinstance(ctx, TenantContext) else TenantContext()


async def set_tenant(session: AsyncSession, ctx: TenantContext) -> None:
    """Bind ``ctx`` to the session; applies immediately if a transaction is already open."""
    session.info[_TENANT_KEY] = ctx
    if session.in_transaction():
        await session.execute(_SET_TENANT_SQL, ctx.as_params())


@event.listens_for(Session, "after_begin")
def _apply_tenant_on_begin(
    session: Session, transaction: SessionTransaction, connection: Connection, *_: Any
) -> None:
    connection.execute(_SET_TENANT_SQL, get_tenant(session).as_params())
