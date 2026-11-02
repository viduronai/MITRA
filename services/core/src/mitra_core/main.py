"""FastAPI application factory."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mitra_core.api import internal, internal_billing, internal_calls, internal_telephony
from mitra_core.api.v1 import health
from mitra_core.api.v1 import router as v1_router
from mitra_core.config import Settings, get_settings
from mitra_core.db import dispose_engine
from mitra_core.errors import register_error_handlers
from mitra_core.logging import configure_logging, get_logger

log = get_logger("mitra_core.access")

_REQUEST_ID_HEADER = "x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    """Assigns a request id, binds it to log context, and writes one JSON access log line.

    Logs the path only (never the query string, headers or body) so tokens and phone numbers
    cannot leak into logs. ``business_id`` is read from ``request.state`` once auth has run.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(_REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((_REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            state = scope.get("state") or {}
            log.info(
                "request",
                method=scope["method"],
                path=scope["path"],
                status=status_code,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                business_id=state.get("business_id"),
            )
            structlog.contextvars.unbind_contextvars("request_id")


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Mitra Core API",
        version="0.1.0",
        description="Businesses, users, AI employees. Multi-tenant with Postgres RLS.",
        lifespan=_lifespan,
    )
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    if settings.env == "local":
        # Browser dev servers only; deployed environments sit behind a same-origin proxy.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Idempotent-Replayed", "Retry-After"],
            max_age=600,
        )
    app.include_router(health.router)
    app.include_router(v1_router)
    app.include_router(internal.router)
    app.include_router(internal_billing.router)
    app.include_router(internal_calls.router)
    app.include_router(internal_telephony.router)
    return app


app = create_app()
