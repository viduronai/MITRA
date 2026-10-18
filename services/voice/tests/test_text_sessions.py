from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mitra_voice.app import create_app
from mitra_voice.config import Settings

EVAL_PACK = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "sunrise_clinic.json"


def _pack() -> dict[str, Any]:
    if EVAL_PACK.exists():
        data: dict[str, Any] = json.loads(EVAL_PACK.read_text(encoding="utf-8"))
        return data
    return {  # minimal stand-in shaped like the evals schema
        "id": "sunrise_clinic",
        "business_name": "Sunrise Clinic",
        "industry": "clinic",
        "employee_name": "Priya",
        "role": "receptionist",
        "default_language": "te",
        "languages": ["te", "en"],
        "greeting": {
            "inbound": {"en": "Hello, this is Priya, an AI assistant. This call may be recorded."}
        },
        "facts": [
            {
                "key": "consultation_fee",
                "category": "prices",
                "label": "General consultation fee",
                "value": "₹500",
            }
        ],
        "behaviour": {"ask_for": ["patient name"], "never_say": [], "escalate_to": "Front desk"},
    }


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings())) as c:
        yield c


def test_text_session_contract(client: TestClient) -> None:
    res = client.post(
        "/v1/text-sessions",
        json={
            "pack": _pack(),
            "context": {"scenario_id": "s1", "language": "en", "direction": "inbound"},
        },
    )
    assert res.status_code == 201
    body = res.json()
    sid, greeting = body["session_id"], body["reply"]
    assert "AI" in greeting["text"]
    assert "record" in greeting["text"]
    assert greeting["actions"] == []
    assert greeting["end_call"] is False

    fee = client.post(
        f"/v1/text-sessions/{sid}/turns", json={"text": "What is the consultation fee?"}
    )
    assert fee.status_code == 200
    assert "₹500" in fee.json()["text"]

    book = client.post(
        f"/v1/text-sessions/{sid}/turns",
        json={"text": "Book me tomorrow morning", "interrupt": True},
    ).json()
    assert {"name": "check_availability", "args": {}} in book["actions"]

    sos = client.post(
        f"/v1/text-sessions/{sid}/turns", json={"text": "My father has chest pain!"}
    ).json()
    assert {a["name"] for a in sos["actions"]} == {"transfer_to_human", "alert_staff"}

    stop = client.post(
        f"/v1/text-sessions/{sid}/turns", json={"text": "Please don't call me again"}
    ).json()
    assert [a["name"] for a in stop["actions"]] == ["opt_out"]
    assert stop["end_call"] is True

    assert client.delete(f"/v1/text-sessions/{sid}").status_code == 204
    assert client.delete(f"/v1/text-sessions/{sid}").status_code == 404
    assert client.post(f"/v1/text-sessions/{sid}/turns", json={"text": "hi"}).status_code == 404


def test_invalid_pack_is_422(client: TestClient) -> None:
    assert client.post("/v1/text-sessions", json={"pack": {"id": "x"}}).status_code == 422
