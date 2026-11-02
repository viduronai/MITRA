"""Post-call analysis: deterministic heuristics and the optional LLM summarizer (mocked)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
from pydantic import SecretStr

from mitra_core.calls.summarizer import (
    ActionRecord,
    CallInput,
    HeuristicSummarizer,
    LlmSummarizer,
    Turn,
    analyze_heuristic,
    get_summarizer,
)
from mitra_core.config import Settings
from mitra_core.models.enums import CallDirection, CallResult, MemoryStatus, Sentiment

ENDED = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


def _call(turns: list[tuple[str, str]], actions: list[ActionRecord] | None = None) -> CallInput:
    return CallInput(
        transcript=[Turn(role, text) for role, text in turns],  # type: ignore[arg-type]
        actions=actions or [],
        direction=CallDirection.INBOUND,
        language="hi",
        ended_at=ENDED,
    )


def test_lead_fields_budget_and_interest() -> None:
    call = _call(
        [("user", "3BHK chahiye Kondapur mein, budget 70 lakh tak"), ("assistant", "Noted.")],
        [
            ActionRecord("record_field", {"field": "Bedrooms", "value": "3BHK"}, {}, ok=True),
            ActionRecord(
                "record_field", {"field": "preferred location", "value": "Kondapur"}, {}, ok=True
            ),
        ],
    )
    a = analyze_heuristic(call)
    assert a.result == CallResult.INTERESTED
    assert a.fields == {"bedrooms": "3BHK", "preferred_location": "Kondapur"}
    memory = {m.key: m for m in a.memory}
    assert memory["bedrooms"].status == MemoryStatus.CONFIRMED
    assert memory["budget"].status == MemoryStatus.INFERRED
    assert memory["budget"].value == "70 lakh"
    assert memory["preferred_language"].value == "Hindi"
    assert "Interested; shared bedrooms, preferred location." in a.summary


def test_not_interested_and_summary_cap() -> None:
    long = " ".join(["bahut"] * 200)
    a = analyze_heuristic(_call([("user", f"{long} not interested")]))
    assert a.result == CallResult.NOT_INTERESTED
    assert len(a.summary.split()) <= 80


def test_failed_booking_is_not_booked() -> None:
    a = analyze_heuristic(
        _call(
            [("user", "Book tomorrow 9 pm please")],
            [
                ActionRecord(
                    "book_slot", {"date": "2026-10-21"}, {"status": "unavailable"}, ok=False
                )
            ],
        )
    )
    assert a.result == CallResult.INFO_ONLY
    assert a.commitments == []


def test_native_script_sentiment_and_deferral() -> None:
    a = analyze_heuristic(
        _call(
            [
                ("user", "మీ సర్వీస్ చెత్త"),
                ("user", "EMI option undha?"),
                ("assistant", "Naaku teliyadu, nenu కనుక్కొని cheptanu."),
            ]
        )
    )
    assert a.sentiment == Sentiment.NEGATIVE
    assert a.unknown_questions == ["EMI option undha?"]


def _llm(handler: httpx.MockTransport) -> LlmSummarizer:
    return LlmSummarizer("https://llm.example/v1", "k", "test-model", transport=handler)


async def test_llm_summarizer_merges_without_overriding_confirmed() -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        content = {
            "summary": "Caller wants a 3BHK in Kondapur under 70L.",
            "sentiment": "positive",
            "memory": [
                {"key": "bedrooms", "value": "2BHK", "status": "inferred"},
                {"key": "family", "value": "Lives with parents", "status": "confirmed"},
            ],
            "unknown_questions": ["Is there a clubhouse?"],
        }
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(content)}}]}
        )

    call = _call(
        [("user", "3BHK in Kondapur, parents ke saath rehte hain")],
        [ActionRecord("record_field", {"field": "bedrooms", "value": "3BHK"}, {}, ok=True)],
    )
    a = await _llm(httpx.MockTransport(handle)).analyze(call)
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "test-model"  # type: ignore[index]
    assert a.summary == "Caller wants a 3BHK in Kondapur under 70L."
    assert a.sentiment == Sentiment.POSITIVE
    memory = {m.key: m for m in a.memory}
    assert memory["bedrooms"].value == "3BHK"  # action-confirmed beats the model's guess
    assert memory["family"].status == MemoryStatus.CONFIRMED
    assert a.unknown_questions == ["Is there a clubhouse?"]
    assert a.result == CallResult.INTERESTED


async def test_llm_summarizer_falls_back_on_errors() -> None:
    call = _call([("user", "Fee entha andi?")])
    expected = await HeuristicSummarizer().analyze(call)
    for transport in (
        httpx.MockTransport(lambda r: httpx.Response(500)),
        httpx.MockTransport(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "nope"}}]})
        ),
    ):
        assert await _llm(transport).analyze(call) == expected


def test_summarizer_selection() -> None:
    assert isinstance(get_summarizer(Settings()), HeuristicSummarizer)
    assert isinstance(get_summarizer(Settings(summarizer="llm")), HeuristicSummarizer)
    configured = Settings(
        summarizer="llm",
        summarizer_llm_url="https://llm.example/v1",
        summarizer_llm_api_key=SecretStr("k"),
        summarizer_llm_model="m",
    )
    assert isinstance(get_summarizer(configured), LlmSummarizer)
