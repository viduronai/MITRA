"""HTTP delivery of one webhook, with SSRF protection.

Owners type any URL, so targets are checked twice: when saved (:func:`validate_url`) and before
every send (the host is resolved and every address must be public). Redirects are not followed.
TODO(egress): send through an egress proxy with a fixed IP so customers can allow-list us, which
also closes the DNS-rebinding window between the check and the connect.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from mitra_core.config import Settings, get_settings

Resolver = Callable[[str], Awaitable[list[str]]]


class UnsafeUrlError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SendResult:
    status: int | None
    error: str | None
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class WebhookSender(Protocol):
    async def send(self, url: str, headers: dict[str, str], body: bytes) -> SendResult: ...


def _private(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not ip.is_global or ip.is_multicast


def validate_url(url: str, *, allow_private: bool) -> str:
    """Raise :class:`UnsafeUrlError` for anything but a plain public http(s) URL."""
    parts = urlsplit(url)
    if parts.scheme != "https" and not (allow_private and parts.scheme == "http"):
        raise UnsafeUrlError("The address must start with https://")
    if not parts.hostname or parts.username or parts.password:
        raise UnsafeUrlError("The address is not valid")
    host = parts.hostname
    local = host == "localhost" or host.endswith((".localhost", ".internal", ".local"))
    if local and not allow_private:
        raise UnsafeUrlError("Private addresses are not allowed")
    try:
        private = _private(host)
    except ValueError:
        private = False  # a host name: resolved and checked again before each send
    if private and not allow_private:
        raise UnsafeUrlError("Private addresses are not allowed")
    return url


async def system_resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class HttpSender:
    def __init__(
        self,
        settings: Settings,
        *,
        resolve: Resolver = system_resolve,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.allow_private = settings.webhook_allow_private_urls
        self.timeout = settings.webhook_timeout_seconds
        self.resolve = resolve
        self.transport = transport

    async def _check(self, url: str) -> None:
        validate_url(url, allow_private=self.allow_private)
        if self.allow_private:
            return
        host = urlsplit(url).hostname or ""
        try:
            addresses = await self.resolve(host)
        except OSError as exc:
            raise UnsafeUrlError("The address could not be found") from exc
        if not addresses or any(_private(a) for a in addresses):
            raise UnsafeUrlError("Private addresses are not allowed")

    async def send(self, url: str, headers: dict[str, str], body: bytes) -> SendResult:
        start = time.perf_counter()

        def took() -> int:
            return round((time.perf_counter() - start) * 1000)

        try:
            await self._check(url)
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=False, transport=self.transport
            ) as client:
                resp = await client.post(url, content=body, headers=headers)
        except UnsafeUrlError as exc:
            return SendResult(None, str(exc), took())
        except httpx.TimeoutException:
            return SendResult(None, "Timed out", took())
        except httpx.HTTPError as exc:
            return SendResult(None, f"Could not connect ({type(exc).__name__})", took())
        error = None if 200 <= resp.status_code < 300 else f"Answered HTTP {resp.status_code}"
        return SendResult(resp.status_code, error, took())


def default_sender() -> WebhookSender:
    return HttpSender(get_settings())


def get_webhook_sender() -> WebhookSender:
    """FastAPI dependency (tests override it)."""
    return default_sender()
