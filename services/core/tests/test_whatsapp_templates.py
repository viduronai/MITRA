"""WhatsApp in production shape: template registry == docs, 24-hour window, flattening, named
parameters and buttons, blocked sends, name fallback, STOP opt-outs, template approval taps."""

from __future__ import annotations

import json
import re
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from mitra_core.approvals import request_approval
from mitra_core.db import tenant_session
from mitra_core.manager.customers import is_opt_out
from mitra_core.manager.inbound import handle_inbound
from mitra_core.manager.planner import RulesPlanner
from mitra_core.tenancy import TenantContext
from mitra_core.whatsapp import (
    CloudApiProvider,
    Document,
    TemplateMessage,
    notify_owner,
    send_customer_message,
    send_heads_up,
    send_text,
)
from mitra_core.whatsapp.inbound import InboundMessage
from mitra_core.whatsapp.provider import template_body
from mitra_core.whatsapp.templates import (
    LANGUAGES,
    TEMPLATES,
    TemplateError,
    body_params,
    flatten,
    prepare,
)
from tests.manager_helpers import make_business

ROOT = Path(__file__).resolve().parents[3]
SRC = Path(__file__).resolve().parents[1] / "src" / "mitra_core"
CUSTOMER = "+919811112222"
NOW = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)


# --- registry ------------------------------------------------------------------------------------


def _doc_bodies() -> dict[str, dict[str, str]]:
    doc = (ROOT / "docs" / "whatsapp-templates.md").read_text(encoding="utf-8")
    out: dict[str, dict[str, str]] = {}
    current = ""
    for line in doc.splitlines():
        if m := re.match(r"^### \d+[a-z]?\. `(\w+)`", line):
            current = m.group(1)
            out[current] = {}
        elif current and (m := re.match(r"^\| (en|hi|te) \| (.+) \|$", line)):
            out[current][m.group(1)] = m.group(2)
    return out


def test_registry_matches_the_doc_word_for_word() -> None:
    assert _doc_bodies() == {name: dict(s.bodies) for name, s in TEMPLATES.items()}


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_template_is_well_formed(name: str) -> None:
    s = TEMPLATES[name]
    assert s.category == "UTILITY"
    assert set(s.bodies) == set(LANGUAGES)
    for lang, body in s.bodies.items():
        assert sorted(set(body_params(body))) == sorted(s.params), (name, lang)
        assert not body.startswith("{{"), (name, lang)
        assert not body.endswith("}}"), (name, lang)
    assert len(s.quick_replies) <= 3


def test_every_template_the_code_sends_is_registered_in_all_languages() -> None:
    used: set[str] = set()
    pattern = re.compile(r"""template\s*=\s*["'](\w+)["']""")
    for path in SRC.rglob("*.py"):
        used |= set(pattern.findall(path.read_text(encoding="utf-8")))
    assert used, "the scan found no template sends"
    missing = sorted(used - set(TEMPLATES))
    assert missing == []
    for name in used:
        assert set(TEMPLATES[name].bodies) == set(LANGUAGES)


def test_flatten_and_prepare() -> None:
    assert flatten("Ravi\nwants\ta  2BHK      now ") == "Ravi wants a 2BHK now"
    assert len(flatten("x" * 500, 300)) == 300
    values = prepare(
        "owner_alert", "en", {"title": "Hot lead", "business": "B", "detail": "y" * 900}
    )
    assert len(values["detail"]) == 300
    with pytest.raises(TemplateError):
        prepare("owner_alert", "en", {"title": "x"})
    with pytest.raises(TemplateError):
        prepare("no_such_template", "en", {})
    assert (
        prepare("call_heads_up", "hi", {"name": "", "business": "B", "minutes": "2"})["name"]
        == "जी"
    )
    te = {"name": " ", "business": "B", "minutes": "2"}
    assert prepare("call_heads_up", "te", te)["name"] == "అండి"  # "నమస్కారం అండి,"
    assert prepare("call_heads_up", "te", te | {"name": "Ravi"})["name"] == "Ravi గారు"


def test_named_parameters_and_buttons_payload() -> None:
    body = template_body(
        TemplateMessage(
            "payment_reminder",
            "hi",
            {"business": "B", "amount": "500", "purpose": "fee", "due": "5 Nov"},
            payloads=["paid:123"],
            url_suffix="abc123",
        )
    )
    assert body["parameter_format"] == "NAMED"
    assert body["language"] == {"code": "hi"}
    params = body["components"][0]["parameters"]
    assert params[0] == {"type": "text", "parameter_name": "business", "text": "B"}
    url, quick = body["components"][1], body["components"][2]
    assert (url["sub_type"], url["index"], url["parameters"][0]["text"]) == ("url", "0", "abc123")
    assert (quick["sub_type"], quick["index"]) == ("quick_reply", "1")
    assert quick["parameters"] == [{"type": "payload", "payload": "paid:123"}]
    with pytest.raises(TemplateError):  # the Pay-now link needs its suffix
        template_body(
            TemplateMessage(
                "payment_link", "en", {"name": "R", "business": "B", "purpose": "p", "amount": "1"}
            )
        )
    doc = template_body(
        TemplateMessage(
            "share_document",
            "en",
            {"document": "price list", "business": "B"},
            document=Document("https://x/p.pdf", "p.pdf"),
        )
    )
    assert doc["components"][0]["type"] == "header"


async def test_cloud_provider_sends_named_template() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.T"}]})

    provider = CloudApiProvider("tok", "123", transport=httpx.MockTransport(handler))
    msg = TemplateMessage(
        "approval_request",
        "te",
        {"business": "B", "employee": "Priya", "summary": "S"},
        ["appr:1:1:approve", "appr:1:1:decline"],
    )
    result = await provider.send_template("+919800000001", msg)
    assert result.message_id == "wamid.T"
    assert seen[0]["type"] == "template"
    assert seen[0]["template"]["name"] == "approval_request"


# --- the 24-hour window --------------------------------------------------------------------------


def _session_for(biz: dict[str, Any]) -> AbstractAsyncContextManager[AsyncSession]:
    return tenant_session(TenantContext(business_id=uuid.UUID(biz["id"])))


async def _rows(admin: AsyncEngine, business_id: str) -> list[dict[str, Any]]:
    async with admin.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT direction, kind, purpose, status, template, body, buttons, ref, params,"
                " provider_message_id FROM wa_message WHERE business_id = :b ORDER BY created_at"
            ),
            {"b": uuid.UUID(business_id)},
        )
        return [dict(r._mapping) for r in rows]


async def _customer_writes(
    said: str, *, button: str | None = None, context: str | None = None
) -> str:
    msg = InboundMessage(
        CUSTOMER,
        "button_reply" if button else "text",
        f"wamid.{uuid.uuid4().hex}",
        text=said,
        button_id=button,
        context_id=context,
    )
    return await handle_inbound(
        msg, provider="sim", planner=RulesPlanner(), transcriber=None, now=NOW
    )


async def test_customer_gets_template_then_free_text_inside_window(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    bid = uuid.UUID(biz["id"])
    async with _session_for(biz) as session:
        await send_customer_message(
            session, bid, to_phone=CUSTOMER, template="enquiry_follow_up",
            params={"name": "Ravi", "topic": "2BHK in Kondapur"}, text="Hi Ravi, any questions?",
        )  # fmt: skip
        await session.commit()
    assert await _customer_writes("yes, price please") == "recorded"
    async with _session_for(biz) as session:
        await send_customer_message(
            session, bid, to_phone=CUSTOMER, template="enquiry_follow_up",
            params={"name": "Ravi", "topic": "2BHK"}, text="It is ₹60L.",
        )  # fmt: skip
        await session.commit()
    rows = await _rows(admin_engine, biz["id"])
    assert [(r["direction"], r["kind"]) for r in rows] == [
        ("out", "template"),
        ("in", "text"),
        ("out", "text"),
    ]
    # The business's first language is Telugu, and nothing about Ravi says otherwise.
    assert rows[0]["body"].startswith("నమస్కారం Ravi గారు, Sunrise Clinic నుంచి, 2BHK in Kondapur")
    assert rows[2]["body"] == "It is ₹60L."


async def test_free_text_outside_window_is_blocked_and_owner_told(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    async with _session_for(biz) as session:
        msg = await send_text(session, uuid.UUID(biz["id"]), to_phone=CUSTOMER, text="hello")
        await session.commit()
    assert msg is not None
    assert msg.status == "blocked"
    rows = await _rows(admin_engine, biz["id"])
    owner = [r for r in rows if r["purpose"] == "alert"]
    assert len(owner) == 1
    assert owner[0]["template"] == "owner_alert"
    assert owner[0]["body"].startswith("Alert: WhatsApp not sent at Sunrise Clinic.")


async def test_owner_alert_free_text_once_owner_has_written(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    bid = uuid.UUID(biz["id"])
    async with _session_for(biz) as session:
        await notify_owner(session, bid, "hot_lead", "Ravi wants a visit", url_suffix="calls/1")
        await session.commit()
    res = await client.post(
        "/v1/manager/whatsapp-sim/inbound",
        json={"kind": "text", "text": "help"},
        headers=biz["headers"],
    )
    assert res.status_code == 200
    async with _session_for(biz) as session:
        await notify_owner(session, bid, "hot_lead", "Lakshmi wants a call", url_suffix="calls/2")
        await session.commit()
    alerts = [r for r in await _rows(admin_engine, biz["id"]) if r["purpose"] == "alert"]
    assert [a["kind"] for a in alerts] == ["template", "text"]
    assert alerts[0]["buttons"] == [
        {"url": "http://localhost:3000/calls/1", "title": "Open in Mitra"}
    ]
    assert alerts[1]["body"] == "Lakshmi wants a call"


async def test_heads_up_name_fallback_in_hindi(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["hi", "en"])
    async with _session_for(biz) as session:
        await send_heads_up(
            session, uuid.UUID(biz["id"]), phone_e164=CUSTOMER, name=None,
            employee_id=None, eta_seconds=120, source="lead",
        )  # fmt: skip
        await session.commit()
    row = (await _rows(admin_engine, biz["id"]))[0]
    assert row["params"]["language"] == "hi"
    assert row["body"].startswith("नमस्ते जी, हम Sunrise Clinic से हैं।")
    assert "there" not in row["body"]
    assert [b["id"] for b in row["buttons"]] == ["call_later", "opt_out"]


# --- opt-out (CMP-06) ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("STOP", True),
        ("stop.", True),
        ("Please don't call me again", True),
        ("Don’t call me", True),  # noqa: RUF001 (curly apostrophe)
        ("कॉल मत करो", True),
        ("bhai call mat karo", True),
        ("దయచేసి call చేయకండి", True),
        ("call cheyakandi", True),
        ("Is there a bus stop near the clinic?", False),
        ("call me at 5", False),
        ("రేపు రండి", False),
    ],
)
def test_opt_out_phrases(said: str, expected: bool) -> None:
    assert is_opt_out(said) is expected


async def _opt_outs(admin: AsyncEngine, business_id: str) -> int:
    async with admin.connect() as conn:
        return int(
            await conn.scalar(
                text("SELECT count(*) FROM opt_out WHERE business_id = :b AND purpose IS NULL"),
                {"b": uuid.UUID(business_id)},
            )
            or 0
        )


async def test_stop_in_hindi_opts_out_and_confirms_in_hindi(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    bid = uuid.UUID(biz["id"])
    async with _session_for(biz) as session:
        await send_heads_up(
            session,
            bid,
            phone_e164=CUSTOMER,
            name="Ravi",
            employee_id=None,
            eta_seconds=120,
            source="lead",
        )
        await session.commit()
    assert await _customer_writes("कॉल मत करो") == "opted_out"
    assert await _customer_writes("कॉल मत करो") == "opted_out"  # idempotent
    assert await _opt_outs(admin_engine, biz["id"]) == 1
    rows = await _rows(admin_engine, biz["id"])
    confirm = [r for r in rows if r["ref"].get("kind") == "opt_out_confirmation"]
    assert confirm[0]["body"] == "ठीक है। Sunrise Clinic अब आपको call या message नहीं करेगा।"
    async with _session_for(biz) as session:
        later = await send_customer_message(
            session, bid, to_phone=CUSTOMER, template="enquiry_follow_up",
            params={"name": "Ravi", "topic": "2BHK"},
        )  # fmt: skip
        await session.commit()
    assert later is not None
    assert later.status == "blocked"


async def test_dont_call_me_button_opts_out(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client, languages=["te", "en"])
    async with _session_for(biz) as session:
        await send_heads_up(
            session,
            uuid.UUID(biz["id"]),
            phone_e164=CUSTOMER,
            name="Ravi",
            employee_id=None,
            eta_seconds=60,
            source="lead",
        )
        await session.commit()
    sent = (await _rows(admin_engine, biz["id"]))[0]
    outcome = await _customer_writes(
        "Don't call me", button="opt_out", context=sent["provider_message_id"]
    )
    assert outcome == "opted_out"
    assert await _opt_outs(admin_engine, biz["id"]) == 1
    confirm = (await _rows(admin_engine, biz["id"]))[-1]
    assert confirm["body"].startswith("సరే. Sunrise Clinic")


async def test_stranger_is_ignored(client: httpx.AsyncClient) -> None:
    await make_business(client)
    assert await _customer_writes("STOP") == "unknown_sender"


# --- approvals outside the window ----------------------------------------------------------------


async def test_template_approval_card_tap_approves(
    client: httpx.AsyncClient, admin_engine: AsyncEngine
) -> None:
    biz = await make_business(client)
    bid = uuid.UUID(biz["id"])
    async with _session_for(biz) as session:
        approval = await request_approval(
            session, bid, kind="refund", summary="Refund\n₹2,000 to Lakshmi",
            payload={"rupees": 2000}, requested_by="call:x",
        )  # fmt: skip
        await session.commit()
    card = (await _rows(admin_engine, biz["id"]))[0]
    assert card["template"] == "approval_request"
    assert card["body"] == (
        "Approval needed at Sunrise Clinic: Mitra needs your OK. Refund ₹2,000 to Lakshmi "
        "Tap a button below."
    )
    approve = card["buttons"][0]["id"]
    assert approve == f"appr:{approval.id}:1:approve"
    # Meta delivers a template quick-reply tap as type "button" with the payload.
    tap = InboundMessage(
        biz["owner"].phone,
        "button_reply",
        "wamid.t",
        text="Approve",
        button_id=approve,
        context_id=card["provider_message_id"],
    )
    outcome = await handle_inbound(
        tap, provider="sim", planner=RulesPlanner(), transcriber=None, now=datetime.now(UTC)
    )
    assert outcome == "decided"
    detail = (await client.get(f"/v1/approvals/{approval.id}", headers=biz["headers"])).json()
    assert detail["approval"]["status"] == "approved"
