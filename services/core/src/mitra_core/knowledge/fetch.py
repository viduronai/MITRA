"""SSRF-guarded web page fetcher for "learn from link".

Every hop (the first URL and each redirect, at most ``MAX_REDIRECTS``) is checked the same way:
http(s) only, no credentials in the URL, a web port, and EVERY address the host resolves to
must be public (``ipaddress.is_global``; this rejects private, loopback, link-local incl. the
169.254.169.254 metadata endpoint, CGNAT, reserved and multicast ranges, also when wrapped as
IPv4-mapped IPv6). The connection is then made to the vetted IP itself, with the original
``Host`` header and TLS SNI/certificate name, so a second DNS lookup (DNS rebinding) cannot
swap in a different address. Proxies from the environment are ignored for the same reason.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 3
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
_ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_USER_AGENT = "MitraBot/0.1 (business knowledge import)"

Resolver = Callable[[str, int], Awaitable[list[str]]]


class FetchError(Exception):
    """A user-presentable reason the page could not be fetched."""


class BlockedAddressError(FetchError):
    pass


async def resolve_host(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    content_type: str
    text: str


@dataclass(slots=True)
class Fetcher:
    """Injectable (a FastAPI dependency) so tests can supply a mock transport and resolver."""

    transport: httpx.AsyncBaseTransport | None = None
    resolver: Resolver = field(default=resolve_host)

    async def fetch(self, url: str) -> FetchedPage:
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):
                return await self._fetch(url)
        except TimeoutError:
            raise FetchError("The website took too long to respond (10 s limit).") from None

    async def _fetch(self, url: str) -> FetchedPage:
        async with httpx.AsyncClient(
            transport=self.transport,
            follow_redirects=False,
            timeout=TIMEOUT_SECONDS,
            trust_env=False,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,text/plain;q=0.8"},
        ) as client:
            current = httpx.URL(url)
            for _ in range(MAX_REDIRECTS + 1):
                ip = await self._vet(current)
                request = client.build_request(
                    "GET",
                    current.copy_with(host=ip),
                    headers={"Host": _host_header(current)},
                    extensions={"sni_hostname": current.host},
                )
                try:
                    response = await client.send(request, stream=True)
                except httpx.HTTPError as exc:
                    raise FetchError("Could not connect to the website.") from exc
                try:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("The website sent a redirect without a location.")
                        current = current.join(location)
                        continue
                    return await _read(response, str(current))
                finally:
                    await response.aclose()
            raise FetchError(f"Too many redirects (more than {MAX_REDIRECTS}).")

    async def _vet(self, url: httpx.URL) -> str:
        """Validate one hop and return the IP to connect to."""
        if url.scheme not in {"http", "https"}:
            raise FetchError("Only http and https links are supported.")
        if url.userinfo:
            raise FetchError("Links with a username or password are not supported.")
        if not url.host:
            raise FetchError("The link has no host name.")
        port = url.port or (443 if url.scheme == "https" else 80)
        if port not in ALLOWED_PORTS:
            raise FetchError("Only standard web ports are supported.")
        try:
            addresses = [ipaddress.ip_address(url.host)]
        except ValueError:
            try:
                resolved = await self.resolver(url.host, port)
            except OSError as exc:
                raise FetchError("The website's address could not be found.") from exc
            try:
                addresses = [ipaddress.ip_address(a.split("%", 1)[0]) for a in resolved]
            except ValueError as exc:
                raise FetchError("The website's address could not be found.") from exc
        if not addresses:
            raise FetchError("The website's address could not be found.")
        if not all(is_public_ip(a) for a in addresses):
            raise BlockedAddressError(
                "This link points to a private or reserved network address and can't be used."
            )
        return str(addresses[0])


def _host_header(url: httpx.URL) -> str:
    host = url.host if ":" not in url.host else f"[{url.host}]"
    return host if url.port is None else f"{host}:{url.port}"


async def _read(response: httpx.Response, url: str) -> FetchedPage:
    if response.status_code >= 400:
        raise FetchError(f"The website answered with HTTP {response.status_code}.")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in _ALLOWED_TYPES:
        raise FetchError("The link is not a web page (unsupported content type).")
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise FetchError("The page is larger than 2 MB.")
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > MAX_BYTES:
            raise FetchError("The page is larger than 2 MB.")
    encoding = response.charset_encoding or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    return FetchedPage(url=url, content_type=content_type or "text/html", text=text)


def get_fetcher() -> Fetcher:
    """FastAPI dependency."""
    return Fetcher()
