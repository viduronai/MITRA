from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mitra_voice.app import create_app
from mitra_voice.config import Settings
from mitra_voice.pack import FIXTURES_DIR, load_fixture
from mitra_voice.providers import ProviderConfigError, resolve_providers
from mitra_voice.session import CallSession


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings())) as c:
        yield c


def test_index_serves_the_test_page(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "Start talking" in res.text
    assert "/api/offer" in res.text


def test_health_reports_providers(client: TestClient) -> None:
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["providers"] == {"stt": "mock", "llm": "mock", "tts": "mock"}
    assert health["loop_lag_max_ms"] >= 0


def test_metrics_endpoint(client: TestClient) -> None:
    assert client.get("/sessions/nope/metrics").status_code == 404
    session = CallSession(
        scenario="clinic",
        pack=load_fixture(FIXTURES_DIR / "sunrise-clinic.json"),
        providers=resolve_providers(Settings()),
    )
    client.app.state.sessions.add(session)  # type: ignore[attr-defined]
    body = client.get(f"/sessions/{session.id}/metrics").json()
    assert body["session_id"] == session.id
    assert body["turns"] == []
    assert body["summary"]["first_audio_ms"] == {"n": 0, "p50": None, "p95": None}
    assert client.get("/sessions").json()[0]["session_id"] == session.id


def test_offer_input_is_validated(client: TestClient) -> None:
    assert client.post("/api/offer", json={"sdp": "v=0", "type": "answer"}).status_code == 422
    bad = {"sdp": "v=0", "type": "offer", "scenario": "bakery"}
    assert client.post("/api/offer", json=bad).status_code == 422


def test_non_local_startup_fails_fast_without_keys() -> None:
    app = create_app(Settings(mitra_env="staging", mitra_llm="anthropic"))  # type: ignore[arg-type]
    with pytest.raises(ProviderConfigError), TestClient(app):
        pass
