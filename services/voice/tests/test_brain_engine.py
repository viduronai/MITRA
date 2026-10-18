"""The brain turn loop against a scripted fake Gemini (no network): tool execution, guardrail
short-circuits, post-check on streamed text, first-token timeout -> retry -> apology."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from google.genai import types
from pipecat.processors.aggregators.llm_context import LLMContext

from mitra_voice.brain.backend import ChatBackend
from mitra_voice.brain.engine import Brain, BrainConfig, Message, TurnResult
from mitra_voice.brain.gemini_backend import GeminiBackend
from mitra_voice.brain.llm import history_from_context
from mitra_voice.brain.tools import IST, ToolExecutor
from mitra_voice.config import Settings
from mitra_voice.pack import EmployeePack
from mitra_voice.text_sessions import TextSessionIn, TextSessionStore, pack_from_eval
from tests.brain_fakes import FakeModels, Scripted, calls, say

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


def _brain(pack: EmployeePack, fake: FakeModels | ChatBackend, **config: Any) -> Brain:
    cfg = BrainConfig(model="fast-model", **config)
    backend = GeminiBackend(fake) if isinstance(fake, FakeModels) else fake
    return Brain(backend, cfg, pack, clock=lambda: NOW)


async def test_tool_loop_executes_locally_and_returns_actions(clinic: EmployeePack) -> None:
    probe = ToolExecutor(clinic, clock=lambda: NOW)
    slot = probe.execute("check_availability", {"date": "2026-10-22", "part_of_day": "evening"})
    fake = FakeModels(
        [
            calls(("book_slot", {"date": "2026-10-22", "time": slot["free_slots"][0]})),
            calls(("send_whatsapp_template", {"template": "booking_confirmation"})),
            say("Done Kiran, booked for tomorrow at 5 PM. ", "Details on WhatsApp."),
        ]
    )
    brain = _brain(clinic, fake)
    result = await brain.turn([], "Book me tomorrow evening, name Kiran.", "en")
    assert [a.name for a in result.actions] == ["book_slot", "send_whatsapp_template"]
    assert result.text == "Done Kiran, booked for tomorrow at 5 PM. Details on WhatsApp."
    # The tool result went back to the model as a function response.
    second = fake.requests[1]["contents"]
    response = second[-1].parts[0].function_response
    assert response.name == "book_slot"
    assert response.response["status"] == "booked"
    # Static system prompt (cacheable), per-turn notes on the caller's message.
    config = fake.requests[0]["config"]
    assert config.system_instruction == brain.system_prompt
    assert "CONFIRMED FACTS" in brain.system_prompt
    caller = fake.requests[0]["contents"][-1].parts[0].text
    assert "[reply language: en]" in caller
    assert "Wednesday 2026-10-21" in caller
    assert brain.usage.cached_tokens == 800


async def test_history_and_tool_log_reach_the_model(clinic: EmployeePack) -> None:
    fake = FakeModels(
        [calls(("check_availability", {"date": "tomorrow"})), say("Tomorrow is open."), say("Ok.")]
    )
    brain = _brain(clinic, fake)
    await brain.turn([Message("assistant", "Hello, AI assistant.")], "Tomorrow?", "en")
    await brain.turn(
        [Message("assistant", "Hello."), Message("user", "Tomorrow?")], "Morning?", "en"
    )
    last = fake.requests[-1]["contents"]
    assert [c.role for c in last] == ["model", "user", "user"]
    assert "check_availability" in last[-1].parts[0].text  # tool log of earlier turns


async def test_emergency_never_calls_the_model(clinic: EmployeePack) -> None:
    fake = FakeModels([])
    result = await _brain(clinic, fake).turn([], "My father has chest pain!", "en")
    assert fake.requests == []
    assert result.guard == "emergency"
    assert "112" in result.text
    assert {a.name for a in result.actions} == {"transfer_to_human", "alert_staff"}


async def test_opt_out_ends_the_call_without_the_model(clinic: EmployeePack) -> None:
    fake = FakeModels([])
    result = await _brain(clinic, fake).turn([], "Please don't call me again.", "en")
    assert fake.requests == []
    assert result.end_call
    assert [a.name for a in result.actions] == ["opt_out", "end_call"]


async def test_medical_turn_instruction_and_enforcement(clinic: EmployeePack) -> None:
    fake = FakeModels([say("Paracetamol 500 mg is fine. ", "See the doctor.")])
    result = await _brain(clinic, fake).turn([], "Which tablet should I take for fever?", "en")
    note = fake.requests[0]["contents"][-1].parts[0].text
    assert "GUARDRAIL" in note
    assert result.guard == "medical"
    assert "medical" in result.violations
    assert "aracetamol" not in result.text
    assert "doctor" in result.text


async def test_streamed_amounts_are_post_checked(clinic: EmployeePack) -> None:
    fake = FakeModels([say("Our ultrasound is ₹1,500. ", "Want a slot?")])
    brain = _brain(clinic, fake)
    result = TurnResult()
    sentences = [s async for s in brain.stream_turn([], "Ultrasound price?", "en", result)]
    assert result.violations == ["amount"]
    assert all("1,500" not in s for s in sentences)
    assert sentences[-1] == "Want a slot?"


async def test_brevity_cap_keeps_two_sentences(clinic: EmployeePack) -> None:
    fake = FakeModels([say("One. ", "Two. ", "Three.")])
    result = await _brain(clinic, fake).turn([], "Tell me everything.", "en")
    assert result.text == "One. Two."


async def test_first_token_timeout_retries_on_the_slow_model(clinic: EmployeePack) -> None:
    fake = FakeModels([say("late", delay_s=0.5), say("Sunday 10 AM to 1 PM.")])
    retried: list[bool] = []

    async def on_retry() -> None:
        retried.append(True)

    brain = _brain(clinic, fake, first_token_timeout_s=0.05, slow_model="slow-model")
    result = TurnResult()
    async for _ in brain.stream_turn([], "Open on Sunday?", "en", result, on_retry=on_retry):
        pass
    assert result.retried
    assert retried == [True]
    assert [r["model"] for r in fake.requests] == ["fast-model", "slow-model"]
    assert result.text == "Sunday 10 AM to 1 PM."


async def test_retry_failure_apologises_and_schedules_a_callback(clinic: EmployeePack) -> None:
    fake = FakeModels([say("late", delay_s=0.5), say("late", delay_s=0.5)])
    brain = _brain(clinic, fake, first_token_timeout_s=0.05, retry_timeout_s=0.05)
    result = await brain.turn([], "ఫీజు ఎంత?", "te")
    assert result.failed
    assert "క్షమించండి" in result.text
    assert [a.name for a in result.actions] == ["schedule_callback"]


async def test_api_errors_apologise(clinic: EmployeePack) -> None:
    fake = FakeModels([Scripted([], error=RuntimeError("500 internal"))])
    result = await _brain(clinic, fake).turn([], "Fee?", "hi")
    assert result.failed
    assert "माफ़" in result.text


async def test_rate_limits_are_waited_out_only_when_allowed(clinic: EmployeePack) -> None:
    error = RuntimeError("429 RESOURCE_EXHAUSTED 'retryDelay': '0s'")
    fake = FakeModels([Scripted([], error=error), say("₹500.")])
    result = await _brain(clinic, fake, max_rate_limit_wait_s=5).turn([], "Fee?", "en")
    assert result.text == "₹500."
    fake = FakeModels([Scripted([], error=error)])
    assert (await _brain(clinic, fake).turn([], "Fee?", "en")).failed


async def test_thinking_level_falls_back_when_minimal_is_rejected(clinic: EmployeePack) -> None:
    error = RuntimeError("400 INVALID_ARGUMENT: thinking_level minimal is not supported")
    fake = FakeModels([Scripted([], error=error), say("Hello.")])
    result = await _brain(clinic, fake, reasoning="minimal").turn([], "Hi", "en")
    assert result.text == "Hello."
    config = fake.requests[1]["config"]
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW


def test_history_from_pipecat_context() -> None:
    context = LLMContext(
        messages=[
            {"role": "system", "content": "prompt"},
            {"role": "assistant", "content": "Hello, I'm an AI assistant."},
            {"role": "user", "content": "Fee?"},
            {"role": "assistant", "content": "₹500."},
            {"role": "user", "content": "And"},
            {"role": "user", "content": [{"type": "text", "text": "Sunday?"}]},
        ]
    )
    history, caller = history_from_context(context)
    assert caller == "And Sunday?"
    assert [m.role for m in history] == ["assistant", "user", "assistant"]


async def test_text_sessions_route_through_the_brain(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeModels([say("జనరల్ కన్సల్టేషన్ ఫీజు 500 రూపాయలు అండి.")])
    monkeypatch.setattr("mitra_voice.text_sessions.make_backend", lambda _: GeminiBackend(fake))
    settings = Settings(
        mitra_llm="gemini",
        gemini_api_key="test-key",
        mitra_llm_model="fast-model",
        mitra_brain_fixed_now=NOW,
    )
    store = TextSessionStore(settings=settings)
    assert store.uses_brain
    body = TextSessionIn(pack=_eval_pack("sunrise_clinic"), context={"language": "te"})
    session = store.open(body)
    assert "AI" in session.start()["text"]
    reply = await session.send("కన్సల్టేషన్ ఫీజు ఎంత?")
    assert reply["text"].startswith("జనరల్")
    assert "first_token_ms" in reply["timings"]
    # Localised fact wording is in the prompt.
    assert "500 రూపాయలు" in fake.requests[0]["config"].system_instruction
    emergency = await session.send("ఛాతీ నొప్పి వస్తుంది!")
    assert {a["name"] for a in emergency["actions"]} == {"transfer_to_human", "alert_staff"}


def test_text_sessions_stay_on_the_mock_without_gemini() -> None:
    assert not TextSessionStore(settings=Settings()).uses_brain


async def test_eval_cache_replays_identical_requests(clinic: EmployeePack, tmp_path: Path) -> None:
    from mitra_voice.brain.cache import CachingBackend

    fake = FakeModels([calls(("check_availability", {"date": "tomorrow"})), say("Tomorrow works.")])
    cached = CachingBackend(GeminiBackend(fake), tmp_path)
    first = await _brain(clinic, cached).turn([], "Is tomorrow free?", "en")
    assert cached.misses == 2
    replay = await _brain(clinic, cached).turn([], "Is tomorrow free?", "en")
    assert replay.text == first.text == "Tomorrow works."
    assert [a.name for a in replay.actions] == ["check_availability"]
    assert cached.hits == 2
    assert len(fake.requests) == 2  # nothing new reached the model


async def test_cues_add_turn_instructions(clinic: EmployeePack) -> None:
    fake = FakeModels([say("Booked."), say("Sent.")])
    brain = _brain(clinic, fake)
    offer = [Message("assistant", "Would you like to book an appointment with Dr. Kavitha?")]
    await brain.turn(offer, "Yes, Thursday morning is fine.", "en")
    assert "BOOKING CUE" in fake.requests[0]["contents"][-1].parts[0].text
    dob = [Message("assistant", "May I have the patient's date of birth?")]
    await brain.turn(dob, "5 जून 1990", "hi")
    assert "REPORT CUE" in fake.requests[1]["contents"][-1].parts[0].text


async def test_retry_filler_is_skipped_when_the_pipeline_already_spoke_one(
    clinic: EmployeePack, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pipecat.frames.frames import TTSSpeakFrame

    from mitra_voice.brain.llm import MitraBrainLLMService
    from mitra_voice.call_context import CallContext

    settings = Settings(mitra_llm="gemini", gemini_api_key="k", mitra_llm_model="fast-model")
    for already_spoken, expected in ((True, 0), (False, 1)):
        call = CallContext(session_id="s", language="en")
        call.filler_spoken = already_spoken
        service = MitraBrainLLMService(pack=clinic, settings=settings, call=call)
        service.turns.brain = _brain(
            clinic, FakeModels([say("late", delay_s=0.5), say("Ok.")]), first_token_timeout_s=0.05
        )
        pushed: list[object] = []

        async def capture(frame: object, *_: object) -> None:
            pushed.append(frame)  # noqa: B023

        monkeypatch.setattr(service, "push_frame", capture)
        monkeypatch.setattr(service, "_push_llm_text", capture)
        context = LLMContext(messages=[{"role": "user", "content": "Fee?"}])
        await service._process_context(context)
        assert sum(isinstance(f, TTSSpeakFrame) for f in pushed) == expected
        assert call.filler_spoken
