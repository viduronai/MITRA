"""The brain on Groq's OpenAI-compatible API, against a scripted fake client (no network):
streamed tool-call deltas, tool messages, reasoning stripping, 429 retry-after, pacing, the
eval cache, text-session routing and the Pipecat service."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from mitra_voice.brain import backend as backend_module
from mitra_voice.brain.backend import ChatRequest, ChatTurn, ToolCall, pace, reset_pacing
from mitra_voice.brain.cache import CachingBackend
from mitra_voice.brain.client import brain_config
from mitra_voice.brain.engine import Brain, BrainConfig
from mitra_voice.brain.openai_backend import OpenAICompatBackend, _ThinkFilter, messages_for
from mitra_voice.brain.tools import IST, TOOL_SPECS, ToolExecutor
from mitra_voice.config import Settings
from mitra_voice.pack import EmployeePack
from mitra_voice.text_sessions import TextSessionIn, TextSessionStore, pack_from_eval
from tests.groq_fakes import FakeOpenAI, RateLimitedError, Step, text, tool_delta, usage

FIXTURES = Path(__file__).resolve().parents[3] / "evals" / "fixtures"
NOW = datetime(2026, 10, 21, 8, 0, tzinfo=IST)


def _eval_pack(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        pytest.skip("evals fixtures not present")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def clinic() -> EmployeePack:
    return pack_from_eval(_eval_pack("sunrise_clinic"))


def _brain(pack: EmployeePack, fake: FakeOpenAI, **config: Any) -> Brain:
    cfg = BrainConfig(model="groq-model", **config)
    return Brain(OpenAICompatBackend(fake), cfg, pack, clock=lambda: NOW)


def _free_evening_slot(pack: EmployeePack) -> str:
    probe = ToolExecutor(pack, clock=lambda: NOW)
    free = probe.execute("check_availability", {"date": "2026-10-22", "part_of_day": "evening"})
    slot: str = free["free_slots"][0]
    return slot


async def test_streamed_tool_call_deltas_are_assembled_and_executed(
    clinic: EmployeePack,
) -> None:
    slot = _free_evening_slot(clinic)
    args = json.dumps({"date": "2026-10-22", "time": slot, "name": "Kiran"})
    fake = FakeOpenAI(
        [
            # The call arrives in pieces: id + name first, arguments split across chunks.
            Step(
                [
                    tool_delta(0, id="call_a", name="book_slot", args=args[:15]),
                    tool_delta(0, args=args[15:]),
                    tool_delta(1, id="call_b", name="send_whatsapp_template"),
                    tool_delta(1, args='{"template": "booking_confirmation"}'),
                    usage(),
                ]
            ),
            Step([text("Done Kiran, "), text("booked for tomorrow at 5 PM. "), usage(1300)]),
        ]
    )
    brain = _brain(clinic, fake)
    result = await brain.turn([], "Book me tomorrow evening, name Kiran.", "en")
    assert [a.name for a in result.actions] == ["book_slot", "send_whatsapp_template"]
    assert result.actions[0].args["name"] == "Kiran"
    assert result.text == "Done Kiran, booked for tomorrow at 5 PM."
    first, second = fake.requests
    assert first["stream"] is True
    assert first["tool_choice"] == "auto"
    assert {t["function"]["name"] for t in first["tools"]} == set(TOOL_SPECS)
    assert first["messages"][0] == {"role": "system", "content": brain.system_prompt}
    assert "reasoning_effort" not in first  # provider default unless configured
    # The second request carries the assistant tool calls and one tool message per call.
    msgs = second["messages"]
    assert msgs[-3]["role"] == "assistant"
    assert [c["id"] for c in msgs[-3]["tool_calls"]] == ["call_a", "call_b"]
    assert msgs[-2]["role"] == "tool"
    assert msgs[-2]["tool_call_id"] == "call_a"
    assert json.loads(msgs[-2]["content"])["status"] == "booked"
    assert msgs[-1]["tool_call_id"] == "call_b"
    assert brain.usage.prompt_tokens == 2500
    assert brain.usage.requests == 2


async def test_guardrails_short_circuit_on_groq_too(clinic: EmployeePack) -> None:
    fake = FakeOpenAI([])
    result = await _brain(clinic, fake).turn([], "మా అమ్మకి ఛాతీ నొప్పి వస్తుంది!", "te")
    assert fake.requests == []
    assert "112" in result.text
    assert {a.name for a in result.actions} == {"transfer_to_human", "alert_staff"}


async def test_amount_post_check_on_groq(clinic: EmployeePack) -> None:
    fake = FakeOpenAI([Step([text("An ultrasound is ₹900. "), text("Want a slot?")])])
    result = await _brain(clinic, fake).turn([], "Ultrasound price?", "en")
    assert result.violations == ["amount"]
    assert "900" not in result.text


def test_think_filter_strips_inline_reasoning_across_chunks() -> None:
    f = _ThinkFilter()
    out = f.feed("<thi") + f.feed("nk>plan the reply</th") + f.feed("ink>Hello, ")
    out += f.feed("₹500.<think>more</think> Bye.") + f.flush()
    assert out == "Hello, ₹500. Bye."
    assert _ThinkFilter().feed("a < b") == "a < b"


async def test_reasoning_is_sent_and_dropped_when_rejected(clinic: EmployeePack) -> None:
    error = RuntimeError("400 `reasoning_effort` is not supported with this model")
    fake = FakeOpenAI([Step([], error=error), Step([text("Hello.")])])
    result = await _brain(clinic, fake, reasoning="low").turn([], "Hi", "en")
    assert result.text == "Hello."
    assert fake.requests[0]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in fake.requests[1]


async def test_429_retry_after_is_honoured_in_text_mode(
    clinic: EmployeePack, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    fake = FakeOpenAI([Step([], error=RateLimitedError(retry_after="2")), Step([text("₹500.")])])
    brain = _brain(clinic, fake, max_rate_limit_wait_s=30)
    monkeypatch.setattr("mitra_voice.brain.engine.asyncio.sleep", fake_sleep)
    result = await brain.turn([], "Fee?", "en")
    assert result.text == "₹500."
    assert slept == [2.5]
    # Live calls (no wait budget) fail fast to the apology instead.
    fake = FakeOpenAI([Step([], error=RateLimitedError(retry_after="2"))])
    assert (await _brain(clinic, fake).turn([], "Fee?", "en")).failed


def test_groq_rate_limit_parsing() -> None:
    b = OpenAICompatBackend(FakeOpenAI([]))
    assert b.rate_limit_delay(RateLimitedError(retry_after="7")) == 7.5
    msg = "Rate limit reached on tokens per minute. Please try again in 1m2.5s."
    assert b.rate_limit_delay(RateLimitedError(message=msg)) == 63.0
    assert b.rate_limit_delay(RateLimitedError(message="try again in 450ms")) == pytest.approx(0.95)
    assert b.rate_limit_delay(ValueError("bad request")) is None
    server_error = RuntimeError("boom")
    server_error.status_code = 503  # type: ignore[attr-defined]
    assert b.is_transient(server_error)


async def test_pacing_spaces_requests_per_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(backend_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(backend_module.asyncio, "sleep", fake_sleep)
    reset_pacing()
    for _ in range(2):
        await pace("groq", "m", 100, max_rpm=2, max_tpm=0)
    assert slept == []
    await pace("groq", "m", 100, max_rpm=2, max_tpm=0)  # third in the same minute waits
    assert slept == [pytest.approx(60.05)]
    await pace("gemini", "m", 100, max_rpm=2, max_tpm=0)  # other provider: own budget
    assert len(slept) == 1
    slept.clear()
    await pace("groq", "t", 900, max_rpm=0, max_tpm=1000)
    await pace("groq", "t", 900, max_rpm=0, max_tpm=1000)  # token budget exceeded: waits
    assert slept
    reset_pacing()


async def test_eval_cache_replays_groq_streams(clinic: EmployeePack, tmp_path: Path) -> None:
    fake = FakeOpenAI(
        [
            Step([tool_delta(0, id="c1", name="check_availability", args='{"date": "tomorrow"}')]),
            Step([text("Tomorrow works.")]),
        ]
    )
    cached = CachingBackend(OpenAICompatBackend(fake), tmp_path)
    cfg = BrainConfig(model="groq-model")
    first = await Brain(cached, cfg, clinic, clock=lambda: NOW).turn([], "Tomorrow?", "en")
    again = await Brain(cached, cfg, clinic, clock=lambda: NOW).turn([], "Tomorrow?", "en")
    assert first.text == again.text == "Tomorrow works."
    assert [a.name for a in again.actions] == ["check_availability"]
    assert (cached.misses, cached.hits) == (2, 2)
    assert len(fake.requests) == 2


def test_messages_for_neutral_transcript() -> None:
    call = ToolCall("record_field", {"field": "budget", "value": "60 lakh"}, id="x1")
    msgs = messages_for(
        "SYS",
        (
            ChatTurn(role="user", text="Budget 60 lakh"),
            ChatTurn(role="assistant", calls=(call,)),
            ChatTurn(role="tool", results=((call, {"status": "saved"}),)),
            ChatTurn(role="assistant", text="Noted."),
        ),
    )
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "assistant"]
    assert msgs[2]["content"] is None
    assert json.loads(msgs[2]["tool_calls"][0]["function"]["arguments"])["field"] == "budget"
    assert msgs[3] == {"role": "tool", "tool_call_id": "x1", "content": '{"status": "saved"}'}


def test_request_token_estimate_grows_with_the_transcript() -> None:
    short = ChatRequest("m", "s" * 300, (ChatTurn(role="user", text="hi"),), 0.3, 100)
    long = ChatRequest("m", "s" * 300, (ChatTurn(role="user", text="x" * 3000),), 0.3, 100)
    assert long.estimated_tokens() - short.estimated_tokens() == pytest.approx(1000, abs=2)


def test_groq_settings_and_per_provider_limits() -> None:
    settings = Settings(
        mitra_llm="groq",
        groq_api_key="k",
        mitra_llm_model="groq-model",
        groq_max_rpm=30,
        groq_max_tpm=6000,
        gemini_max_rpm=5,
        mitra_llm_rate_limit_wait_s=60,
    )
    live, text_mode = brain_config(settings), brain_config(settings, text_mode=True)
    assert (live.max_rpm, live.max_tpm, live.reasoning) == (30, 6000, None)
    assert (live.max_rate_limit_wait_s, text_mode.max_rate_limit_wait_s) == (0.0, 60)
    gemini = brain_config(settings.model_copy(update={"mitra_llm": "gemini"}))
    assert (gemini.max_rpm, gemini.reasoning) == (5, "minimal")


async def test_text_sessions_route_through_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenAI([Step([text("जनरल कंसल्टेशन की फीस 500 रुपये है।")])])
    monkeypatch.setattr(
        "mitra_voice.text_sessions.make_backend", lambda _: OpenAICompatBackend(fake)
    )
    settings = Settings(
        mitra_llm="groq", groq_api_key="k", mitra_llm_model="groq-model", mitra_brain_fixed_now=NOW
    )
    store = TextSessionStore(settings=settings)
    assert store.uses_brain
    session = store.open(
        TextSessionIn(pack=_eval_pack("sunrise_clinic"), context={"language": "hi"})
    )
    session.start()
    reply = await session.send("डॉक्टर को दिखाने की फीस कितनी है?")
    assert "500" in reply["text"]
    assert "[reply language: hi]" in fake.requests[0]["messages"][-1]["content"]
    assert not TextSessionStore(
        settings=settings.model_copy(update={"groq_api_key": None})
    ).uses_brain


async def test_groq_pipecat_service_runs_a_brain_turn(clinic: EmployeePack) -> None:
    from pipecat.processors.aggregators.llm_context import LLMContext

    from mitra_voice.brain.llm import MitraGroqBrainLLMService, make_brain_llm
    from mitra_voice.call_context import CallContext

    settings = Settings(mitra_llm="groq", groq_api_key="k", mitra_llm_model="groq-model")
    service = make_brain_llm(
        pack=clinic, settings=settings, call=CallContext(session_id="s", language="en")
    )
    assert isinstance(service, MitraGroqBrainLLMService)
    assert service.brain.backend.provider == "groq"
    fake = FakeOpenAI([Step([text("The fee is ₹500.")])])
    service.turns.brain = _brain(clinic, fake)
    spoken: list[str] = []

    async def capture_text(value: str) -> None:
        spoken.append(value)

    async def ignore(*_: object) -> None:
        return None

    service._push_llm_text = capture_text  # type: ignore[method-assign]
    service.push_frame = ignore  # type: ignore[method-assign]
    await service._process_context(LLMContext(messages=[{"role": "user", "content": "Fee?"}]))
    assert spoken == ["The fee is ₹500. "]
