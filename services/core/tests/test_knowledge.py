"""Knowledge API: text + URL sources (network mocked), facts CRUD, gaps, SSRF guard."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from mitra_core.knowledge.fetch import MAX_BYTES, Fetcher, get_fetcher
from mitra_core.main import app
from mitra_core.models.enums import MemberRole
from tests.helpers import add_fact, add_member, create_business, new_actor

PUBLIC_IP = "93.184.216.34"
DNS = {
    "sunrise.example": [PUBLIC_IP],
    "hop.example": ["93.184.216.35"],
    "internal.example": ["10.0.0.7"],
    "mixed.example": [PUBLIC_IP, "127.0.0.1"],
    "metadata.example": ["169.254.169.254"],
    "mapped.example": ["::ffff:192.168.1.1"],
}
PAGE = (
    "<html><head><title>Sunrise Clinic</title></head><body>"
    "<p>Consultation fee: ₹500</p><p>Open Mon-Sat 9 AM - 8 PM</p>"
    "<p>Call 98480 12345</p></body></html>"
)

Handler = Callable[[httpx.Request], httpx.Response]


async def _resolver(host: str, port: int) -> list[str]:
    if host not in DNS:
        raise OSError("no such host")
    return DNS[host]


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def _use_network(handler: Handler) -> Recorder:
    recorder = Recorder(handler)
    fetcher = Fetcher(transport=httpx.MockTransport(recorder), resolver=_resolver)
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    return recorder


def _html(body: str = PAGE, **headers: str) -> httpx.Response:
    return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})


async def _setup(client: httpx.AsyncClient, industry: str = "clinic") -> dict[str, str]:
    owner = new_actor()
    business = await create_business(client, owner, industry=industry)
    return owner.headers(business["id"])


async def _add_url(client: httpx.AsyncClient, headers: dict[str, str], url: str) -> dict[str, Any]:
    resp = await client.post(
        "/v1/knowledge/sources", json={"type": "url", "url": url}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "processing"
    # ASGITransport runs background tasks before returning, so the source is final now.
    sources = (await client.get("/v1/knowledge/sources", headers=headers)).json()
    return next(s for s in sources if s["id"] == resp.json()["id"])


async def test_text_source_creates_facts(client: httpx.AsyncClient) -> None:
    headers = await _setup(client)
    text = "Sunrise Clinic\nConsultation fee: ₹500\nTimings: 9 AM - 8 PM\nCall 98480 12345"
    resp = await client.post(
        "/v1/knowledge/sources", json={"type": "text", "text": text}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    source = resp.json()
    assert (source["type"], source["status"], source["title"]) == (
        "text",
        "ready",
        "Sunrise Clinic",
    )
    assert source["error"] is None

    facts = (await client.get("/v1/knowledge/facts", headers=headers)).json()
    summary = {(f["category"], f["key"], f["value"], f["status"]) for f in facts}
    assert ("prices", "Consultation fee", "₹500", "confirmed") in summary
    assert ("timings", "Timings", "9 AM - 8 PM", "confirmed") in summary
    assert ("contact", "Phone", "+919848012345", "suggested") in summary
    assert all(f["source_id"] == source["id"] for f in facts)


async def test_url_source_extracts_suggested_facts(client: httpx.AsyncClient) -> None:
    recorder = _use_network(lambda request: _html())
    headers = await _setup(client)
    source = await _add_url(client, headers, "https://sunrise.example/about")
    assert source["status"] == "ready", source
    assert source["title"] == "Sunrise Clinic"
    assert source["url"] == "https://sunrise.example/about"

    request = recorder.requests[0]
    assert request.url.host == PUBLIC_IP  # connected to the vetted IP ...
    assert request.headers["host"] == "sunrise.example"  # ... for the original host
    assert request.extensions["sni_hostname"] == "sunrise.example"

    facts = (await client.get("/v1/knowledge/facts", headers=headers)).json()
    assert {f["status"] for f in facts} == {"suggested"}
    keys = {(f["category"], f["key"]) for f in facts}
    assert {("prices", "Consultation fee"), ("timings", "Opening hours")} <= keys
    assert ("contact", "Phone") in keys


async def test_url_follows_safe_redirects(client: httpx.AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["host"] == "hop.example":
            return httpx.Response(301, headers={"location": "https://sunrise.example/home"})
        return _html()

    recorder = _use_network(handler)
    headers = await _setup(client)
    source = await _add_url(client, headers, "http://hop.example/")
    assert source["status"] == "ready", source
    assert [r.headers["host"] for r in recorder.requests] == ["hop.example", "sunrise.example"]


@pytest.mark.parametrize(
    "url",
    [
        "http://internal.example/",
        "http://mixed.example/",
        "http://metadata.example/latest/meta-data/",
        "http://mapped.example/",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://10.1.2.3/",
        "http://100.100.100.200/",  # CGNAT range (also a cloud metadata address)
        "http://0.0.0.0/",
    ],
)
async def test_ssrf_blocks_private_addresses(client: httpx.AsyncClient, url: str) -> None:
    recorder = _use_network(lambda request: _html())
    headers = await _setup(client)
    source = await _add_url(client, headers, url)
    assert source["status"] == "failed"
    assert "private or reserved" in source["error"]
    assert recorder.requests == []
    assert (await client.get("/v1/knowledge/facts", headers=headers)).json() == []


async def test_ssrf_blocks_redirect_to_private_address(client: httpx.AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example/secret"})

    recorder = _use_network(handler)
    headers = await _setup(client)
    source = await _add_url(client, headers, "https://sunrise.example/")
    assert source["status"] == "failed"
    assert "private or reserved" in source["error"]
    assert len(recorder.requests) == 1  # the private hop was never requested


async def test_redirect_limit(client: httpx.AsyncClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.params.get("n", "0"))
        return httpx.Response(302, headers={"location": f"/loop?n={n + 1}"})

    recorder = _use_network(handler)
    headers = await _setup(client)
    source = await _add_url(client, headers, "https://sunrise.example/loop")
    assert source["status"] == "failed"
    assert "Too many redirects" in source["error"]
    assert len(recorder.requests) == 4  # the original request + 3 redirects


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            httpx.Response(
                200, content=b"x" * (MAX_BYTES + 1), headers={"content-type": "text/html"}
            ),
            "larger than 2 MB",
        ),
        (
            httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
            "not a web page",
        ),
        (httpx.Response(404, text="nope"), "HTTP 404"),
    ],
)
async def test_fetch_failures_are_reported(
    client: httpx.AsyncClient, response: httpx.Response, message: str
) -> None:
    _use_network(lambda request: response)
    headers = await _setup(client)
    source = await _add_url(client, headers, "https://sunrise.example/")
    assert source["status"] == "failed"
    assert message in source["error"]


async def test_unresolvable_host_and_bad_ports(client: httpx.AsyncClient) -> None:
    _use_network(lambda request: _html())
    headers = await _setup(client)
    source = await _add_url(client, headers, "https://nowhere.example/")
    assert "could not be found" in source["error"]
    source = await _add_url(client, headers, "http://sunrise.example:22/")
    assert "standard web ports" in source["error"]
    source = await _add_url(client, headers, "http://user:pw@sunrise.example/")
    assert "username or password" in source["error"]


@pytest.mark.parametrize(
    "body",
    [
        {"type": "url", "url": "file:///etc/passwd"},
        {"type": "url", "url": "ftp://sunrise.example/"},
        {"type": "url", "url": "gopher://sunrise.example/"},
        {"type": "url", "url": "not a url"},
        {"type": "text", "text": "   "},
        {"type": "text", "text": "x" * 20_001},
        {"type": "pdf", "url": "https://sunrise.example/"},
        {"type": "text"},
    ],
)
async def test_source_validation(client: httpx.AsyncClient, body: dict[str, Any]) -> None:
    headers = await _setup(client)
    resp = await client.post("/v1/knowledge/sources", json=body, headers=headers)
    assert resp.status_code == 422, body


async def test_fact_crud(client: httpx.AsyncClient) -> None:
    headers = await _setup(client)
    fact = await add_fact(client, headers, "prices", "Consultation fee", "₹400")
    assert fact["status"] == "confirmed"
    assert fact["source_id"] is None

    resp = await client.patch(
        f"/v1/knowledge/facts/{fact['id']}", json={"value": "₹500"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "₹500"
    resp = await client.patch(
        f"/v1/knowledge/facts/{fact['id']}", json={"status": "suggested"}, headers=headers
    )
    assert resp.json()["status"] == "suggested"
    for bad in ({"value": None}, {"status": "maybe"}, {"key": "x"}, {"value": "x" * 501}):
        resp = await client.patch(f"/v1/knowledge/facts/{fact['id']}", json=bad, headers=headers)
        assert resp.status_code == 422, bad

    resp = await client.delete(f"/v1/knowledge/facts/{fact['id']}", headers=headers)
    assert resp.status_code == 204
    assert resp.content == b""
    assert (await client.get("/v1/knowledge/facts", headers=headers)).json() == []
    resp = await client.delete(f"/v1/knowledge/facts/{fact['id']}", headers=headers)
    assert resp.status_code == 404


async def test_fact_validation(client: httpx.AsyncClient) -> None:
    headers = await _setup(client)
    for body in (
        {"category": "gossip", "key": "k", "value": "v"},
        {"category": "faq", "key": "", "value": "v"},
        {"category": "faq", "key": "k"},
    ):
        resp = await client.post("/v1/knowledge/facts", json=body, headers=headers)
        assert resp.status_code == 422, body


async def test_fact_create_is_idempotent(client: httpx.AsyncClient) -> None:
    headers = await _setup(client)
    body = {"category": "faq", "key": "Languages", "value": "Telugu, Hindi"}
    keyed = headers | {"Idempotency-Key": "fact-1"}
    first = await client.post("/v1/knowledge/facts", json=body, headers=keyed)
    second = await client.post("/v1/knowledge/facts", json=body, headers=keyed)
    assert second.json() == first.json()
    assert second.headers["idempotent-replayed"] == "true"
    assert len((await client.get("/v1/knowledge/facts", headers=headers)).json()) == 1


async def test_gaps_shrink_as_facts_are_added(client: httpx.AsyncClient) -> None:
    headers = await _setup(client)
    gaps = (await client.get("/v1/knowledge/gaps", headers=headers)).json()
    assert [g["key"] for g in gaps] == [
        "Consultation fee",
        "Timings",
        "Doctors",
        "Address",
        "Parking",
        "Google Maps link",
    ]
    assert gaps[0] == {
        "category": "prices",
        "key": "Consultation fee",
        "question": "What is your consultation fee?",
        "source": "checklist",
        "call_id": None,
    }
    await add_fact(client, headers, "prices", "Consultation fee", "₹500")
    await add_fact(client, headers, "location", "Parking", "Free basement parking")
    gaps = (await client.get("/v1/knowledge/gaps", headers=headers)).json()
    assert [g["key"] for g in gaps] == ["Timings", "Doctors", "Address", "Google Maps link"]

    realty = await _setup(client, industry="real_estate")
    gaps = (await client.get("/v1/knowledge/gaps", headers=realty)).json()
    assert [g["key"] for g in gaps] == [
        "Projects",
        "Price range",
        "Address",
        "Site-visit timings",
        "Google Maps link",
    ]


async def test_staff_can_read_but_not_teach(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    owner = new_actor()
    business = await create_business(client, owner)
    fact = await add_fact(client, owner.headers(business["id"]), "faq", "Languages", "Telugu")
    staff = (await add_member(admin_engine, business["id"], MemberRole.STAFF)).headers(
        business["id"]
    )
    for path in ("/v1/knowledge/facts", "/v1/knowledge/sources", "/v1/knowledge/gaps"):
        assert (await client.get(path, headers=staff)).status_code == 200, path
    writes = [
        client.post(
            "/v1/knowledge/facts", json={"category": "faq", "key": "k", "value": "v"}, headers=staff
        ),
        client.post("/v1/knowledge/sources", json={"type": "text", "text": "a: b"}, headers=staff),
        client.patch(f"/v1/knowledge/facts/{fact['id']}", json={"value": "x"}, headers=staff),
        client.delete(f"/v1/knowledge/facts/{fact['id']}", headers=staff),
    ]
    for request in writes:
        assert (await request).status_code == 403


async def test_knowledge_requires_business_scope(client: httpx.AsyncClient) -> None:
    actor = new_actor()
    resp = await client.get("/v1/knowledge/facts", headers=actor.headers())
    assert resp.status_code == 403
    resp = await client.get(f"/v1/knowledge/facts/{uuid.uuid4()}", headers=actor.headers())
    assert resp.status_code == 405
