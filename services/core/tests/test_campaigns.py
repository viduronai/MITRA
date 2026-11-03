"""Campaigns API (CALL-15/16): list import, start, buckets, pause/resume, extend, export, RLS."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from mitra_core.dialer import hooks
from mitra_core.dialer.csvimport import ListError, normalize_phone, parse_list
from mitra_core.dialer.voice import DialRejectedError
from mitra_core.models.enums import CallResult
from mitra_core.telephony.enums import AttemptOutcome
from tests.dialer_helpers import configure, consent, morning_clock, opt_out, tenant, tick
from tests.helpers import FakeClock

CSV = (
    "Name,Phone,Interest\n"
    "Ravi,98765 00001,2BHK\n"
    "Lakshmi,+91 98765-00002,Plot\n"
    "Arjun,098765 00003,Villa\n"
    "Dup,9876500001,2BHK\n"
    "Bad,12345,-\n"
)
PHONES = ["+919876500001", "+919876500002", "+919876500003"]


def test_normalize_phone() -> None:
    assert normalize_phone("98765 43210") == "+919876543210"
    assert normalize_phone("098765-43210") == "+919876543210"
    assert normalize_phone("919876543210") == "+919876543210"
    assert normalize_phone("+91 (98765) 43210") == "+919876543210"
    assert normalize_phone("+14155550100") is None
    assert normalize_phone("12345") is None


def test_parse_list_headers_and_paste() -> None:
    parsed = parse_list(CSV)
    assert parsed.phone_column == "Phone"
    assert parsed.name_column == "Name"
    assert parsed.column_map == {"Name": "lead_name", "Interest": "interest"}
    assert [r.phone for r in parsed.rows] == PHONES
    assert parsed.rows[0].variables == {"lead_name": "Ravi", "interest": "2BHK"}
    assert (parsed.duplicates, parsed.invalid) == (1, 1)

    pasted = parse_list("Ravi\t9876500001\tKondapur\nSita\t9876500002\tKukatpally\n")
    assert pasted.phone_column == "column_2"
    assert pasted.name_column == "column_1"
    assert pasted.rows[1].name == "Sita"
    assert pasted.rows[1].variables == {"lead_name": "Sita", "column_3": "Kukatpally"}

    custom = parse_list(CSV, column_map={"Interest": "property"})
    assert custom.rows[0].variables == {"property": "2BHK"}
    with pytest.raises(ListError):
        parse_list("name,city\nRavi,Hyd\n")
    with pytest.raises(ListError):
        parse_list(CSV, column_map={"Nope": "x"})
    with pytest.raises(ListError):
        parse_list(CSV, max_rows=2)


async def _create(client: httpx.AsyncClient, t: dict[str, Any], **extra: Any) -> dict[str, Any]:
    body = {
        "name": "Diwali offer",
        "employee_id": t["employee"]["id"],
        "text": CSV,
        "consent_attested": True,  # the owner's list tick (docs/08 section 8.5)
    } | extra
    resp = await client.post("/v1/campaigns", json=body, headers=t["headers"])
    assert resp.status_code == 201, resp.text
    return resp.json()  # type: ignore[no-any-return]


async def _action(client: httpx.AsyncClient, t: dict[str, Any], cid: str, action: str) -> Any:
    return await client.post(f"/v1/campaigns/{cid}/{action}", headers=t["headers"])


async def test_preview_and_sample(client: httpx.AsyncClient) -> None:
    configure()
    t = await tenant(client, number=False)
    resp = await client.post("/v1/campaigns/preview", json={"text": CSV}, headers=t["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["valid"], body["invalid"], body["duplicates"]) == (3, 1, 1)
    assert body["sample"][0] == {
        "row_number": 1,
        "phone_last4": "0001",
        "name": "Ravi",
        "variables": {"lead_name": "Ravi", "interest": "2BHK"},
    }
    assert "+91" not in str(body["sample"])
    resp = await client.get("/v1/campaigns/sample.csv", headers=t["headers"])
    assert resp.status_code == 200
    assert resp.text.startswith("name,phone")
    bad = await client.post("/v1/campaigns/preview", json={"text": "a,b\n"}, headers=t["headers"])
    assert bad.status_code == 422


async def test_campaign_runs_to_buckets(
    client: httpx.AsyncClient, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    voice, _ = configure()
    morning_clock(clock)
    events: list[tuple[str, dict[str, Any]]] = []

    async def fake_emit(
        _s: Any, _b: Any, event: str, payload: dict[str, Any], **_: Any
    ) -> list[Any]:
        events.append((event, payload))
        return []

    from mitra_core.webhooks import service as webhooks

    monkeypatch.setattr(webhooks, "emit_event", fake_emit)
    t = await tenant(client)
    await opt_out(client, t, PHONES[2])  # the third asked not to be called
    created = await _create(client, t)
    assert (created["added"], created["invalid"], created["duplicates"]) == (3, 1, 1)
    campaign = created["campaign"]
    assert campaign["status"] == "draft"
    assert campaign["variables"] == ["interest", "lead_name"]
    assert campaign["progress"]["remaining"] == 3
    assert campaign["progress"]["eta_minutes"] == 1  # 3 x 90 s / 5 channels

    voice.script["0001"] = (AttemptOutcome.ANSWERED, CallResult.BOOKED)
    voice.script["0002"] = (AttemptOutcome.ANSWERED, CallResult.NOT_INTERESTED)
    resp = await _action(client, t, campaign["id"], "start")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    await tick(client)

    detail = (await client.get(f"/v1/campaigns/{campaign['id']}", headers=t["headers"])).json()
    assert detail["status"] == "completed"
    buckets = detail["progress"]["buckets"]
    assert buckets["interested"] == 1
    assert buckets["not_interested"] == 1
    assert buckets["blocked"] == 1
    assert detail["progress"]["blocked_summary"] == ["1 person skipped: asked not to be called"]
    assert {p.variables["interest"] for p in voice.placed} == {"2BHK", "Plot"}
    [(event, payload)] = events
    assert event == "campaign.finished"
    assert (payload["total"], payload["called"], payload["connected"]) == (3, 2, 2)

    contacts = await client.get(
        f"/v1/campaigns/{campaign['id']}/contacts?bucket=blocked", headers=t["headers"]
    )
    assert contacts.json()["total"] == 1
    assert contacts.json()["items"][0]["reasons"] == ["opted_out"]

    export = await client.get(f"/v1/campaigns/{campaign['id']}/export.csv", headers=t["headers"])
    assert export.status_code == 200
    lines = export.text.strip().splitlines()
    assert lines[0].startswith("row,name,phone,status,result")
    assert "+919876500001" in lines[1]
    assert ",interested," in lines[1]

    listed = (await client.get("/v1/campaigns", headers=t["headers"])).json()
    assert [c["id"] for c in listed["items"]] == [campaign["id"]]


async def test_pause_resume_edit_extend(client: httpx.AsyncClient, clock: FakeClock) -> None:
    voice, _ = configure()
    morning_clock(clock)
    t = await tenant(client)
    await consent(client, t, *PHONES, "+919876500004")
    cid = (await _create(client, t))["campaign"]["id"]
    assert (await _action(client, t, cid, "pause")).status_code == 409  # still a draft
    await _action(client, t, cid, "start")
    paused = await _action(client, t, cid, "pause")
    assert paused.json()["status"] == "paused"
    assert (await tick(client))["dialed"] == 0

    edit = await client.patch(
        f"/v1/campaigns/{cid}",
        json={"retry_ladder": [60], "avg_call_seconds": 120, "name": "Diwali v2"},
        headers=t["headers"],
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["retry_ladder"] == [60]
    assert edit.json()["progress"]["eta_minutes"] is None  # frozen while paused

    resumed = await _action(client, t, cid, "resume")
    assert resumed.json()["status"] == "running"
    assert (await tick(client))["dialed"] == 3

    more = await client.post(
        f"/v1/campaigns/{cid}/contacts",
        json={
            "text": "Name,Phone,Interest\nNew,9876500004,Shop\nRavi,9876500001,2BHK\n",
            "consent_attested": True,
        },
        headers=t["headers"],
    )
    assert more.status_code == 200, more.text
    # Ravi was called a moment ago (skip_recent_days=7): not added twice, not called again.
    assert more.json()["added"] == 1
    await tick(client)
    assert len(voice.placed) >= 4


async def test_skip_recent_and_calling_days(client: httpx.AsyncClient, clock: FakeClock) -> None:
    voice, _ = configure()
    morning_clock(clock)
    t = await tenant(client)
    await consent(client, t, *PHONES)
    first = (await _create(client, t, text="Phone\n9876500001\n"))["campaign"]["id"]
    await _action(client, t, first, "start")
    await tick(client)
    created = await _create(client, t, skip_recent_days=7)
    assert created["skipped_recent"] == 1
    assert created["campaign"]["progress"]["skipped"] == 1
    await _action(client, t, created["campaign"]["id"], "start")

    # Today (Monday) is a holiday: the campaign waits for Tuesday.
    holiday = await _create(
        client,
        t,
        text="Phone\n9876500002\n",
        skip_recent_days=0,
        holidays=[clock.now.date().isoformat()],
    )
    await _action(client, t, holiday["campaign"]["id"], "start")
    placed = len(voice.placed)
    await tick(client)
    assert len(voice.placed) == placed + 2  # the other campaign's two people, not this one
    clock.advance(24 * 3600)
    await tick(client)
    holiday_job = [p for p in voice.placed[placed + 2 :] if p.phone_e164 == PHONES[1]]
    assert holiday_job, "the holiday campaign calls on the next calling day"


async def test_carrier_rejections_auto_pause(
    client: httpx.AsyncClient, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    voice, _ = configure(strike_limit=2)
    morning_clock(clock)
    alerts: list[dict[str, Any]] = []

    async def fake_alert(_s: Any, business_id: uuid.UUID, **kw: Any) -> None:
        alerts.append({"business_id": business_id} | kw)

    monkeypatch.setattr(hooks, "alert_owner", fake_alert)
    t = await tenant(client)
    await consent(client, t, *PHONES)
    for last4 in ("0001", "0002", "0003"):
        voice.script[last4] = DialRejectedError("carrier said no")
    cid = (await _create(client, t))["campaign"]["id"]
    await _action(client, t, cid, "start")
    report = await tick(client)
    assert report["paused_campaigns"] == [cid]
    detail = (await client.get(f"/v1/campaigns/{cid}", headers=t["headers"])).json()
    assert (detail["status"], detail["pause_reason"]) == ("paused", "carrier_rejected")
    assert alerts[0]["kind"] == "campaign_paused"
    assert alerts[0]["link"] == f"/campaigns/{cid}"


async def test_big_list_needs_approval(
    client: httpx.AsyncClient, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure()
    morning_clock(clock)

    async def always(*_a: Any) -> bool:
        return True

    monkeypatch.setattr(hooks, "needs_list_approval", always)
    t = await tenant(client)
    await consent(client, t, *PHONES)
    cid = (await _create(client, t))["campaign"]["id"]
    started = await _action(client, t, cid, "start")
    assert started.json()["status"] == "pending_approval"
    approval_id = started.json()["approval_id"]
    assert (await tick(client))["dialed"] == 0

    from mitra_core.approvals.service import _handlers
    from mitra_core.db import tenant_session
    from mitra_core.models import Approval
    from mitra_core.tenancy import TenantContext

    bid = uuid.UUID(t["business"]["id"])
    async with tenant_session(TenantContext(business_id=bid)) as s:
        approval = await s.get(Approval, uuid.UUID(approval_id))
        assert approval is not None
        assert approval.kind == "list_call"
        assert approval.payload["contacts"] == 3
        approval.status, approval.decided_at = "approved", clock.now
        await _handlers["list_call"](s, approval)
        await s.commit()
    detail = (await client.get(f"/v1/campaigns/{cid}", headers=t["headers"])).json()
    assert detail["status"] == "running"
    assert (await tick(client))["dialed"] == 3


async def test_edited_approval_calls_only_approved_people(
    client: httpx.AsyncClient, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """APPR-06: the owner edits 3 people down to 2; only the first 2 are called."""
    voice, _ = configure()
    morning_clock(clock)

    async def always(*_a: Any) -> bool:
        return True

    monkeypatch.setattr(hooks, "needs_list_approval", always)
    t = await tenant(client)
    await consent(client, t, *PHONES)
    cid = (await _create(client, t))["campaign"]["id"]
    approval_id = (await _action(client, t, cid, "start")).json()["approval_id"]
    for last4 in ("0001", "0002"):
        voice.script[last4] = (AttemptOutcome.ANSWERED, CallResult.INTERESTED)

    from mitra_core.approvals.service import _handlers
    from mitra_core.db import tenant_session
    from mitra_core.models import Approval
    from mitra_core.tenancy import TenantContext

    bid = uuid.UUID(t["business"]["id"])
    async with tenant_session(TenantContext(business_id=bid)) as s:
        approval = await s.get(Approval, uuid.UUID(approval_id))
        assert approval is not None
        approval.payload = {**approval.payload, "contacts": 2}  # edited before approving
        approval.status, approval.decided_at = "approved", clock.now
        await _handlers["list_call"](s, approval)
        await s.commit()

    assert (await tick(client))["dialed"] == 2
    assert sorted(p.phone_e164 for p in voice.placed) == PHONES[:2]
    removed = await client.get(f"/v1/campaigns/{cid}/contacts?status=skipped", headers=t["headers"])
    [row] = removed.json()["items"]
    assert row["phone_last4"] == "0003"
    assert row["reasons"] == ["removed_at_approval"]
    detail = (await client.get(f"/v1/campaigns/{cid}", headers=t["headers"])).json()
    assert detail["status"] == "completed"
    assert detail["progress"]["skipped"] == 1
    assert detail["progress"]["blocked_summary"] == []


async def test_approval_for_another_campaign_is_ignored(
    client: httpx.AsyncClient, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure()
    morning_clock(clock)

    async def always(*_a: Any) -> bool:
        return True

    monkeypatch.setattr(hooks, "needs_list_approval", always)
    t = await tenant(client)
    first = (await _create(client, t))["campaign"]["id"]
    second = (await _create(client, t, text="Phone\n9876500009\n"))["campaign"]["id"]
    approval_id = (await _action(client, t, first, "start")).json()["approval_id"]
    await _action(client, t, second, "start")

    from mitra_core.approvals.service import _handlers
    from mitra_core.db import tenant_session
    from mitra_core.models import Approval
    from mitra_core.tenancy import TenantContext

    bid = uuid.UUID(t["business"]["id"])
    async with tenant_session(TenantContext(business_id=bid)) as s:
        approval = await s.get(Approval, uuid.UUID(approval_id))
        assert approval is not None
        approval.payload = {**approval.payload, "campaign_id": second}  # edited to point elsewhere
        approval.status, approval.decided_at = "approved", clock.now
        await _handlers["list_call"](s, approval)
        await s.commit()
    for cid in (first, second):
        detail = (await client.get(f"/v1/campaigns/{cid}", headers=t["headers"])).json()
        assert detail["status"] == "pending_approval"


async def test_small_list_starts_without_approval(client: httpx.AsyncClient) -> None:
    configure()
    t = await tenant(client)
    cid = (await _create(client, t))["campaign"]["id"]  # 3 people < default threshold 50
    assert (await _action(client, t, cid, "start")).json()["status"] == "running"


async def test_roles_and_isolation(client: httpx.AsyncClient, clock: FakeClock) -> None:
    configure()
    morning_clock(clock)
    a = await tenant(client)
    b = await tenant(client)
    cid = (await _create(client, a))["campaign"]["id"]
    assert (await client.get(f"/v1/campaigns/{cid}", headers=b["headers"])).status_code == 404
    assert (await _action(client, b, cid, "start")).status_code == 404
    resp = await client.post(
        "/v1/campaigns",
        json={"name": "x", "employee_id": a["employee"]["id"], "text": CSV},
        headers=b["headers"],
    )
    assert resp.status_code == 404  # another business's employee
    assert (await client.get("/v1/campaigns", headers=b["headers"])).json()["items"] == []
    settings = await client.put(
        "/v1/campaigns/settings", json={"channels": 3}, headers=a["headers"]
    )
    assert settings.json() == {"channels": 3}
    assert (await client.get("/v1/campaigns/settings", headers=b["headers"])).json() == {
        "channels": 5
    }


async def test_list_approval_edit_can_only_lower_the_count(
    client: httpx.AsyncClient, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """APPR-06 server rule: a list call can be cut down, never raised or pointed elsewhere."""
    configure()
    morning_clock(clock)

    async def always(*_a: Any) -> bool:
        return True

    monkeypatch.setattr(hooks, "needs_list_approval", always)
    t = await tenant(client)
    await consent(client, t, *PHONES)
    cid = (await _create(client, t))["campaign"]["id"]
    approval_id = (await _action(client, t, cid, "start")).json()["approval_id"]
    url = f"/v1/approvals/{approval_id}"
    card = (await client.get(url, headers=t["headers"])).json()
    card = card.get("approval", card)
    assert card["editable"] == ["contacts"]
    payload = card["payload"]

    async def edit(**changes: Any) -> httpx.Response:
        body = {"version": card["version"], "payload": {**payload, **changes}}
        return await client.patch(url, json=body, headers=t["headers"])

    for bad in (4, 0, 2.5, True):
        resp = await edit(contacts=bad)
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"]["code"] == "invalid_edit"
    other = await edit(campaign_id=str(uuid.uuid4()))
    assert other.status_code == 422
    assert other.json()["error"]["code"] == "not_editable"
    ok = await edit(contacts=2)
    assert ok.status_code == 200, ok.text
    assert ok.json()["payload"]["contacts"] == 2
