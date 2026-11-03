"""Razorpay: order creation (fake HTTP), checkout signature, webhook signature + idempotency."""

from __future__ import annotations

import json
from typing import Any

import httpx

from mitra_core.billing.providers import (
    MockProvider,
    RazorpayProvider,
    get_payment_provider,
    hmac_hex,
    provider_for,
)
from mitra_core.config import Settings
from mitra_core.main import app
from tests.billing_helpers import WEBHOOK_SECRET, configure, summary, tenant, topup
from tests.helpers import FakeClock

KEY_SECRET = "rzp_test_secret_abc"
WEBHOOK = "/v1/billing/webhooks/razorpay"


def _razorpay(orders: list[dict[str, Any]]) -> RazorpayProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/orders"
        assert request.headers["Authorization"].startswith("Basic ")
        body = json.loads(request.content)
        orders.append(body)
        return httpx.Response(200, json={"id": f"order_test{len(orders)}", **body})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RazorpayProvider("rzp_test_key", KEY_SECRET, client=client)


def _use(provider: RazorpayProvider) -> None:
    app.dependency_overrides[get_payment_provider] = lambda: provider


def _event(
    order: dict[str, Any], *, name: str = "payment.captured", amount: int | None = None
) -> bytes:
    entity = {
        "id": "pay_test123",
        "order_id": order["provider_order_id"],
        "amount": order["total_paise"] if amount is None else amount,
        "status": "captured",
    }
    return json.dumps({"event": name, "payload": {"payment": {"entity": entity}}}).encode()


async def _post(
    client: httpx.AsyncClient, raw: bytes, secret: str = WEBHOOK_SECRET
) -> httpx.Response:
    sig = hmac_hex(secret, raw)
    return await client.post(
        WEBHOOK,
        content=raw,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )


def test_provider_selection() -> None:
    assert isinstance(provider_for(Settings()), MockProvider)
    rzp = Settings(payment_provider="razorpay").model_copy(
        update={
            "razorpay_key_id": "rzp_test_x",
            "razorpay_key_secret": __import__("pydantic").SecretStr("s"),
        }
    )
    assert isinstance(provider_for(rzp), RazorpayProvider)


def test_mock_provider_refused_in_prod() -> None:
    import pytest
    from pydantic import SecretStr, ValidationError

    with pytest.raises(ValidationError, match="PAYMENT_PROVIDER=mock"):
        Settings(
            env="prod",
            jwt_secret=SecretStr("x" * 40),
            phone_hash_key=SecretStr("p" * 40),
            otp_hash_key=SecretStr("o" * 40),
            phone_enc_key=SecretStr("e" * 40),
            service_token=SecretStr("s" * 40),
        )


async def test_razorpay_checkout_then_webhook_credits_once(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure(razorpay_key_id="rzp_test_key")
    orders: list[dict[str, Any]] = []
    _use(_razorpay(orders))
    t = await tenant(client)
    resp = await topup(client, t["headers"], 10_000)
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "created"
    assert orders[0]["amount"] == 1_180_000  # incl. 18% GST
    assert orders[0]["currency"] == "INR"
    assert order["checkout"] == {
        "provider": "razorpay",
        "key_id": "rzp_test_key",
        "order_id": "order_test1",
        "amount": 1_180_000,
        "currency": "INR",
    }
    before = await summary(client, t["headers"])
    assert before["balance_paise"] == 0

    # Checkout callback with a forged signature is refused.
    bad = await client.post(
        f"/v1/billing/topups/{order['id']}/confirm",
        json={"payment_id": "pay_test123", "signature": "0" * 64},
        headers=t["headers"],
    )
    assert bad.status_code == 400
    good_sig = hmac_hex(KEY_SECRET, b"order_test1|pay_test123")
    ok = await client.post(
        f"/v1/billing/topups/{order['id']}/confirm",
        json={"payment_id": "pay_test123", "signature": good_sig},
        headers=t["headers"],
    )
    assert ok.json()["status"] == "paid"
    assert ok.json()["invoice_id"] is not None

    # The webhook for the same payment (and its retries) changes nothing.
    for _ in range(2):
        hook = await _post(client, _event(order))
        assert hook.status_code == 200
        assert hook.json() == {"status": "duplicate"}
    after = await summary(client, t["headers"])
    assert after["balance_paise"] == 1_000_000
    assert after["bonus_paise"] == before["bonus_paise"] + 50_000
    invoices = (await client.get("/v1/billing/invoices", headers=t["headers"])).json()["items"]
    assert len(invoices) == 1


async def test_webhook_alone_credits(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    _use(_razorpay([]))
    t = await tenant(client)
    order = (await topup(client, t["headers"], 500)).json()
    hook = await _post(client, _event(order, name="order.paid"))
    assert hook.json() == {"status": "credited"}
    assert (await _post(client, _event(order))).json() == {"status": "duplicate"}
    assert (await summary(client, t["headers"]))["balance_paise"] == 50_000


async def test_webhook_rejects_bad_signatures(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    _use(_razorpay([]))
    t = await tenant(client)
    order = (await topup(client, t["headers"], 500)).json()
    raw = _event(order)
    assert (await _post(client, raw, secret="wrong")).status_code == 400
    assert (await client.post(WEBHOOK, content=raw)).status_code == 400  # no signature
    tampered = raw.replace(b"captured", b"capturedX")
    sig = hmac_hex(WEBHOOK_SECRET, raw)
    resp = await client.post(WEBHOOK, content=tampered, headers={"X-Razorpay-Signature": sig})
    assert resp.status_code == 400
    assert (await summary(client, t["headers"]))["balance_paise"] == 0


async def test_webhook_disabled_without_secret(client: httpx.AsyncClient) -> None:
    resp = await client.post(WEBHOOK, content=b"{}", headers={"X-Razorpay-Signature": "x"})
    assert resp.status_code == 503


async def test_webhook_amount_mismatch_and_failure(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure()
    _use(_razorpay([]))
    t = await tenant(client)
    order = (await topup(client, t["headers"], 500)).json()
    assert (await _post(client, _event(order, amount=100))).json() == {"status": "amount_mismatch"}
    assert (await _post(client, _event(order, name="payment.failed"))).json() == {
        "status": "failed"
    }
    status = (await client.get(f"/v1/billing/topups/{order['id']}", headers=t["headers"])).json()
    assert status["status"] == "failed"
    assert (await summary(client, t["headers"]))["balance_paise"] == 0


async def test_webhook_unknown_order_and_other_events(
    client: httpx.AsyncClient, clock: FakeClock
) -> None:
    configure()
    fake = {"provider_order_id": "order_nope", "total_paise": 100}
    assert (await _post(client, _event(fake))).json() == {"status": "ignored"}
    raw = json.dumps({"event": "refund.created", "payload": {}}).encode()
    assert (await _post(client, raw)).json() == {"status": "ignored"}
    assert (await _post(client, b"not json")).status_code == 400
